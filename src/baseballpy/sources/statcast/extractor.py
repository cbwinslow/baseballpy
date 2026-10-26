"""Extractor for Baseball Savant (Statcast) pitch tracking data with date chunking and rate limits."""

import asyncio
from datetime import date, datetime, timedelta
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
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

SAVANT_BASE_URL = "https://baseballsavant.mlb.com/statcast_search/csv"


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


class StatcastExtractor:
    """Extracts pitch-level tracking data from Baseball Savant with chunking and token bucket limits."""

    def __init__(
        self,
        cache_config: CacheConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        chunk_days: int = 5,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.chunk_days = chunk_days
        rate = self.rate_limit_config.host_rates.get("baseballsavant.mlb.com", 2.5)
        self.limiter = AsyncLimiter(rate, 1.0)
        self.semaphore = asyncio.Semaphore(self.rate_limit_config.max_concurrency)
        self.normalizer = StatcastNormalizer()
        self.manifest = ManifestTracker(self.cache_config.statcast_dir / "manifest.json")

    def _get_cache_path(self, start_dt: date, end_dt: date, **filters: Any) -> Path:
        """Derive cache file path for a date chunk and filter combination."""
        filter_str = "_".join(f"{k}-{v}" for k, v in sorted(filters.items()) if v is not None)
        filename = f"{start_dt.isoformat()}_{end_dt.isoformat()}"
        if filter_str:
            filename = f"{filename}_{filter_str}"
        return self.cache_config.statcast_dir / f"{filename}.parquet"

    async def _fetch_chunk(
        self,
        client: httpx.AsyncClient,
        start_dt: date,
        end_dt: date,
        refresh: bool = False,
        **filters: Any,
    ) -> pa.Table:
        """Fetch and normalize a single date chunk with caching and rate limiting."""
        cache_path = self._get_cache_path(start_dt, end_dt, **filters)
        chunk_id = cache_path.stem

        if not refresh and cache_path.exists() and self.manifest.is_completed(chunk_id):
            return pq.read_table(cache_path)

        params: dict[str, Any] = {
            "all": "true",
            "type": "details",
            "game_date_gt": start_dt.isoformat(),
            "game_date_lt": end_dt.isoformat(),
        }
        params.update(filters)

        @retry(
            reraise=True,
            stop=stop_after_attempt(self.rate_limit_config.max_retries),
            wait=wait_exponential_jitter(initial=1.0, max=10.0),
            retry=retry_if_exception_type(
                (httpx.HTTPStatusError, httpx.ConnectTimeout, httpx.ReadTimeout)
            ),
        )
        async def _call() -> bytes:
            async with self.semaphore, self.limiter:
                resp = await client.get(SAVANT_BASE_URL, params=params)
                resp.raise_for_status()
                return resp.content

        raw_csv = await _call()
        table = self.normalizer.normalize(raw_csv)

        if self.cache_config.enabled and len(table) > 0:
            atomic_write_parquet(table, cache_path, compression="snappy")
            self.manifest.set_completed(chunk_id, records_count=len(table))

        return table

    async def extract_async(
        self,
        start_date: str | date,
        end_date: str | date,
        refresh: bool = False,
        **filters: Any,
    ) -> pa.Table:
        """Asynchronously extract and concat all date chunks for the requested range."""
        start = (
            datetime.strptime(start_date, "%Y-%m-%d").date()
            if isinstance(start_date, str)
            else start_date
        )
        end = (
            datetime.strptime(end_date, "%Y-%m-%d").date()
            if isinstance(end_date, str)
            else end_date
        )

        chunks = split_date_range(start, end, chunk_days=self.chunk_days)

        with default_audit_logger.track(
            operation="statcast_extract",
            source="statcast",
            endpoint=SAVANT_BASE_URL,
            destination=str(self.cache_config.statcast_dir),
        ) as tracker:
            limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
            async with httpx.AsyncClient(
                http2=True,
                limits=limits,
                timeout=self.rate_limit_config.timeout_seconds,
            ) as client:
                tasks = [
                    self._fetch_chunk(client, chunk_start, chunk_end, refresh=refresh, **filters)
                    for chunk_start, chunk_end in chunks
                ]
                tables = await asyncio.gather(*tasks)

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
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Running inside an active loop (e.g. Jupyter or async framework)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    lambda: asyncio.run(
                        self.extract_async(start_date, end_date, refresh=refresh, **filters)
                    )
                )
                return future.result()
        else:
            return asyncio.run(self.extract_async(start_date, end_date, refresh=refresh, **filters))
