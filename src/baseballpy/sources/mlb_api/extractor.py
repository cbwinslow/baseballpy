"""MLB Stats API Extractor with token bucket rate limiting and atomic caching."""

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from aiolimiter import AsyncLimiter
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from baseballpy.core.atomic import ManifestTracker, atomic_write_parquet
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.sources.mlb_api.normalizer import MlbApiNormalizer

MLB_BASE_URL = "https://statsapi.mlb.com/api"


class MlbApiExtractor:
    """Extracts official MLB data from statsapi.mlb.com with rate limiting and atomic parquet caching."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        rate = self.rate_limit_config.host_rates.get("statsapi.mlb.com", 8.0)
        self.limiter = AsyncLimiter(rate, 1.0)
        self.semaphore = asyncio.Semaphore(self.rate_limit_config.max_concurrency)
        self.normalizer = MlbApiNormalizer()
        self.cache_dir = self.cache_config.mlb_api_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.cache_dir / "manifest.json")

    def _get_cache_file(self, category: str, identifier: str) -> Path:
        cat_dir = self.cache_dir / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        return cat_dir / f"{identifier}.parquet"

    def _fetch_json(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch JSON payload with retries and audit tracking."""
        url = f"{MLB_BASE_URL}/{endpoint.lstrip('/')}"
        params = params or {}

        with default_audit_logger.track(
            operation="mlb_api_fetch",
            source="mlb_api",
            endpoint=url,
        ) as tracker:

            @retry(
                reraise=True,
                stop=stop_after_attempt(self.rate_limit_config.max_retries),
                wait=wait_exponential_jitter(initial=1.0, max=10.0),
                retry=retry_if_exception_type(
                    (httpx.HTTPStatusError, httpx.ConnectTimeout, httpx.ReadTimeout)
                ),
            )
            def _call() -> dict[str, Any]:
                with httpx.Client(
                    timeout=self.rate_limit_config.timeout_seconds, follow_redirects=True
                ) as client:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    return resp.json()  # type: ignore[no-any-return]

            data = _call()
            tracker.set_cache_hit(False)
            return data

    def extract_schedule(
        self,
        season: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        refresh: bool = False,
    ) -> pa.Table:
        """Extract and normalize game schedule."""
        ident = f"schedule_{season or f'{start_date}_{end_date}'}"
        cache_file = self._get_cache_file("schedule", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        params: dict[str, Any] = {"sportId": 1}
        if season:
            params["season"] = season
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date

        data = self._fetch_json("v1/schedule", params)
        table = self.normalizer.normalize_schedule(data)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table

    def extract_boxscore(self, game_pk: int, refresh: bool = False) -> tuple[pa.Table, pa.Table]:
        """Extract and normalize game boxscore into (batting_table, pitching_table)."""
        batting_file = self._get_cache_file("boxscores_batting", f"{game_pk}")
        pitching_file = self._get_cache_file("boxscores_pitching", f"{game_pk}")
        ident = f"box_{game_pk}"

        if (
            not refresh
            and batting_file.exists()
            and pitching_file.exists()
            and self.manifest.is_completed(ident)
        ):
            return pq.read_table(batting_file), pq.read_table(pitching_file)

        data = self._fetch_json(f"v1/game/{game_pk}/boxscore")
        batting_table, pitching_table = self.normalizer.normalize_boxscore(data, game_pk=game_pk)

        if self.cache_config.enabled:
            if len(batting_table) > 0:
                atomic_write_parquet(batting_table, batting_file)
            if len(pitching_table) > 0:
                atomic_write_parquet(pitching_table, pitching_file)
            self.manifest.set_completed(
                ident, records_count=len(batting_table) + len(pitching_table)
            )

        return batting_table, pitching_table

    def extract_standings(self, season: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract and normalize league/division standings."""
        ident = f"standings_{season}"
        cache_file = self._get_cache_file("standings", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        data = self._fetch_json("v1/standings", {"leagueId": "103,104", "season": season})
        table = self.normalizer.normalize_standings(data, season=season)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table

    def extract_teams(self, refresh: bool = False) -> pa.Table:
        """Extract and normalize MLB franchises."""
        ident = "teams_mlb"
        cache_file = self._get_cache_file("teams", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        data = self._fetch_json("v1/teams", {"sportId": 1})
        table = self.normalizer.normalize_teams(data)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table

    def extract_roster(self, team_id: int, refresh: bool = False) -> pa.Table:
        """Extract and normalize team active roster."""
        ident = f"roster_{team_id}"
        cache_file = self._get_cache_file("rosters", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        data = self._fetch_json(f"v1/teams/{team_id}/roster")
        table = self.normalizer.normalize_roster(data, team_id=team_id)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table

    def extract_transactions(self, season: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract and normalize roster transactions for a season."""
        ident = f"transactions_{season}"
        cache_file = self._get_cache_file("transactions", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        data = self._fetch_json("v1/transactions", {"season": season})
        table = self.normalizer.normalize_transactions(data)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table

    def extract_draft(self, year: int = 2024, refresh: bool = False) -> pa.Table:
        """Extract and normalize MLB first-year player draft."""
        ident = f"draft_{year}"
        cache_file = self._get_cache_file("draft", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        data = self._fetch_json(f"v1/draft/{year}")
        table = self.normalizer.normalize_draft(data, year=year)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table

    def extract_venues(self, refresh: bool = False) -> pa.Table:
        """Extract and normalize official ballparks/venues."""
        ident = "venues_all"
        cache_file = self._get_cache_file("venues", ident)

        if not refresh and cache_file.exists() and self.manifest.is_completed(ident):
            return pq.read_table(cache_file)

        data = self._fetch_json("v1/venues")
        table = self.normalizer.normalize_venues(data)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_file)
            self.manifest.set_completed(ident, records_count=len(table))

        return table
