"""Extractor for the SABR Lahman Baseball Database from GitHub mirror."""

import asyncio
from pathlib import Path

import httpx

from baseballpy.core.atomic import ManifestTracker, atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.sources.lahman.schema import LahmanTable

LAHMAN_GITHUB_BASE = "https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/main/data"


class LahmanExtractor:
    """Extracts raw CSV files for the Lahman database with local caching and atomic guarantees."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.raw_dir = self.cache_config.lahman_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.cache_config.lahman_dir / "manifest.json")

    def get_raw_path(self, table_name: str | LahmanTable) -> Path:
        """Return local path to raw CSV file."""
        return self.raw_dir / f"{table_name}.csv"

    def extract_table(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> bytes:
        """Extract a single Lahman table CSV, hitting cache if available."""
        name_str = str(table_name)
        target_file = self.get_raw_path(name_str)
        url = f"{LAHMAN_GITHUB_BASE}/{name_str}.csv"

        with default_audit_logger.track(
            operation="lahman_extract_table",
            source="lahman",
            endpoint=url,
            destination=str(target_file),
        ) as tracker:
            if not refresh and target_file.exists():
                tracker.set_cache_hit(True)
                content = target_file.read_bytes()
                tracker.set_records(content.count(b"\n"))
                return content

            with httpx.Client(timeout=self.rate_limit_config.timeout_seconds) as client:
                resp = client.get(url)
                resp.raise_for_status()
                content = resp.content

                if self.cache_config.enabled:
                    with atomic_write(target_file) as part_path:
                        part_path.write_bytes(content)
                    self.manifest.set_completed(
                        name_str,
                        records_count=content.count(b"\n"),
                        etag=resp.headers.get("ETag", ""),
                    )

                tracker.set_cache_hit(False)
                tracker.set_records(content.count(b"\n"))
                return content

    async def extract_table_async(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> bytes:
        """Asynchronously extract a single Lahman table CSV."""
        name_str = str(table_name)
        target_file = self.get_raw_path(name_str)
        url = f"{LAHMAN_GITHUB_BASE}/{name_str}.csv"

        with default_audit_logger.track(
            operation="lahman_extract_table_async",
            source="lahman",
            endpoint=url,
            destination=str(target_file),
        ) as tracker:
            if not refresh and target_file.exists():
                tracker.set_cache_hit(True)
                content = target_file.read_bytes()
                tracker.set_records(content.count(b"\n"))
                return content

            async with httpx.AsyncClient(timeout=self.rate_limit_config.timeout_seconds) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content

                if self.cache_config.enabled:
                    with atomic_write(target_file) as part_path:
                        part_path.write_bytes(content)
                    self.manifest.set_completed(
                        name_str,
                        records_count=content.count(b"\n"),
                        etag=resp.headers.get("ETag", ""),
                    )

                tracker.set_cache_hit(False)
                tracker.set_records(content.count(b"\n"))
                return content

    def extract_all(self, refresh: bool = False) -> dict[str, bytes]:
        """Extract all 27 core Lahman tables."""
        results: dict[str, bytes] = {}
        for table in LahmanTable:
            results[table.value] = self.extract_table(table, refresh=refresh)
        return results

    async def extract_all_async(self, refresh: bool = False) -> dict[str, bytes]:
        """Asynchronously extract all 27 tables with bounded concurrency."""
        semaphore = asyncio.Semaphore(self.rate_limit_config.max_concurrency)
        results: dict[str, bytes] = {}

        async def _fetch(table: LahmanTable) -> None:
            async with semaphore:
                results[table.value] = await self.extract_table_async(table, refresh=refresh)

        tasks = [_fetch(table) for table in LahmanTable]
        await asyncio.gather(*tasks)
        return results
