"""Extractor for the SABR Lahman Baseball Database from the owner's GitHub repository.

Lahman data comes only from this repository (or from a user-supplied archive via
``LahmanSource.import_archive``). The ``chadwickbureau/baseballdatabank`` repository must
never be used: its data stops around 2023.
"""

import asyncio
from pathlib import Path

from baseballpy.core.atomic import ManifestTracker, cleanup_stale_parts
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import (
    HttpClient,
    HttpResult,
    HttpStatusError,
    TransportError,
    get_http_client,
)
from baseballpy.core.sources_lock import get_source_ref
from baseballpy.core.stores import RawStore
from baseballpy.sources.lahman.schema import LahmanTable

#: Default (pinned) data URL; instances derive theirs from the lock / env override.
LOCAL_IMPORT = "local-import"
LAHMAN_GITHUB_BASE = f"{get_source_ref('lahman').raw_base()}/data"


class LahmanSourceError(RuntimeError):
    """The configured Lahman remote could not deliver a table (no other repository is tried)."""


class LahmanExtractor:
    """Extracts raw CSV files for the Lahman database with local caching and atomic guarantees."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or LakeConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.raw = RawStore(self.cache_config)
        self.source_ref = get_source_ref("lahman", self.cache_config.home)
        self.base_url = f"{self.source_ref.raw_base()}/data"
        # discard orphaned .part files from killed runs
        cleanup_stale_parts(self.cache_config.raw_root / "lahman")

    def manifest_for(self, table_name: str | LahmanTable) -> ManifestTracker:
        """Per-table raw manifest at ``raw/lahman/<Table>/manifest.json``."""
        return self.cache_config.dataset_manifest("lahman", str(table_name), "raw")

    def get_raw_path(self, table_name: str | LahmanTable) -> Path:
        """Return local path to raw CSV file (``raw/lahman/<Table>/<Table>.csv``)."""
        return self.cache_config.raw_dir("lahman", str(table_name)) / f"{table_name}.csv"

    def _is_cached(self, name: str, refresh: bool) -> bool:
        """A table is cached only if the file exists AND the manifest recorded its completion."""
        target = self.get_raw_path(name)
        entry = self.manifest_for(name).get_chunk(name)
        if entry is not None and entry.get("origin") == LOCAL_IMPORT:
            # user-supplied data is authoritative until the caller explicitly refreshes
            return not refresh and self.get_raw_path(name).exists()
        if entry is not None and entry.get("source_ref") not in (None, self.source_ref.ref):
            return False  # fetched at a different upstream ref: stale
        return (
            not refresh
            and target.exists()
            and target.stat().st_size > 0
            and self.cache_config.is_fresh(entry, "lahman")
        )

    def _store(self, name: str, result: HttpResult) -> bytes:
        content = result.content
        if self.cache_config.enabled:
            self.raw.put(
                "lahman",
                name,
                f"{name}.csv",
                content,
                source_ref=self.source_ref.ref,
                etag=result.etag or "",
            )
            self.manifest_for(name).set_completed(
                name,
                records_count=content.count(b"\n"),
                etag=result.etag or "",
                metadata={
                    "source": f"{self.base_url}/{name}.csv",
                    "origin": f"{self.source_ref.repo}@{self.source_ref.ref}",
                    "source_ref": self.source_ref.ref,
                },
            )
        return content

    def _hint(self, name: str, exc: Exception) -> LahmanSourceError:
        return LahmanSourceError(
            f"could not fetch Lahman table {name} from {self.source_ref.repo}@{self.source_ref.ref} "
            f"({exc}). No other repository is tried; download the release yourself and call "
            "LahmanSource.import_archive(path) or point BASEBALLPY_LAHMAN_REPO at your own fork."
        )

    def _get(self, url: str, name: str) -> HttpResult:
        try:
            return self.http.get_sync(url)
        except (HttpStatusError, TransportError) as exc:
            raise self._hint(name, exc) from exc

    def extract_table(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> bytes:
        """Extract a single Lahman table CSV, hitting cache if available."""
        name_str = str(table_name)
        url = f"{self.base_url}/{name_str}.csv"
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

            content = self._store(name_str, self._get(url, name_str))
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
        url = f"{self.base_url}/{name_str}.csv"
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

            try:
                result = await self.http.get(url)
            except (HttpStatusError, TransportError) as exc:
                raise self._hint(name_str, exc) from exc
            content = self._store(name_str, result)
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
