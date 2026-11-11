"""What an ingest command would download: held vs missing season folders and a typical size.

``baseballpy ingest --dry-run`` shows this so a user knows what a command means before it runs. The
sizes are *measured* values (``typical_sizes.json``, written by ``scripts/measure_dataset_sizes.py`` from a
real lake): the median bytes of one season folder of a dataset (or the whole folder of a dataset without
seasons). A dataset that was never measured is counted as unknown, never as zero. Nothing is downloaded and
no network is needed; the datasets come from the registry, so no dataset is named here.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.core.listing import dataset_files
from baseballpy.ingest.types import Selection

PACKAGED_SIZES = Path(__file__).resolve().parent.parent / "core" / "typical_sizes.json"


@dataclass(frozen=True)
class TypicalSize:
    """The median bytes of one season folder of a dataset, and how many seasons were measured."""

    bytes_per_folder: int
    folders_measured: int


@dataclass(frozen=True)
class Estimate:
    """What a selection would download, from the registry, the lake and the measured sizes."""

    datasets: int = 0
    folders_total: int = 0
    folders_held: int = 0
    folders_missing: int = 0
    bytes_typical: int = 0
    unknown_datasets: int = 0
    unestimated_datasets: int = 0
    unresolved: tuple[str, ...] = ()
    seasons_given: bool = True
    measured_on: str = ""

    def as_dict(self) -> dict[str, object]:
        """The estimate as a plain dict (the ``--json`` summary)."""
        data = asdict(self)
        data["unresolved"] = list(self.unresolved)
        return data


def load_typical_sizes() -> tuple[Mapping[str, TypicalSize], str]:
    """``(dataset key -> TypicalSize, measured_on)`` from the packaged table; empty when it is missing."""
    try:
        raw = json.loads(PACKAGED_SIZES.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, ""
    sizes = {
        key: TypicalSize(int(v["bytes_per_folder"]), int(v["folders_measured"]))
        for key, v in raw.get("datasets", {}).items()
    }
    return sizes, str(raw.get("measured_on", ""))


def _held(config: LakeConfig, spec: DatasetSpec, season: int | None) -> bool:
    root = config.processed_dir(spec.source, spec.name, season)
    return bool(dataset_files(root, by_season=False))


def _datasets_of(selection: Selection) -> tuple[list[DatasetSpec], list[str]]:
    """The registered datasets a selection covers, and the names that are not registered datasets."""
    specs = [s for s in DATASETS.values() if s.source in selection.sources]
    if not selection.datasets:
        return [s for s in specs if s.ingest == "default"], []
    by_name = {s.name: s for s in specs}
    chosen = [by_name[n] for n in selection.datasets if n in by_name]
    return chosen, [n for n in selection.datasets if n not in by_name]


def estimate(
    selections: Iterable[Selection],
    config: LakeConfig | None = None,
    sizes: Mapping[str, TypicalSize] | None = None,
) -> Estimate:
    """The held and missing season folders of ``selections`` and a typical size for the missing ones."""
    cfg = config or LakeConfig()
    measured_on = ""
    if sizes is None:
        sizes, measured_on = load_typical_sizes()
    counts = {
        "datasets": 0,
        "total": 0,
        "held": 0,
        "missing": 0,
        "bytes": 0,
        "unknown": 0,
        "skip": 0,
    }
    unresolved: list[str] = []
    seasons_given = True
    for selection in selections:
        specs, missing_names = _datasets_of(selection)
        unresolved.extend(missing_names)
        for spec in specs:
            counts["datasets"] += 1
            if spec.partition == "season":
                if not selection.seasons:
                    counts["skip"] += 1
                    seasons_given = False
                    continue
                folders: list[int | None] = list(selection.seasons)
            else:
                folders = [None]
            missing = [f for f in folders if not _held(cfg, spec, f)]
            counts["total"] += len(folders)
            counts["held"] += len(folders) - len(missing)
            counts["missing"] += len(missing)
            size = sizes.get(spec.key)
            if size is None:
                counts["unknown"] += 1
            else:
                counts["bytes"] += size.bytes_per_folder * len(missing)
    return Estimate(
        datasets=counts["datasets"],
        folders_total=counts["total"],
        folders_held=counts["held"],
        folders_missing=counts["missing"],
        bytes_typical=counts["bytes"],
        unknown_datasets=counts["unknown"],
        unestimated_datasets=counts["skip"],
        unresolved=tuple(unresolved),
        seasons_given=seasons_given,
        measured_on=measured_on,
    )


__all__ = ["Estimate", "TypicalSize", "estimate", "load_typical_sizes"]
