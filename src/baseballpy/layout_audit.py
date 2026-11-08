"""Layout audit: is the lake still shaped for fast reads? Offline, nothing is changed.

``baseballpy catalog layout`` looks at the files under ``processed/`` and ``raw/`` and reports what
would slow queries down or hint at damage: many small part files in one dataset folder, zero-row
files, parts whose columns differ from the registered schema, tiny row groups, compacted files that
no download record points at, folders under ``processed/`` that no registered dataset owns, and raw
text files that are not yet gzipped.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.compacted import COMPACT_PREFIX, INTO, chunk_map
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.rawfiles import is_compressible, is_packed
from baseballpy.sources import catalog

#: more part files than this in one dataset (or season) folder is worth compacting
MAX_PART_FILES = 10
#: DuckDB: row groups under 5,000 rows can make queries 5 to 10 times slower
MIN_ROW_GROUP_ROWS = 5_000


class LayoutKind(StrEnum):
    """Layout verdicts. MIXED_SCHEMA, ORPHAN_COMPACT and UNKNOWN_FOLDER fail; the rest advise."""

    TINY_FILES = "TINY_FILES"  # many small part files: run `baseballpy compact`
    EMPTY_FILES = "EMPTY_FILES"  # zero-row files of empty chunks: run `baseballpy compact`
    MIXED_SCHEMA = "MIXED_SCHEMA"  # a part's columns differ from the registered schema
    SMALL_ROW_GROUPS = "SMALL_ROW_GROUPS"  # row groups under 5,000 rows in a multi-group file
    ORPHAN_COMPACT = "ORPHAN_COMPACT"  # a compacted file no download record points at
    RAW_PLAIN = "RAW_PLAIN"  # raw text files not gzipped: run `baseballpy compress-raw`
    UNKNOWN_FOLDER = "UNKNOWN_FOLDER"  # a processed/ folder no registered dataset owns


@dataclass(frozen=True)
class LayoutFinding:
    """One layout result with the evidence behind it."""

    kind: LayoutKind
    source: str
    item: str
    evidence: str

    @property
    def fails(self) -> bool:
        """Schema mix-ups and orphan compacted files fail the check (exit code 1)."""
        return self.kind in (
            LayoutKind.MIXED_SCHEMA,
            LayoutKind.ORPHAN_COMPACT,
            LayoutKind.UNKNOWN_FOLDER,
        )


def _unknown_folder_findings(config: LakeConfig, sources: set[str]) -> list[LayoutFinding]:
    """Folders under ``processed/`` that the registry does not own: no view reads them."""
    findings: list[LayoutFinding] = []
    root = config.processed_root
    if not root.is_dir():
        return findings
    known: dict[str, set[str]] = defaultdict(set)
    for spec in DATASETS.values():
        known[spec.source].add(spec.name)
    for source_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if sources and source_dir.name not in sources:
            continue
        if source_dir.name not in known:
            findings.append(
                LayoutFinding(
                    LayoutKind.UNKNOWN_FOLDER,
                    source_dir.name,
                    f"{source_dir.name}/",
                    "no registered source has this name, so no view reads it",
                )
            )
            continue
        for dataset_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
            if dataset_dir.name not in known[source_dir.name]:
                findings.append(
                    LayoutFinding(
                        LayoutKind.UNKNOWN_FOLDER,
                        source_dir.name,
                        f"{dataset_dir.name}/",
                        "no registered dataset has this name, so no view reads it "
                        "(a renamed or removed dataset? move or delete the folder)",
                    )
                )
    return findings


def _processed_findings(config: LakeConfig, sources: set[str]) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    for spec in DATASETS.values():
        if sources and spec.source not in sources:
            continue
        root = config.processed_dir(spec.source, spec.name)
        if not root.exists():
            continue
        label = f"{spec.name}"
        by_folder: dict[Path, list[Path]] = defaultdict(list)
        for path in root.rglob("*.parquet"):
            by_folder[path.parent].append(path)
        parts = [p for files in by_folder.values() for p in files if p.name.startswith("part-")]
        crowded = {f: len(fs) for f, fs in by_folder.items() if len(fs) > MAX_PART_FILES}
        if crowded:
            total = sum(crowded.values())
            findings.append(
                LayoutFinding(
                    LayoutKind.TINY_FILES,
                    spec.source,
                    label,
                    f"{total} files in {len(crowded)} folder(s) with more than {MAX_PART_FILES}"
                    " files each; run `baseballpy compact`",
                )
            )
        empty = [p for p in parts if pq.read_metadata(p).num_rows == 0]
        if empty:
            findings.append(
                LayoutFinding(
                    LayoutKind.EMPTY_FILES,
                    spec.source,
                    label,
                    f"{len(empty)} zero-row file(s); run `baseballpy compact`",
                )
            )
        wrong = _schema_mismatches(spec.schema, [p for fs in by_folder.values() for p in fs])
        if wrong:
            findings.append(
                LayoutFinding(
                    LayoutKind.MIXED_SCHEMA,
                    spec.source,
                    label,
                    f"{len(wrong)} file(s) differ from the registered schema, first: {wrong[0]};"
                    " run `baseballpy compact` to rewrite them",
                )
            )
        findings += _row_group_findings(spec.source, label, by_folder)
        findings += _orphan_findings(config, spec.source, spec.name, root, by_folder)
    return findings


def _schema_mismatches(schema: pa.Schema, paths: list[Path]) -> list[str]:
    bad: list[str] = []
    for path in paths:
        try:
            found = pq.read_schema(path)
        except OSError as exc:
            bad.append(f"{path.name} ({exc})")
            continue
        if not found.equals(schema, check_metadata=False):
            names = set(found.names) ^ set(schema.names)
            bad.append(f"{path.name} (columns differing: {sorted(names)[:3] or 'types'})")
    return bad


def _row_group_findings(
    source: str, label: str, by_folder: dict[Path, list[Path]]
) -> list[LayoutFinding]:
    small = 0
    for files in by_folder.values():
        for path in files:
            meta = pq.read_metadata(path)
            if meta.num_row_groups > 1 and meta.num_rows / meta.num_row_groups < MIN_ROW_GROUP_ROWS:
                small += 1
    if not small:
        return []
    return [
        LayoutFinding(
            LayoutKind.SMALL_ROW_GROUPS,
            source,
            label,
            f"{small} file(s) average under {MIN_ROW_GROUP_ROWS:,} rows per row group",
        )
    ]


def _orphan_findings(
    config: LakeConfig,
    source: str,
    dataset: str,
    root: Path,
    by_folder: dict[Path, list[Path]],
) -> list[LayoutFinding]:
    compact_files = [
        p for files in by_folder.values() for p in files if p.name.startswith(COMPACT_PREFIX)
    ]
    if not compact_files:
        return []
    chunks = config.dataset_manifest(source, dataset, "processed").chunks()
    referenced = {str(e[INTO]) for e in chunks.values() if e.get(INTO)}
    findings: list[LayoutFinding] = []
    for path in compact_files:
        rel = path.relative_to(root).as_posix()
        if rel not in referenced:
            findings.append(
                LayoutFinding(
                    LayoutKind.ORPHAN_COMPACT,
                    source,
                    dataset,
                    f"{rel} is not in the download records",
                )
            )
            continue
        missing = [k for k, e in chunks.items() if e.get(INTO) == rel and k not in chunk_map(path)]
        if missing:
            findings.append(
                LayoutFinding(
                    LayoutKind.ORPHAN_COMPACT,
                    source,
                    dataset,
                    f"{rel} lacks {len(missing)} chunk(s) its records point at, first: {missing[0]}",
                )
            )
    return findings


def _raw_findings(config: LakeConfig, sources: set[str]) -> list[LayoutFinding]:
    findings: list[LayoutFinding] = []
    raw_root = config.raw_root
    if not raw_root.exists():
        return findings
    for source in sorted(config.raw_compress_sources):
        if sources and source not in sources:
            continue
        plain = 0
        for manifest_path in (raw_root / source).rglob("_manifest.json"):
            for name, entry in config.manifest_for_path(manifest_path).chunks().items():
                if (
                    entry.get("status") == "COMPLETED"
                    and "sha256" in entry
                    and not is_packed(entry)
                    and is_compressible(name)
                    and (manifest_path.parent / name).exists()
                ):
                    plain += 1
        if plain:
            findings.append(
                LayoutFinding(
                    LayoutKind.RAW_PLAIN,
                    source,
                    "raw/",
                    f"{plain:,} raw text file(s) not gzipped; run `baseballpy compress-raw`",
                )
            )
    return findings


def audit_layout(
    config: LakeConfig | None = None, sources: tuple[str, ...] = ()
) -> list[LayoutFinding]:
    """Layout findings for the lake (all sources, or only ``sources``)."""
    catalog.register_all()
    cfg = config or LakeConfig()
    wanted = set(sources)
    return (
        _unknown_folder_findings(cfg, wanted)
        + _processed_findings(cfg, wanted)
        + _raw_findings(cfg, wanted)
    )


__all__ = ["LayoutFinding", "LayoutKind", "audit_layout"]
