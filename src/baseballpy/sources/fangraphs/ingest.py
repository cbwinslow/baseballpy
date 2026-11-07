"""FanGraphs ingest: type the files in ``inbox/fangraphs/`` and store them (no network).

The user supplies the files (``scripts/export_homelab_fangraphs.py`` copies the tables already held
in the homelab database; a member's own export can be dropped in the same folder). Each file is kept
as raw bytes with its sha256, typed, and stored as one Parquet chunk. A file whose bytes are
unchanged since the last ingest is left alone, so a rerun costs nothing.
"""

import gzip
import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for, get_dataset
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.sources import catalog
from baseballpy.sources.fangraphs.files import BY_DATASET, FangraphsFile
from baseballpy.sources.fangraphs.normalizer import FangraphsNormalizer

logger = logging.getLogger(__name__)


def dataset_names() -> list[str]:
    """Names of the registered FanGraphs datasets (the registry is the only list)."""
    catalog.register_all()
    return [spec.name for spec in datasets_for("fangraphs")]


@dataclass
class IngestOutcome:
    """Rows per dataset typed in this call, and the datasets left alone or without a file."""

    rows: dict[str, int] = field(default_factory=dict)
    unchanged: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)


def find_file(inbox: Path, file: FangraphsFile) -> Path | None:
    """The inbox file of a dataset (``<dataset>.csv`` or ``.csv.gz``), if the user supplied one."""
    return next((inbox / n for n in file.names if (inbox / n).is_file()), None)


def ingest(
    datasets: Sequence[str] | None = None,
    *,
    refresh: bool = False,
    config: LakeConfig | None = None,
    normalizer: FangraphsNormalizer | None = None,
) -> IngestOutcome:
    """Make the selected datasets (default: all with a file in the inbox) current in ``processed/``.

    Unknown dataset names raise ``ValueError``; a dataset asked for by name without a file raises
    ``FileNotFoundError`` that says where to put it.
    """
    names = dataset_names()
    explicit = bool(datasets)
    wanted = list(datasets) if datasets else names
    unknown = [d for d in wanted if d not in names]
    if unknown:
        raise ValueError(f"unknown dataset(s) for fangraphs: {unknown}; known: {names}")
    cfg = config or LakeConfig()
    inbox = cfg.inbox_dir("fangraphs")
    store, raw_store = ProcessedStore(cfg), RawStore(cfg)
    normalizer = normalizer or FangraphsNormalizer()
    outcome = IngestOutcome()
    for name in wanted:
        file = BY_DATASET[name]
        path = find_file(inbox, file)
        if path is None:
            if explicit:
                raise FileNotFoundError(
                    f"no file for fangraphs.{name}: put {file.names[0]} in {inbox} "
                    "(scripts/export_homelab_fangraphs.py copies it from the homelab database)"
                )
            outcome.missing.append(name)
            continue
        data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        spec = get_dataset("fangraphs", name)
        entry = cfg.dataset_manifest("fangraphs", name, "raw").get_chunk(f"{name}.csv")
        if not refresh and entry and entry.get("sha256") == digest and store.is_cached(spec):
            outcome.unchanged.append(name)
            outcome.rows[name] = store.row_count(spec)
            continue
        table = normalizer.normalize(name, data)
        outcome.rows[name] = table.num_rows
        if cfg.enabled:
            raw_store.put("fangraphs", name, f"{name}.csv", data, source_ref=path.name)
            store.put(spec, table, source_ref=path.name)
    return outcome


__all__ = ["IngestOutcome", "dataset_names", "find_file", "ingest"]
