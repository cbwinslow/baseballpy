"""Kalshi catalog ingest: series, then events and markets per series, in parallel threads.

The series list is fetched first; every in-scope series is then one unit of work (its events, its
live markets and its archived markets) run on worker threads. Requests are limited per host by the
shared ``HttpClient`` (rate and in-flight caps), so the worker count only decides how many answers
are being waited for; it never raises the request rate. Each series is stored as its own chunk, so
a rerun overwrites exactly what changed and nothing else.
"""

import logging
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import pyarrow as pa

from baseballpy.core.concurrency import resolve_concurrency
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.kalshi.endpoints import (
    CATALOG_DATASETS,
    DATASET_KEYS,
    ENDPOINTS,
    KalshiEndpoint,
)
from baseballpy.sources.kalshi.extractor import KalshiExtractor
from baseballpy.sources.kalshi.normalizer import KalshiNormalizer
from baseballpy.sources.kalshi.raw import RawLog

logger = logging.getLogger(__name__)

#: ``series`` is one table fetched once; the other datasets fan out per series
_PER_SERIES = tuple(e for e in ENDPOINTS if e.fan_out == "series")


def dataset_names() -> list[str]:
    """Names of the registered Kalshi datasets (the registry is the only list)."""
    catalog.register_all()
    return [spec.name for spec in datasets_for("kalshi")]


@dataclass
class IngestOutcome:
    """Rows per dataset written by one call."""

    rows: dict[str, int] = field(default_factory=dict)
    series: int = 0


def _newest_per_key(records: list[dict[str, Any]], key: tuple[str, ...]) -> list[dict[str, Any]]:
    """One record per key; when a market is in both the live and the archived list, the newer wins."""
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in records:
        k = tuple(record.get(c) for c in key)
        held = best.get(k)
        if held is None or str(record.get("updated_time") or "") >= str(
            held.get("updated_time") or ""
        ):
            best[k] = record
    return list(best.values())


def _series_records(
    extractor: KalshiExtractor, ticker: str, routes: Sequence[KalshiEndpoint]
) -> dict[str, list[dict[str, Any]]]:
    """Records of every wanted route for one series, grouped by dataset; raw kept per dataset."""
    by_dataset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    logs: dict[str, RawLog] = defaultdict(RawLog)
    for endpoint in routes:
        by_dataset[endpoint.dataset].extend(
            extractor.records(endpoint, ticker, logs[endpoint.dataset])
        )
    for dataset, log in logs.items():
        extractor.keep(dataset, f"{dataset}-{ticker}.jsonl.gz", log)
    return by_dataset


def ingest(
    datasets: Sequence[str] | None = None,
    *,
    config: LakeConfig | None = None,
    extractor: KalshiExtractor | None = None,
    normalizer: KalshiNormalizer | None = None,
    workers: int | None = None,
) -> IngestOutcome:
    """Make the selected catalog datasets (default: all) current in ``processed/``.

    Unknown dataset names raise ``ValueError``. The catalog is small and its markets change while
    they trade, so every call fetches it again.
    """
    names = [n for n in dataset_names() if n in CATALOG_DATASETS]
    wanted = list(datasets) if datasets else names
    unknown = [d for d in wanted if d not in names]
    if unknown:
        raise ValueError(f"unknown dataset(s) for kalshi: {unknown}; known: {names}")

    cfg = config or LakeConfig()
    store = ProcessedStore(cfg)
    extractor = extractor or KalshiExtractor(cache_config=cfg)
    normalizer = normalizer or KalshiNormalizer()
    outcome = IngestOutcome()

    series = extractor.series()
    outcome.series = len(series)
    table = normalizer.normalize("series", series)
    outcome.rows["series"] = table.num_rows
    if "series" in wanted and cfg.enabled and table.num_rows:
        store.put(get_dataset("kalshi", "series"), table)

    routes = [e for e in _PER_SERIES if e.dataset in wanted]
    if not routes:
        return outcome
    tickers = sorted(str(s["ticker"]) for s in series)

    def one(ticker: str) -> tuple[str, dict[str, pa.Table]]:
        records = _series_records(extractor, ticker, routes)
        return ticker, {
            dataset: normalizer.normalize(dataset, _newest_per_key(rows, DATASET_KEYS[dataset]))
            for dataset, rows in records.items()
        }

    with ThreadPoolExecutor(max_workers=resolve_concurrency(workers, len(tickers))) as pool:
        for ticker, tables in pool.map(one, tickers):
            for dataset, part in tables.items():
                outcome.rows[dataset] = outcome.rows.get(dataset, 0) + part.num_rows
                if cfg.enabled and part.num_rows:
                    store.put(get_dataset("kalshi", dataset), part, chunk_id=ticker)
    return outcome


__all__ = ["IngestOutcome", "dataset_names", "ingest"]
