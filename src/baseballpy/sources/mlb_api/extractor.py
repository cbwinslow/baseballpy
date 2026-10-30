"""MLB Stats API extractor: shared HttpClient (rate limit, HTTP/2, retry) and fresh-aware caching."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker, cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.freshness import is_fresh
from baseballpy.core.http import HttpClient, HttpResult, get_http_client
from baseballpy.core.stores import ProcessedStore, RawStore, manifest_key, schema_matches
from baseballpy.core.upstream import response_fingerprint
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.normalizer import MlbApiNormalizer

MLB_BASE_URL = "https://statsapi.mlb.com/api"
FINAL_STATES = frozenset({"Final", "Game Over", "Completed Early"})


class MlbApiExtractor:
    """Extracts official MLB data from statsapi.mlb.com with atomic, freshness-aware caching."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.normalizer = MlbApiNormalizer()
        self.store = ProcessedStore(self.cache_config)
        self.raw = RawStore(self.cache_config)
        # discard orphaned .part files from killed runs
        cleanup_stale_parts(self.cache_config.raw_root / "mlb_api")
        cleanup_stale_parts(self.cache_config.processed_root / "mlb_api")

    def _season(self, season: int | None) -> int:
        """The given season, else the current one (no season is hard-coded)."""
        return season if season is not None else self.cache_config.today_or_now().year

    @staticmethod
    def _spec(name: str) -> DatasetSpec:
        return get_dataset("mlb_api", name)

    def _fetch(self, endpoint: str, params: Mapping[str, Any] | None = None) -> HttpResult:
        """Fetch an endpoint through the shared client with audit tracking."""
        url = f"{MLB_BASE_URL}/{endpoint.lstrip('/')}"
        with default_audit_logger.track(
            operation="mlb_api_fetch", source="mlb_api", endpoint=url
        ) as tracker:
            result = self.http.get_sync(url, params=params)
            tracker.set_cache_hit(False)
            tracker.set_records(len(result.content))
            return result

    def _fetch_json(self, endpoint: str, params: Mapping[str, Any] | None = None) -> Any:
        """Fetch a JSON payload through the shared client with audit tracking."""
        return self._fetch(endpoint, params).json()

    def _read_cached(self, cache_file: Path, endpoint: str) -> pa.Table:
        with default_audit_logger.track(
            operation="mlb_api_cache_read",
            source="mlb_api",
            endpoint=endpoint,
            destination=str(cache_file),
        ) as tracker:
            table = pq.read_table(cache_file)
            tracker.set_cache_hit(True)
            tracker.set_records(len(table))
            return table

    def _extract(
        self,
        *,
        dataset: str,
        ident: str,
        endpoint: str,
        params: Mapping[str, Any] | None,
        normalize: Callable[[Any], pa.Table],
        season: int | None,
        refresh: bool,
        freshness_key: str | None = None,
    ) -> pa.Table:
        """Cache-or-fetch one dataset: freshness check, fetch, normalize, raw + processed store."""
        spec = self._spec(dataset)
        cache_file = self.store.part_path(spec, ident, season)
        entry = self.store.config.dataset_manifest("mlb_api", dataset).get_chunk(
            manifest_key(ident, season)
        )
        if (cache_file.exists() and schema_matches(spec, entry)) and self.cache_config.is_fresh(
            entry, freshness_key or dataset, season=season, refresh=refresh
        ):
            return self._read_cached(cache_file, endpoint)

        result = self._fetch(endpoint, params)
        table = normalize(result.json())
        if self.cache_config.enabled and len(table) > 0:
            self.raw.put(
                "mlb_api",
                dataset,
                f"{ident}.json",
                result.content,
                season=season,
                etag=result.etag or "",
                upstream=response_fingerprint(result.content, result.etag),
            )
            self.store.put(spec, table, chunk_id=ident, season=season)
        return table

    def extract_schedule(
        self,
        season: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        refresh: bool = False,
    ) -> pa.Table:
        """Extract and normalize game schedule."""
        part_season = season or (int(start_date[:4]) if start_date else None)
        if part_season is None:
            raise ValueError("extract_schedule needs a season or a start_date")
        params: dict[str, Any] = {"sportId": 1}
        if season:
            params["season"] = season
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        return self._extract(
            ident=f"schedule_{season or f'{start_date}_{end_date}'}",
            dataset="schedule",
            endpoint="v1/schedule",
            params=params,
            normalize=self.normalizer.normalize_schedule,
            season=part_season,
            refresh=refresh,
        )

    def _game_info(self, game_pk: int) -> tuple[bool, int | None]:
        """Look up (is_final, season) from the schedule; boxscores freeze only once final."""
        data = self._fetch_json("v1/schedule", {"sportId": 1, "gamePk": game_pk})
        for day in data.get("dates", []):
            for game in day.get("games", []):
                if game.get("gamePk") == game_pk:
                    status = game.get("status", {})
                    final = (
                        status.get("abstractGameState", "") in FINAL_STATES
                        or status.get("detailedState", "") in FINAL_STATES
                    )
                    season = game.get("season")
                    return final, int(season) if season else None
        return False, None

    def _game_is_final(self, game_pk: int) -> bool:
        """Boxscores are immutable only once the game is final."""
        return self._game_info(game_pk)[0]

    def manifest_for(self, dataset: str) -> ManifestTracker:
        """Processed-tier manifest of one MLB dataset."""
        return self.cache_config.dataset_manifest("mlb_api", dataset)

    def _find_box_parts(self, game_pk: int) -> tuple[Path | None, Path | None]:
        """Locate previously stored batting/pitching parts for a game (any season)."""
        found: list[Path | None] = []
        for name in ("box_batting", "box_pitching"):
            root = self.store.dataset_dir(self._spec(name))
            matches = sorted(root.glob(f"season=*/part-{game_pk}.parquet")) if root.exists() else []
            found.append(matches[0] if matches else None)
        return found[0], found[1]

    def extract_boxscore(
        self, game_pk: int, refresh: bool = False, season: int | None = None
    ) -> tuple[pa.Table, pa.Table]:
        """Extract and normalize game boxscore into (batting_table, pitching_table)."""
        batting_file, pitching_file = self._find_box_parts(game_pk)
        ident = f"box_{game_pk}"
        endpoint = f"v1/game/{game_pk}/boxscore"

        entry = self.manifest_for("box_batting").get_chunk(ident)
        final = bool(entry and entry.get("final"))
        ttl = None if final else self.cache_config.ttl_for("boxscore")
        if (
            batting_file is not None
            and pitching_file is not None
            and is_fresh(entry, ttl_seconds=ttl, today=self.cache_config.today, refresh=refresh)
        ):
            return (
                self._read_cached(batting_file, endpoint),
                self._read_cached(pitching_file, endpoint),
            )

        result = self._fetch(endpoint)
        batting_table, pitching_table = self.normalizer.normalize_boxscore(
            result.json(), game_pk=game_pk
        )

        if self.cache_config.enabled:
            is_final, game_season = self._game_info(game_pk)
            part_season = season or game_season or self.cache_config.today_or_now().year
            for name, table in (("box_batting", batting_table), ("box_pitching", pitching_table)):
                if len(table) > 0:
                    self.store.put(
                        self._spec(name), table, chunk_id=str(game_pk), season=part_season
                    )
            self.raw.put(
                "mlb_api",
                "box_batting",
                f"{ident}.json",
                result.content,
                season=part_season,
                etag=result.etag or "",
                upstream=response_fingerprint(result.content, result.etag),
            )
            self.manifest_for("box_batting").set_completed(
                ident,
                records_count=len(batting_table) + len(pitching_table),
                metadata={"final": is_final, "season": part_season},
            )

        return batting_table, pitching_table

    def extract_standings(self, season: int | None = None, refresh: bool = False) -> pa.Table:
        """Extract and normalize league/division standings (default: the current season)."""
        season = self._season(season)
        return self._extract(
            ident=f"standings_{season}",
            dataset="standings",
            endpoint="v1/standings",
            params={"leagueId": "103,104", "season": season},
            normalize=lambda data: self.normalizer.normalize_standings(data, season=season),
            season=season,
            refresh=refresh,
        )

    def extract_teams(self, refresh: bool = False) -> pa.Table:
        """Extract and normalize MLB franchises."""
        return self._extract(
            ident="teams_mlb",
            dataset="teams",
            endpoint="v1/teams",
            params={"sportId": 1},
            normalize=self.normalizer.normalize_teams,
            season=None,
            refresh=refresh,
        )

    def extract_roster(self, team_id: int, refresh: bool = False) -> pa.Table:
        """Extract and normalize team active roster."""
        return self._extract(
            ident=f"roster_{team_id}",
            dataset="rosters",
            freshness_key="roster",
            endpoint=f"v1/teams/{team_id}/roster",
            params=None,
            normalize=lambda data: self.normalizer.normalize_roster(data, team_id=team_id),
            season=None,
            refresh=refresh,
        )

    def extract_transactions(self, season: int | None = None, refresh: bool = False) -> pa.Table:
        """Extract and normalize roster transactions for a season (default: the current one)."""
        season = self._season(season)
        return self._extract(
            ident=f"transactions_{season}",
            dataset="transactions",
            endpoint="v1/transactions",
            params={"season": season},
            normalize=self.normalizer.normalize_transactions,
            season=season,
            refresh=refresh,
        )

    def extract_draft(self, year: int | None = None, refresh: bool = False) -> pa.Table:
        """Extract and normalize the MLB first-year player draft (default: the current year)."""
        year = self._season(year)
        return self._extract(
            ident=f"draft_{year}",
            dataset="draft",
            endpoint=f"v1/draft/{year}",
            params=None,
            normalize=lambda data: self.normalizer.normalize_draft(data, year=year),
            season=year,
            refresh=refresh,
        )

    def extract_venues(self, refresh: bool = False) -> pa.Table:
        """Extract and normalize official ballparks/venues."""
        return self._extract(
            ident="venues_all",
            dataset="venues",
            endpoint="v1/venues",
            params=None,
            normalize=self.normalizer.normalize_venues,
            season=None,
            refresh=refresh,
        )
