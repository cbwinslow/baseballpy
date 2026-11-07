"""Polymarket price history: one resumable chunk per market start date.

The markets come from the catalog already in the lake (data, not a list): markets that traded,
grouped by the UTC date they started (a date that never changes), newest date first. A date is one
unit of work; its outcome tokens are fetched on worker threads under the shared client's per-host
caps, one request per token and window of at most 14 days, typed, and stored as one Parquet chunk.
The raw answers go to one gzip file. A date is left alone when all its markets are closed and
unchanged, so a rerun only fetches what is new.
"""

import hashlib
import logging
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pyarrow.compute as pc

from baseballpy.core.concurrency import resolve_concurrency
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.rawlog import RawLog
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.polymarket.extractor import PolymarketExtractor
from baseballpy.sources.polymarket.normalizer import PolymarketNormalizer
from baseballpy.sources.polymarket.records import epoch, price_window, windows

logger = logging.getLogger(__name__)

#: threads inside one date's job; the runner runs many dates side by side and the host caps bound
#: the real request rate, so a larger pool only piles up idle threads
MAX_THREADS_PER_DAY = 8
UNDATED = "undated"
#: markets with no traded volume have no price history; they are not fetched (see docs/sources)
MIN_VOLUME = 0.0
Clock = Callable[[], int]


@dataclass(frozen=True)
class MarketRow:
    """What the price job needs to know about one market (read from the catalog in the lake)."""

    market_id: int
    tokens: tuple[str, ...]
    start: datetime | None
    end: datetime | None
    closed: bool | None

    @property
    def day(self) -> str:
        """The UTC date the market started (``undated`` when the catalog has no start)."""
        return self.start.astimezone(UTC).date().isoformat() if self.start else UNDATED


def traded_markets(store: ProcessedStore) -> list[MarketRow]:
    """Markets of the catalog with traded volume (empty before the catalog has been ingested)."""
    catalog.register_all()
    markets = store.read(
        get_dataset("polymarket", "markets"),
        columns=[
            "id",
            "start_date",
            "created_at",
            "closed_time",
            "end_date",
            "closed",
            "volume_num",
        ],
    )
    markets = markets.filter(pc.greater(markets.column("volume_num"), MIN_VOLUME))
    tokens: dict[int, list[tuple[int, str]]] = {}
    outcomes = store.read(
        get_dataset("polymarket", "outcomes"), columns=["market_id", "outcome_index", "token_id"]
    )
    for row in outcomes.to_pylist():
        if row["token_id"]:
            tokens.setdefault(row["market_id"], []).append((row["outcome_index"], row["token_id"]))
    return [
        MarketRow(
            market_id=r["id"],
            tokens=tuple(t for _, t in sorted(tokens[r["id"]])),
            start=r["start_date"] or r["created_at"],
            end=r["closed_time"] or r["end_date"],
            closed=r["closed"],
        )
        for r in markets.to_pylist()
        if r["id"] in tokens
    ]


def plan_days(markets: Sequence[MarketRow]) -> list[str]:
    """The dates that have markets, newest first (``undated`` last)."""
    days = {m.day for m in markets}
    return sorted(days - {UNDATED}, reverse=True) + ([UNDATED] if UNDATED in days else [])


def markets_digest(markets: Sequence[MarketRow]) -> str:
    """Fingerprint of a date's markets and whether they are closed (changes when one closes)."""
    text = "\n".join(
        f"{m.market_id}:{m.closed}:{epoch(m.end)}"
        for m in sorted(markets, key=lambda m: m.market_id)
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class DayOutcome:
    """What one date's job did."""

    day: str
    markets: int = 0
    rows: dict[str, int] = field(default_factory=dict)
    cached: bool = False


def ingest_day(
    day: str,
    markets: Sequence[MarketRow],
    *,
    config: LakeConfig,
    extractor: PolymarketExtractor,
    normalizer: PolymarketNormalizer,
    workers: int | None = None,
    force: bool = False,
    clock: Clock = lambda: int(time.time()),
) -> DayOutcome:
    """Fetch, type and store the price history of one start date (``force``: even if current)."""
    todays = [m for m in markets if m.day == day]
    outcome = DayOutcome(day=day, markets=len(todays))
    if not todays:
        return outcome
    store = ProcessedStore(config)
    spec = get_dataset("polymarket", "prices")
    digest = markets_digest(todays)
    entry = config.dataset_manifest("polymarket", "prices", "processed").get_chunk(day)
    all_closed = all(m.closed for m in todays)
    if (
        all_closed
        and not force
        and entry is not None
        and entry.get("markets_digest") == digest
        and store.is_cached(spec, day)
    ):
        outcome.cached = True
        outcome.rows["prices"] = int(entry.get("records_count") or 0)
        return outcome

    now = clock()
    jobs: list[tuple[str, int, int, int]] = []  # (token, window index, start, end)
    for market in todays:
        window = price_window(market.start, market.end, market.closed, now)
        if window is None:
            continue
        for token in market.tokens:
            jobs += [(token, i, a, b) for i, (a, b) in enumerate(windows(*window))]

    raw = RawLog()
    pool_size = resolve_concurrency(workers, len(jobs), max_cap=MAX_THREADS_PER_DAY)
    with ThreadPoolExecutor(max_workers=pool_size) as pool:
        batches = pool.map(lambda j: extractor.price_history(j[0], j[2], j[3], raw, j[1]), jobs)
        # windows share their boundary second: keep one point per (token, time)
        unique = {(row["tokenId"], row["t"]): row for batch in batches for row in batch}
        records: list[dict[str, Any]] = [unique[key] for key in sorted(unique)]
    table = normalizer.normalize("prices", records)
    outcome.rows["prices"] = table.num_rows
    if config.enabled:
        extractor.keep("prices", f"prices-{day}.jsonl.gz", raw)
        store.put(
            spec,
            table,
            chunk_id=day,
            metadata={"markets_digest": digest, "markets": len(todays)},
        )
    return outcome


__all__ = [
    "UNDATED",
    "DayOutcome",
    "MarketRow",
    "ingest_day",
    "markets_digest",
    "plan_days",
    "traded_markets",
]
