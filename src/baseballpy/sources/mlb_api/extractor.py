"""MLB Stats API extractor: shared HttpClient (rate limit, HTTP/2, retry) and fresh-aware caching."""

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker, atomic_write_parquet
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.core.freshness import is_fresh
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.sources.mlb_api.normalizer import MlbApiNormalizer

MLB_BASE_URL = "https://statsapi.mlb.com/api"
FINAL_STATES = frozenset({"Final", "Game Over", "Completed Early"})


class MlbApiExtractor:
    """Extracts official MLB data from statsapi.mlb.com with atomic, freshness-aware caching."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.normalizer = MlbApiNormalizer()
        self.cache_dir = self.cache_config.mlb_api_dir
        self.manifest = ManifestTracker(self.cache_dir / "manifest.json")

    def _get_cache_file(self, category: str, identifier: str) -> Path:
        cat_dir = self.cache_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        return cat_dir / f"{identifier}.parquet"

    def _fetch_json(self, endpoint: str, params: Mapping[str, Any] | None = None) -> Any:
        """Fetch a JSON payload through the shared client with audit tracking."""
        url = f"{MLB_BASE_URL}/{endpoint.lstrip('/')}"
        with default_audit_logger.track(
            operation="mlb_api_fetch", source="mlb_api", endpoint=url
        ) as tracker:
            result = self.http.get_sync(url, params=params)
            tracker.set_cache_hit(False)
            tracker.set_records(len(result.content))
            return result.json()

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
        category: str,
        ident: str,
        dataset: str,
        endpoint: str,
        params: Mapping[str, Any] | None,
        normalize: Callable[[Any], pa.Table],
        season: int | None,
        refresh: bool,
    ) -> pa.Table:
        """Cache-or-fetch one dataset: freshness check, fetch, normalize, atomic store."""
        cache_file = self._get_cache_file(category, ident)
        entry = self.manifest.get_chunk(ident)
        if cache_file.exists() and self.cache_config.is_fresh(
            entry, dataset, season=season, refresh=refresh
        ):
            return self._read_cached(cache_file, endpoint)

        table = normalize(self._fetch_json(endpoint, params))
        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(
                ident,
                records_count=len(table),
                metadata={"season": season} if season is not None else None,
            )
        return table

    def extract_schedule(
        self,
        season: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        refresh: bool = False,
    ) -> pa.Table:
        """Extract and normalize game schedule."""
        params: dict[str, Any] = {"sportId": 1}
        if season:
            params["season"] = season
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        return self._extract(
            category="schedule",
            ident=f"schedule_{season or f'{start_date}_{end_date}'}",
            dataset="schedule",
            endpoint="v1/schedule",
            params=params,
            normalize=self.normalizer.normalize_schedule,
            season=season,
            refresh=refresh,
        )

    def _game_is_final(self, game_pk: int) -> bool:
        """Look up the abstract game state; boxscores are immutable only once final."""
        data = self._fetch_json("v1/schedule", {"sportId": 1, "gamePk": game_pk})
        for day in data.get("dates", []):
            for game in day.get("games", []):
                if game.get("gamePk") == game_pk:
                    state = game.get("status", {}).get("abstractGameState", "")
                    detailed = game.get("status", {}).get("detailedState", "")
                    return state in FINAL_STATES or detailed in FINAL_STATES
        return False

    def extract_boxscore(self, game_pk: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Extract and normalize game boxscore into (batting_table, pitching_table)."""
        batting_file = self._get_cache_file("boxscores_batting", f"{game_pk}")
        pitching_file = self._get_cache_file("boxscores_pitching", f"{game_pk}")
        ident = f"box_{game_pk}"

        entry = self.manifest.get_chunk(ident)
        final = bool(entry and entry.get("final"))
        ttl = None if final else self.cache_config.ttl_for("boxscore")
        if (
            batting_file.exists()
            and pitching_file.exists()
            and is_fresh(entry, ttl_seconds=ttl, today=self.cache_config.today, refresh=refresh)
        ):
            return (
                self._read_cached(batting_file, f"v1/game/{game_pk}/boxscore"),
                self._read_cached(pitching_file, f"v1/game/{game_pk}/boxscore"),
            )

        data = self._fetch_json(f"v1/game/{game_pk}/boxscore")
        batting_table, pitching_table = self.normalizer.normalize_boxscore(data, game_pk=game_pk)

        if self.cache_config.enabled:
            if len(batting_table) > 0:
                atomic_write_parquet(batting_table, batting_file)
            if len(pitching_table) > 0:
                atomic_write_parquet(pitching_table, pitching_file)
            self.manifest.set_completed(
                ident,
                records_count=len(batting_table) + len(pitching_table),
                metadata={"final": self._game_is_final(game_pk)},
            )

        return batting_table, pitching_table

    def extract_standings(self, season: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract and normalize league/division standings."""
        return self._extract(
            category="standings",
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
            category="teams",
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
            category="rosters",
            ident=f"roster_{team_id}",
            dataset="roster",
            endpoint=f"v1/teams/{team_id}/roster",
            params=None,
            normalize=lambda data: self.normalizer.normalize_roster(data, team_id=team_id),
            season=None,
            refresh=refresh,
        )

    def extract_transactions(self, season: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract and normalize roster transactions for a season."""
        return self._extract(
            category="transactions",
            ident=f"transactions_{season}",
            dataset="transactions",
            endpoint="v1/transactions",
            params={"season": season},
            normalize=self.normalizer.normalize_transactions,
            season=season,
            refresh=refresh,
        )

    def extract_draft(self, year: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract and normalize MLB first-year player draft."""
        return self._extract(
            category="draft",
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
            category="venues",
            ident="venues_all",
            dataset="venues",
            endpoint="v1/venues",
            params=None,
            normalize=self.normalizer.normalize_venues,
            season=None,
            refresh=refresh,
        )
