"""Compare a small sample download with the lake (ADR 108; the rebuild check of AGENTS.md section 15).

``baseballpy verify-sample`` downloads a few chunks into a fresh scratch home and compares them with what the
real lake holds. The comparison itself (:func:`compare_lakes`) is offline and pure: it reads two lakes.

A processed chunk is identical when its rows, sorted by the registered keys, equal the lake's in every
registered column (the lineage column of segment files is ignored). A raw file is identical when its sha256
equals the lake's record. A chunk the lake never fetched is reported, but is not a difference. A provider answer
can change over time, so a difference is information to explain or fix, not always a bug.
"""

import os
import subprocess  # noqa: S404 - runs this interpreter on fixed arguments (the normal ingest)
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, LINEAGE_COLUMN, DatasetSpec
from baseballpy.core.stores import ProcessedStore

ROWS_DIFFER = "rows_differ"
RAW_DIFFERS = "raw_differs"
MISSING_IN_LAKE = "missing_in_lake"
_FAILING = frozenset({ROWS_DIFFER, RAW_DIFFERS})


@dataclass(frozen=True)
class Difference:
    """One place where the sample and the lake do not agree (or the lake has nothing to compare)."""

    kind: str
    source: str
    dataset: str
    item: str
    detail: str


@dataclass
class SampleReport:
    """What a comparison found."""

    compared: int = 0
    identical: int = 0
    missing_in_lake: int = 0
    raw_compared: int = 0
    raw_identical: int = 0
    differences: list[Difference] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """True when a chunk's rows or a raw file's bytes differ (a chunk the lake lacks does not count)."""
        return any(d.kind in _FAILING for d in self.differences)


def _split_key(key: str) -> tuple[int | None, str]:
    """``season=2023/a`` -> ``(2023, "a")``; a key without a season folder -> ``(None, key)``."""
    head, sep, tail = key.partition("/")
    if sep and head.startswith("season=") and head.removeprefix("season=").isdigit():
        return int(head.removeprefix("season=")), tail
    return None, key


def _plain(column: pa.ChunkedArray) -> pa.ChunkedArray:
    """A column by value: a dictionary (category) column is decoded, so two dictionary orders compare equal."""
    if pa.types.is_dictionary(column.type):
        return column.cast(column.type.value_type)
    return column


def _rows_differ(sample: pa.Table, lake: pa.Table, spec: DatasetSpec) -> str | None:
    """Why two chunk tables differ, or ``None`` when they are the same rows."""
    names = [n for n in sample.column_names if n != LINEAGE_COLUMN]
    if sorted(names) != sorted(n for n in lake.column_names if n != LINEAGE_COLUMN):
        return "the columns differ"
    if sample.num_rows != lake.num_rows:
        return f"{sample.num_rows} row(s) in the sample, {lake.num_rows} in the lake"
    keys = [(k, "ascending") for k in spec.keys if k in names]
    left, right = sample.select(names), lake.select(names)
    if keys:
        left, right = left.sort_by(keys), right.sort_by(keys)
    for name in names:
        if not _plain(left[name]).equals(_plain(right[name])):
            return f"column {name} differs"
    return None


def _compare_processed(
    sample: LakeConfig, lake: LakeConfig, spec: DatasetSpec, report: SampleReport
) -> None:
    if not sample.processed_dir(spec.source, spec.name).is_dir():
        return
    mine = ProcessedStore(sample)
    theirs = ProcessedStore(lake)
    lake_manifest = lake.dataset_manifest(spec.source, spec.name, "processed")
    chunks = sample.dataset_manifest(spec.source, spec.name, "processed").chunks()
    for key, entry in sorted(chunks.items()):
        if entry.get("status") != "COMPLETED":
            continue
        season, chunk = _split_key(key)
        report.compared += 1
        if lake_manifest.get_chunk(key) is None or not theirs.has_part(spec, chunk, season):
            report.missing_in_lake += 1
            report.differences.append(
                Difference(
                    MISSING_IN_LAKE,
                    spec.source,
                    spec.name,
                    key,
                    "the lake does not hold this chunk",
                )
            )
            continue
        why = _rows_differ(
            mine.read_part(spec, chunk, season), theirs.read_part(spec, chunk, season), spec
        )
        if why is None:
            report.identical += 1
        else:
            report.differences.append(Difference(ROWS_DIFFER, spec.source, spec.name, key, why))


def _raw_seasons(config: LakeConfig, spec: DatasetSpec) -> list[int | None]:
    root = config.raw_root / spec.source / spec.name
    if not root.is_dir():
        return []
    seasons: list[int | None] = [
        int(p.name.removeprefix("season="))
        for p in sorted(root.glob("season=*"))
        if p.name.removeprefix("season=").isdigit()
    ]
    return seasons or [None]


def _compare_raw(
    sample: LakeConfig, lake: LakeConfig, spec: DatasetSpec, report: SampleReport
) -> None:
    for season in _raw_seasons(sample, spec):
        mine = sample.dataset_manifest(spec.source, spec.name, "raw", season).chunks()
        theirs = lake.dataset_manifest(spec.source, spec.name, "raw", season)
        for name, entry in sorted(mine.items()):
            if not entry.get("sha256") or entry.get("stored") == "segment":
                continue
            report.raw_compared += 1
            other = theirs.get_chunk(name)
            item = f"raw {name}" if season is None else f"raw season={season}/{name}"
            if other is None or not other.get("sha256"):
                report.differences.append(
                    Difference(
                        MISSING_IN_LAKE,
                        spec.source,
                        spec.name,
                        item,
                        "the lake has no such raw file",
                    )
                )
            elif other["sha256"] == entry["sha256"]:
                report.raw_identical += 1
            else:
                report.differences.append(
                    Difference(
                        RAW_DIFFERS, spec.source, spec.name, item, "the bytes differ (sha256)"
                    )
                )


def compare_lakes(
    sample: LakeConfig, lake: LakeConfig, sources: tuple[str, ...] = ()
) -> SampleReport:
    """Compare every processed chunk and raw file of ``sample`` with the same ones of ``lake``.

    The dataset registry must be registered first (``catalog.register_all()``, done by the command).
    """
    report = SampleReport()
    for spec in DATASETS.values():
        if sources and spec.source not in sources:
            continue
        _compare_processed(sample, lake, spec, report)
        _compare_raw(sample, lake, spec, report)
    return report


def run_scratch_ingest(
    source: str,
    home: Path,
    *,
    seasons: str | None = None,
    datasets: tuple[str, ...] = (),
    limit: int | None = None,
) -> int:
    """Run the normal ingest for the sample into ``home`` (a child process; the real lake is not touched)."""
    command: list[str] = [
        sys.executable,
        "-c",
        "from baseballpy.cli import main; main()",
        "ingest",
        source,
    ]
    if seasons:
        command += ["--seasons", seasons]
    for dataset in datasets:
        command += ["--datasets", dataset]
    if limit is not None:
        command += ["--limit", str(limit)]
    command += ["--no-sync-db"]
    env: dict[str, Any] = {**os.environ, "BASEBALLPY_HOME": str(home)}
    return subprocess.run(command, env=env, check=False).returncode  # noqa: S603


__all__ = ["Difference", "SampleReport", "compare_lakes", "run_scratch_ingest"]
