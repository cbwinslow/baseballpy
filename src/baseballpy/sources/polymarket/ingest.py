"""Polymarket catalog ingest: events, markets and outcomes of the in-scope sport.

The events list (each event carries its markets) is walked once with the keyset cursor; the markets
and the two outcome tokens of each market are cut out of it. Everything is stored as one Parquet
chunk per month the event started, so a rerun overwrites exactly what it fetched. The whole catalog
is fetched again on every call: markets change while they trade.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.rawlog import RawLog
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.polymarket.endpoints import CATALOG_DATASETS
from baseballpy.sources.polymarket.extractor import PolymarketExtractor
from baseballpy.sources.polymarket.normalizer import PolymarketNormalizer
from baseballpy.sources.polymarket.records import outcome_rows, split_event

logger = logging.getLogger(__name__)

UNDATED = "undated"


def dataset_names() -> list[str]:
    """Names of the registered Polymarket datasets (the registry is the only list)."""
    catalog.register_all()
    return [spec.name for spec in datasets_for("polymarket")]


@dataclass
class IngestOutcome:
    """Rows per dataset written by one call."""

    rows: dict[str, int] = field(default_factory=dict)
    events: int = 0


def month_of(event: dict[str, Any]) -> str:
    """``YYYY-MM`` of the month an event started (its chunk name); ``undated`` without a date."""
    text = str(event.get("startDate") or event.get("creationDate") or event.get("createdAt") or "")
    return text[:7] if len(text) >= 7 and text[4] == "-" else UNDATED


def ingest(
    datasets: Sequence[str] | None = None,
    *,
    config: LakeConfig | None = None,
    extractor: PolymarketExtractor | None = None,
    normalizer: PolymarketNormalizer | None = None,
) -> IngestOutcome:
    """Make the selected catalog datasets (default: all) current in ``processed/``.

    Unknown dataset names raise ``ValueError``.
    """
    names = [n for n in dataset_names() if n in CATALOG_DATASETS]
    wanted = list(datasets) if datasets else names
    unknown = [d for d in wanted if d not in names]
    if unknown:
        raise ValueError(f"unknown dataset(s) for polymarket: {unknown}; known: {names}")

    cfg = config or LakeConfig()
    store = ProcessedStore(cfg)
    extractor = extractor or PolymarketExtractor(cache_config=cfg)
    normalizer = normalizer or PolymarketNormalizer()
    outcome = IngestOutcome()

    raw = RawLog()
    tag = extractor.sport_tag_id(raw)
    records: dict[str, dict[str, list[dict[str, Any]]]] = {
        name: defaultdict(list) for name in CATALOG_DATASETS
    }
    seen_events: set[Any] = set()
    seen_markets: set[Any] = set()
    for page in extractor.events(tag, raw):
        for event in page:
            if event["id"] in seen_events:
                continue
            seen_events.add(event["id"])
            month = month_of(event)
            plain, markets = split_event(event)
            records["events"][month].append(plain)
            for market in markets:
                if market["id"] in seen_markets:
                    continue
                seen_markets.add(market["id"])
                records["markets"][month].append(market)
                records["outcomes"][month].extend(outcome_rows(market))
    outcome.events = len(seen_events)
    extractor.keep("events", "events-all.jsonl.gz", raw)

    for name in wanted:
        total = 0
        for month, rows in sorted(records[name].items()):
            table = normalizer.normalize(name, rows)
            total += table.num_rows
            if cfg.enabled and table.num_rows:
                store.put(get_dataset("polymarket", name), table, chunk_id=month)
        outcome.rows[name] = total
    return outcome


__all__ = ["UNDATED", "IngestOutcome", "dataset_names", "ingest", "month_of"]
