"""Extractor for the SABR Lahman Baseball Database from the owner's GitHub repository.

Lahman data comes only from this repository (or from a user-supplied archive via
``LahmanSource.import_archive``). The ``chadwickbureau/baseballdatabank`` repository must
never be used: its data stops around 2023.
"""

import asyncio
from pathlib import Path

from baseballpy.core.atomic import ManifestTracker, atomic_write
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, HttpResult, get_http_client
from baseballpy.sources.lahman.schema import LahmanTable

LAHMAN_GITHUB_BASE = "https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/main/data"


class LahmanExtractor:
    """Extracts raw CSV files for the Lahman database with local caching and atomic guarantees."""

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
        self.raw_dir = self.cache_config.lahman_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestTracker(self.cache_config.lahman_dir / "manifest.json")

    def get_raw_path(self, table_name: str | LahmanTable) -> Path:
        """Return local path to raw CSV file."""
        return self.raw_dir / f"{table_name}.csv"

    def _is_cached(self, name: str, refresh: bool) -> bool:
        """A table is cached only if the file exists AND the manifest recorded its completion."""
        target = self.get_raw_path(name)
        return (
            not refresh
            and target.exists()
            and target.stat().st_size > 0
            and self.cache_config.is_fresh(self.manifest.get_chunk(name), "lahman")
        )

    def _store(self, name: str, result: HttpResult) -> bytes:
        content = result.content
        if self.cache_config.enabled:
            with atomic_write(self.get_raw_path(name)) as part_path:
                part_path.write_bytes(content)
            self.manifest.set_completed(
                name,
                records_count=content.count(b"\n"),
                etag=result.etag or "",
                metadata={"source": f"{LAHMAN_GITHUB_BASE}/{name}.csv"},
            )
        return content

    def extract_table(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> bytes:
        """Extract a single Lahman table CSV, hitting cache if available."""
        name_str = str(table_name)
        url = f"{LAHMAN_GITHUB_BASE}/{name_str}.csv"
        with default_audit_logger.track(
            operation="lahman_extract_table",
            source="lahman",
            endpoint=url,
            destination=str(self.get_raw_path(name_str)),
        ) as tracker:
            if self._is_cached(name_str, refresh):
                content = self.get_raw_path(name_str).read_bytes()
                tracker.set_cache_hit(True)
                tracker.set_records(content.count(b"\n"))
                return content

            content = self._store(name_str, self.http.get_sync(url))
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
        url = f"{LAHMAN_GITHUB_BASE}/{name_str}.csv"
        async with default_audit_logger.async_track(
            operation="lahman_extract_table_async",
            source="lahman",
            endpoint=url,
            destination=str(self.get_raw_path(name_str)),
        ) as tracker:
            if self._is_cached(name_str, refresh):
                content = self.get_raw_path(name_str).read_bytes()
                tracker.set_cache_hit(True)
                tracker.set_records(content.count(b"\n"))
                return content

            content = self._store(name_str, await self.http.get(url))
            tracker.set_cache_hit(False)
            tracker.set_records(content.count(b"\n"))
            return content

    def extract_all(self, refresh: bool = False) -> dict[str, bytes]:
        """Extract all 27 core Lahman tables."""
        return {t.value: self.extract_table(t, refresh=refresh) for t in LahmanTable}

    async def extract_all_async(self, refresh: bool = False) -> dict[str, bytes]:
        """Asynchronously extract all 27 tables with bounded concurrency."""
        semaphore = asyncio.Semaphore(self.rate_limit_config.max_concurrency)
        results: dict[str, bytes] = {}

        async def _fetch(table: LahmanTable) -> None:
            async with semaphore:
                results[table.value] = await self.extract_table_async(table, refresh=refresh)

        await asyncio.gather(*[_fetch(table) for table in LahmanTable])
        return results
