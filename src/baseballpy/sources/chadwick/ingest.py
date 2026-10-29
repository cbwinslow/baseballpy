"""Chadwick ingest: download (cached), type and store the register datasets.

This is the whole extract -> normalize -> store path with no in-memory lookup index, so an ingest job
never pays for building one. ``ChadwickRegister.load`` calls it and then builds the index.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.chadwick.extractor import ChadwickExtractor
from baseballpy.sources.chadwick.normalizer import ChadwickNormalizer

logger = logging.getLogger(__name__)

#: dataset -> (raw file it needs or ``None`` for the shards, how to type that file)
_PARSERS: dict[
    str, tuple[str | None, Callable[[ChadwickNormalizer, Mapping[str, bytes]], pa.Table]]
] = {
    "register": (None, lambda n, raw: n.normalize(dict(raw))),
    "register_names": ("names.csv", lambda n, raw: n.normalize_names(raw["names.csv"])),
    "register_links": ("links.csv", lambda n, raw: n.normalize_links(raw["links.csv"])),
    "register_countries": (
        "countries.csv",
        lambda n, raw: n.normalize_countries(raw["countries.csv"]),
    ),
}


def dataset_names() -> list[str]:
    """Names of the registered Chadwick datasets (the registry is the only list)."""
    catalog.register_all()
    return [spec.name for spec in datasets_for("chadwick")]


@dataclass
class IngestOutcome:
    """Rows per dataset, plus the tables that were typed in this call (cached ones are absent)."""

    rows: dict[str, int] = field(default_factory=dict)
    tables: dict[str, pa.Table] = field(default_factory=dict)


def ingest(
    datasets: Sequence[str] | None = None,
    *,
    refresh: bool = False,
    config: LakeConfig | None = None,
    extractor: ChadwickExtractor | None = None,
    normalizer: ChadwickNormalizer | None = None,
) -> IngestOutcome:
    """Make the selected datasets (default: all registered) current in ``processed/``.

    A dataset whose Parquet is cached and whose raw download is current is left alone (rows are read
    from the Parquet footer). Otherwise the raw files are downloaded once for the call, typed and
    stored atomically. Unknown dataset names raise ``ValueError``.
    """
    names = dataset_names()
    wanted = list(datasets) if datasets else names
    unknown = [d for d in wanted if d not in names]
    if unknown:
        raise ValueError(f"unknown dataset(s) for chadwick: {unknown}; known: {names}")
    missing_parsers = [d for d in wanted if d not in _PARSERS]
    if missing_parsers:
        raise RuntimeError(f"no parser for registered chadwick dataset(s) {missing_parsers}")

    cfg = config or LakeConfig()
    store = ProcessedStore(cfg)
    extractor = extractor or ChadwickExtractor(cache_config=cfg)
    normalizer = normalizer or ChadwickNormalizer()
    outcome = IngestOutcome()
    raw: dict[str, bytes] | None = None

    for name in wanted:
        spec = get_dataset("chadwick", name)
        if not refresh and store.is_cached(spec) and extractor.is_cache_current(False):
            outcome.rows[name] = store.row_count(spec)
            continue
        if raw is None:
            raw = extractor.extract(refresh=refresh)
        raw_file, parse = _PARSERS[name]
        if raw_file is not None and raw_file not in raw:
            logger.warning("chadwick download has no %s; dataset %s was not built", raw_file, name)
            outcome.rows[name] = 0
            continue
        table = parse(normalizer, raw)
        outcome.tables[name] = table
        outcome.rows[name] = len(table)
        if cfg.enabled and len(table) > 0:
            sha = (extractor.manifest.get_chunk("commit_sha") or {}).get("sha") or None
            store.put(spec, table, source_ref=sha)
    return outcome


__all__ = ["IngestOutcome", "dataset_names", "ingest"]
