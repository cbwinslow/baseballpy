"""Extractor for Baseball Savant (Statcast) pitch tracking data with chunking and truncation guard."""

import asyncio
import concurrent.futures
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import ManifestTracker, atomic_write_parquet
from baseballpy.core.audit import default_audit_logger, get_audit_logger
from baseballpy.core.config import CacheConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.lazy import lazy_singleton
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

logger = logging.getLogger(__name__)

SAVANT_BASE_URL = "https://baseballsavant.mlb.com/statcast_search/csv"
SAVANT_ROW_CAP = 25_000
#: Chunks ending within this many days of today are always revalidated (scoring corrections).
REVALIDATE_TRAILING_DAYS = 3


class TruncatedResultError(RuntimeError):
    """Raised when a single day still hits Savant's row cap (data would be silently truncated)."""


def split_date_range(
    start_date: date, end_date: date, chunk_days: int = 5
) -> list[tuple[date, date]]:
    """Split a date interval into consecutive sub-ranges of at most chunk_days."""
    if start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be after end_date ({end_date})")

    ranges: list[tuple[date, date]] = []
    current = start_date
    delta = timedelta(days=chunk_days - 1)

    while current <= end_date:
        chunk_end = min(current + delta, end_date)
        ranges.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)

    return ranges


def _to_date(value: str | date) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date() if isinstance(value, str) else value


class StatcastExtractor:
    """Extracts pitch-level tracking data from Baseball Savant with chunking and row-cap bisection."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        chunk_days: int = 5,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.chunk_days = chunk_days
        self.http = http or (
            HttpClient(self.rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.normalizer = StatcastNormalizer()
        self.manifest = ManifestTracker(self.cache_config.statcast_dir / "manifest.json")

    def _today(self) -> date:
        return self.cache_config.today or datetime.now().date()

    def _get_cache_path(self, start_dt: date, end_dt: date, **filters: Any) -> Path:
        """Derive cache file path for a date chunk with Hive-partitioning by season."""
        filter_str = "_".join(f"{k}-{v}" for k, v in sorted(filters.items()) if v is not None)
        filename = f"{start_dt.isoformat()}_{end_dt.isoformat()}"
        if filter_str:
            filename = f"{filename}_{filter_str}"

        # 1. Check legacy flat file for backward compatibility
        legacy_path = self.cache_config.statcast_dir / f"{filename}.parquet"
        if legacy_path.exists():
            return legacy_path

        # 2. Modern Hive-partitioned directory: season=YYYY/
        season_dir = self.cache_config.statcast_dir / f"season={start_dt.year}"
        season_dir.mkdir(parents=True, exist_ok=True)
        return season_dir / f"{filename}.parquet"

    def _is_chunk_fresh(
        self, chunk_id: str, cache_path: Path, start_dt: date, end_dt: date, refresh: bool
    ) -> tuple[bool, int]:
        """Return (fresh, recorded_row_count) per the freshness policy."""
        entry = self.manifest.get_chunk(chunk_id)
        if entry is None:
            return False, 0
        rows = int(entry.get("records_count", 0) or 0)
        if rows > 0 and not cache_path.exists():
            return False, rows
        if end_dt >= self._today() - timedelta(days=REVALIDATE_TRAILING_DAYS) and (
            start_dt.year >= self._today().year
        ):
            return False, rows
        fresh = self.cache_config.is_fresh(entry, "statcast", season=start_dt.year, refresh=refresh)
        return fresh, rows

    async def _fetch_window(self, start_dt: date, end_dt: date, **filters: Any) -> pa.Table:
        """Fetch a window; bisect when Savant's 25,000-row cap is reached (never truncates)."""
        params: dict[str, Any] = {
            "all": "true",
            "type": "details",
            "game_date_gt": start_dt.isoformat(),
            "game_date_lt": end_dt.isoformat(),
        }
        params.update(filters)
        result = await self.http.get(SAVANT_BASE_URL, params=params)
        table = self.normalizer.normalize(result.content)
        if len(table) < SAVANT_ROW_CAP:
            return table
        if start_dt >= end_dt:
            raise TruncatedResultError(
                f"Savant returned {len(table)} rows (the cap) for the single day {start_dt}; "
                "data would be truncated"
            )
        mid = start_dt + (end_dt - start_dt) // 2
        get_audit_logger().log(_bisect_event(start_dt, end_dt, len(table)))
        left = await self._fetch_window(start_dt, mid, **filters)
        right = await self._fetch_window(mid + timedelta(days=1), end_dt, **filters)
        return pa.concat_tables([left, right], promote_options="default")

    async def _fetch_chunk(
        self,
        start_dt: date,
        end_dt: date,
        refresh: bool = False,
        **filters: Any,
    ) -> tuple[pa.Table, bool]:
        """Fetch/normalize one date chunk; returns (table, served_from_cache)."""
        cache_path = self._get_cache_path(start_dt, end_dt, **filters)
        chunk_id = cache_path.stem

        fresh, rows = self._is_chunk_fresh(chunk_id, cache_path, start_dt, end_dt, refresh)
        if fresh and self.cache_config.enabled:
            if rows == 0:
                return pa.Table.from_batches([], schema=self.normalizer.schema), True
            return pq.read_table(cache_path), True

        table = await self._fetch_window(start_dt, end_dt, **filters)

        if self.cache_config.enabled:
            if len(table) > 0:
                atomic_write_parquet(table, cache_path, compression="snappy")
            self.manifest.set_completed(
                chunk_id, records_count=len(table), metadata={"season": start_dt.year}
            )

        return table, False

    async def extract_async(
        self,
        start_date: str | date,
        end_date: str | date,
        refresh: bool = False,
        **filters: Any,
    ) -> pa.Table:
        """Asynchronously extract and concat all date chunks for the requested range."""
        start, end = _to_date(start_date), _to_date(end_date)
        chunks = split_date_range(start, end, chunk_days=self.chunk_days)
        gate = asyncio.Semaphore(self.rate_limit_config.max_concurrency)

        async def _bounded(s: date, e: date) -> tuple[pa.Table, bool]:
            async with gate:
                return await self._fetch_chunk(s, e, refresh=refresh, **filters)

        async with default_audit_logger.async_track(
            operation="statcast_extract",
            source="statcast",
            endpoint=SAVANT_BASE_URL,
            destination=str(self.cache_config.statcast_dir),
        ) as tracker:
            results = await asyncio.gather(*[_bounded(s, e) for s, e in chunks])
            tables = [table for table, _ in results]
            tracker.set_cache_hit(bool(results) and all(hit for _, hit in results))

            if not tables:
                table = pa.Table.from_batches([], schema=self.normalizer.schema)
            else:
                table = pa.concat_tables(tables, promote_options="default")

            tracker.set_records(len(table))
            return table

    def extract(
        self,
        start_date: str | date,
        end_date: str | date,
        refresh: bool = False,
        **filters: Any,
    ) -> pa.Table:
        """Synchronously extract Statcast pitch data (safe for Jupyter/sync scripts)."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.extract_async(start_date, end_date, refresh=refresh, **filters))
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(
                    self.extract_async(start_date, end_date, refresh=refresh, **filters)
                )
            ).result()


def _bisect_event(start: date, end: date, rows: int) -> Any:
    from baseballpy.core.audit import AuditEvent

    now = datetime.now().astimezone().isoformat()
    return AuditEvent(
        timestamp_utc=now,
        operation="statcast_row_cap_bisect",
        source="statcast",
        status="RETRY",
        records_count=rows,
        endpoint=SAVANT_BASE_URL,
        destination=f"{start.isoformat()}..{end.isoformat()}",
        error="row_cap_bisect",
    )


get_default_extractor = lazy_singleton(StatcastExtractor)


def statcast_search(
    start_date: str | date,
    end_date: str | date,
    refresh: bool = False,
    **filters: Any,
) -> pa.Table:
    """Synchronously extract Statcast pitch data (safe for Jupyter and scripts)."""
    return get_default_extractor().extract(
        start_date=start_date, end_date=end_date, refresh=refresh, **filters
    )
