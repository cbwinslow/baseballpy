"""Baseball-Reference WAR ingest: download (recent files are reused), type and store by season.

Each file holds every season since 1871. It is typed once and stored as one Parquet chunk per
season, so ``baseballpy.read("bref.war_batting", seasons=2024)`` opens one small file. The files are
a snapshot of today's WAR (Baseball-Reference revises past seasons), so the download time is kept in
the raw manifest.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

import pyarrow as pa
import pyarrow.compute as pc

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.bref.endpoints import BY_DATASET
from baseballpy.sources.bref.extractor import BrefExtractor
from baseballpy.sources.bref.normalizer import BrefNormalizer

logger = logging.getLogger(__name__)


def dataset_names() -> list[str]:
    """Names of the registered Baseball-Reference datasets (the registry is the only list)."""
    catalog.register_all()
    return [spec.name for spec in datasets_for("bref")]


@dataclass
class IngestOutcome:
    """Rows and seasons per dataset written by one call."""

    rows: dict[str, int] = field(default_factory=dict)
    seasons: dict[str, int] = field(default_factory=dict)


def ingest(
    datasets: Sequence[str] | None = None,
    *,
    refresh: bool = False,
    config: LakeConfig | None = None,
    extractor: BrefExtractor | None = None,
    normalizer: BrefNormalizer | None = None,
) -> IngestOutcome:
    """Make the selected WAR datasets (default: both) current in ``processed/``."""
    names = dataset_names()
    wanted = list(datasets) if datasets else names
    unknown = [d for d in wanted if d not in names]
    if unknown:
        raise ValueError(f"unknown dataset(s) for bref: {unknown}; known: {names}")
    cfg = config or LakeConfig()
    store = ProcessedStore(cfg)
    extractor = extractor or BrefExtractor(cfg)
    normalizer = normalizer or BrefNormalizer()
    outcome = IngestOutcome()
    for name in wanted:
        file = BY_DATASET[name]
        table = normalizer.normalize(name, extractor.fetch(file, refresh=refresh))
        outcome.rows[name] = table.num_rows
        column = table[file.season_column]
        seasons = sorted(pc.unique(column).drop_null().to_pylist())
        outcome.seasons[name] = len(seasons)
        if not cfg.enabled:
            continue
        spec = get_dataset("bref", name)
        for season in seasons:
            part = table.filter(pc.equal(column, pa.scalar(season, column.type)))
            store.put(spec, part, chunk_id=str(season), season=int(season))
    return outcome


__all__ = ["IngestOutcome", "dataset_names", "ingest"]
