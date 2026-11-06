"""Kalshi trades and candlesticks: one resumable chunk per market open date.

The markets come from the catalog already in the lake (data, not a list): traded markets only,
grouped by the UTC date they opened (a date that never changes in a market's life; the close date
of a season-long market can be years away), newest date first. A date is one unit of work; its
markets are fetched on worker threads under the shared client's per-host caps, typed, stored as one
Parquet chunk per dataset, and the raw answers go to one gzip file per dataset. A finished date is
left alone when its markets are all final and unchanged, so a rerun only fetches what is new.
"""

import hashlib
import logging
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pyarrow.compute as pc

from baseballpy.core.concurrency import resolve_concurrency
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore, RawStore, manifest_key
from baseballpy.sources import catalog
from baseballpy.sources.kalshi.endpoints import MARKET_DATASETS, MIN_VOLUME
from baseballpy.sources.kalshi.market_data import Clock, KalshiMarketData, MarketRow
from baseballpy.sources.kalshi.normalizer import KalshiNormalizer
from baseballpy.sources.kalshi.raw import RawLog, keep_raw

logger = logging.getLogger(__name__)

#: threads inside one date's job. The runner already runs many dates side by side and the host caps
#: bound the real request rate, so a larger pool only piles up idle threads (32 jobs of 32 threads
#: was over 700 threads for 16 requests in flight)
MAX_THREADS_PER_DAY = 8
#: a market in any other status may still trade, so its date is fetched again on every run
FINAL_STATUSES = frozenset({"finalized"})
UNDATED = "undated"
_COLUMNS = ["ticker", "status", "volume_fp", "open_time", "close_time", "settlement_ts"]


def traded_markets(store: ProcessedStore) -> list[MarketRow]:
    """Markets of the catalog with traded volume (empty before the catalog has been ingested)."""
    catalog.register_all()
    table = store.read(get_dataset("kalshi", "markets"), columns=_COLUMNS)
    traded = table.filter(pc.greater(table.column("volume_fp"), MIN_VOLUME))
    return [
        MarketRow(
            ticker=r["ticker"],
            status=r["status"],
            open_time=r["open_time"],
            close_time=r["close_time"],
            settlement_ts=r["settlement_ts"],
        )
        for r in traded.to_pylist()
    ]


def day_of(market: MarketRow) -> str:
    """The UTC open date (``YYYY-MM-DD``) a market belongs to; ``undated`` when it has no times."""
    moment = market.open_time or market.end
    return moment.astimezone(UTC).date().isoformat() if moment is not None else UNDATED


def plan_days(markets: Sequence[MarketRow]) -> list[str]:
    """The dates that have markets, newest first (``undated`` last)."""
    days = {day_of(m) for m in markets}
    return sorted(days - {UNDATED}, reverse=True) + ([UNDATED] if UNDATED in days else [])


def markets_digest(markets: Sequence[MarketRow]) -> str:
    """Fingerprint of a date's markets and their statuses (changes when a market is added or settles)."""
    text = "\n".join(f"{m.ticker}:{m.status}" for m in sorted(markets, key=lambda m: m.ticker))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class DayOutcome:
    """What one date's job did."""

    day: str
    markets: int = 0
    rows: dict[str, int] = field(default_factory=dict)
    cached: bool = False


def _is_current(
    config: LakeConfig, store: ProcessedStore, day: str, datasets: Sequence[str], digest: str
) -> bool:
    for name in datasets:
        spec = get_dataset("kalshi", name)
        entry = config.dataset_manifest("kalshi", name, "processed").get_chunk(
            manifest_key(day, None)
        )
        if entry is None or entry.get("markets_digest") != digest or not store.is_cached(spec, day):
            return False
    return True


def ingest_day(
    day: str,
    datasets: Sequence[str],
    markets: Sequence[MarketRow],
    *,
    config: LakeConfig,
    data: KalshiMarketData,
    normalizer: KalshiNormalizer,
    workers: int | None = None,
    force: bool = False,
    clock: Clock = lambda: datetime.now(UTC),
) -> DayOutcome:
    """Fetch, type and store the selected datasets of one close date (``force``: even if current)."""
    unknown = [d for d in datasets if d not in MARKET_DATASETS]
    if unknown:
        raise ValueError(f"unknown market dataset(s) {unknown}; known: {list(MARKET_DATASETS)}")
    todays = [m for m in markets if day_of(m) == day]
    outcome = DayOutcome(day=day, markets=len(todays))
    if not todays:
        return outcome
    store = ProcessedStore(config)
    digest = markets_digest(todays)
    all_final = all(m.status in FINAL_STATUSES for m in todays)
    if all_final and not force and _is_current(config, store, day, datasets, digest):
        outcome.cached = True
        for name in datasets:
            outcome.rows[name] = store.row_count(get_dataset("kalshi", name))
        return outcome

    now = clock()
    pool_size = resolve_concurrency(workers, len(todays), max_cap=MAX_THREADS_PER_DAY)
    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        for name in datasets:
            raw = RawLog()
            records = (
                _trades(pool, data, todays, raw)
                if name == "trades"
                else _candles(pool, data, todays, raw, now)
            )
            table = normalizer.normalize(name, records)
            outcome.rows[name] = table.num_rows
            if not config.enabled:
                continue
            spec = get_dataset("kalshi", name)
            keep_raw(
                RawStore(config), name, f"{name}-{day}.jsonl.gz", raw, day=day, markets=len(todays)
            )
            store.put(
                spec,
                table,
                chunk_id=day,
                metadata={"markets_digest": digest, "markets": len(todays)},
            )
    return outcome


def _trades(
    pool: ThreadPoolExecutor, data: KalshiMarketData, markets: Sequence[MarketRow], raw: RawLog
) -> list[dict[str, Any]]:
    return [t for batch in pool.map(lambda m: data.trades(m, raw), markets) for t in batch]


def _candles(
    pool: ThreadPoolExecutor,
    data: KalshiMarketData,
    markets: Sequence[MarketRow],
    raw: RawLog,
    now: datetime,
) -> list[dict[str, Any]]:
    archived = [m for m in markets if data.candle_route_is_archived(m)]
    live = sorted(
        (m for m in markets if not data.candle_route_is_archived(m)), key=lambda m: m.ticker
    )
    size = 100  # BY_NAME["candlesticks"].batch_size, the most the API takes per call
    batches = [live[i : i + size] for i in range(0, len(live), size)]
    rows: list[dict[str, Any]] = []
    for batch in pool.map(lambda m: data.candles_archived(m, raw, now), archived):
        rows.extend(batch)
    for batch in pool.map(lambda b: data.candles_live(b, raw, now), batches):
        rows.extend(batch)
    return rows


__all__ = [
    "FINAL_STATUSES",
    "UNDATED",
    "DayOutcome",
    "day_of",
    "ingest_day",
    "markets_digest",
    "plan_days",
    "traded_markets",
]
