"""Merge the small download chunks of a dataset into a few big Parquet files.

Why: 13,000 files of 1 to 20 KB per MLB dataset make ``db sync`` and every query slow; DuckDB
advises files of 100 MB to 10 GB and row groups of 100,000 to 1,000,000 rows.

How: per dataset and season the rows of every chunk are written one after another into
``compact-NNNN.parquet`` files (see :mod:`baseballpy.core.compacted`), each new file is read back
and compared chunk by chunk with its source, and only then do the manifest entries point at it
and the small files go. Chunks stay known to the manifest, so a rerun of an ingest still treats
them as downloaded, and a chunk that is downloaded again is taken out of its compacted file.

Run it when no ingest is running.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.compacted import (
    COMPACT_PREFIX,
    INTO,
    compact_file_name,
    holds_chunk,
    read_chunk,
    write_compacted,
)
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.evolve import migrate_dataset
from baseballpy.core.stores import ProcessedStore, part_filename, schema_matches

logger = logging.getLogger(__name__)

#: input bytes (compressed) per compacted file. A batch is held in memory several times over (read,
#: joined, read back, compared) and wide tables (611 columns, mostly empty) grow about 28 times from
#: their compressed size: 400 MB of inputs took 11 GB per dataset and, two at once, 22 GB of the
#: machine's committed memory (2026-11-08). 64 MB keeps a batch near 1.5 GB.
TARGET_BYTES = 64 * 1024 * 1024


@dataclass
class CompactReport:
    """What one dataset's compaction did (or would do)."""

    dataset: str
    groups: int = 0
    chunks: int = 0
    rows: int = 0
    files_before: int = 0
    files_after: int = 0
    empty_files: int = 0
    migrated_files: int = 0  # files rewritten to the registered schema (ADR 87)
    migrate_failed: int = 0
    bytes_before: int = 0
    bytes_after: int = 0


def _decoded(table: pa.Table) -> pa.Table:
    """Category (dictionary) columns as plain values: each chunk has its own dictionary, so only
    the values, not the dictionaries, can be compared."""
    for index, field in enumerate(table.schema):
        if pa.types.is_dictionary(field.type):
            table = table.set_column(
                index, field.name, table[field.name].cast(field.type.value_type)
            )
    return table


def _group_key(key: str) -> int | None:
    return int(key.split("/", 1)[0].removeprefix("season=")) if key.startswith("season=") else None


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _read_file(path: Path) -> pa.Table:
    """All rows of one Parquet file. ``ParquetFile.read`` is twice as fast as ``pq.read_table``
    on a single file (24 ms against 50 ms for a 611-column part), and a season has tens of thousands."""
    with pq.ParquetFile(path) as handle:
        return handle.read()


def _read_source(
    store: ProcessedStore, spec: DatasetSpec, key: str, season: int | None
) -> pa.Table:
    name = key.split("/", 1)[1] if season is not None else key
    path = store.config.processed_dir(spec.source, spec.name, season)
    part = path / _part_name(spec, name, season)
    if part.exists():
        return _read_file(part)
    manifest = store.config.dataset_manifest(spec.source, spec.name, "processed")
    entry = manifest.get_chunk(key) or {}
    return read_chunk(store.config.processed_dir(spec.source, spec.name), entry, key)


def _part_name(spec: DatasetSpec, name: str, season: int | None) -> str:
    return part_filename(spec.name, name, season)


def _cleanup(root: Path, chunks: dict[str, dict[str, Any]]) -> int:
    """Delete leftovers of an interrupted run: parts already inside a compacted file and
    compacted files no manifest entry points at. Returns the number of files removed."""
    removed = 0
    referenced = {str(e[INTO]) for e in chunks.values() if e.get(INTO)}
    for path in root.rglob(f"{COMPACT_PREFIX}*.parquet"):
        if _rel(root, path) not in referenced:
            path.unlink()
            removed += 1
    return removed


def _compact_group(
    store: ProcessedStore,
    spec: DatasetSpec,
    season: int | None,
    keys: list[str],
    *,
    dry_run: bool,
    target_bytes: int,
    report: CompactReport,
) -> None:
    config = store.config
    root = config.processed_dir(spec.source, spec.name)
    folder = config.processed_dir(spec.source, spec.name, season)
    manifest = config.dataset_manifest(spec.source, spec.name, "processed")
    entries = manifest.chunks()

    sources: list[tuple[str, int]] = []  # (key, estimated bytes)
    parts: list[Path] = []
    old_compact: set[str] = set()
    for key in sorted(keys):
        entry = entries[key]
        name = key.split("/", 1)[1] if season is not None else key
        part = folder / _part_name(spec, name, season)
        if part.exists():
            sources.append((key, part.stat().st_size))
            parts.append(part)
        elif holds_chunk(root, entry, key):
            file = root / str(entry[INTO])
            rows_in_file = max(1, pq.ParquetFile(file).metadata.num_rows)
            sources.append((key, file.stat().st_size * int(entry["records_count"]) // rows_in_file))
            old_compact.add(str(entry[INTO]))
    if len(sources) < 2 or not parts:
        return  # nothing small to merge

    batches: list[list[str]] = [[]]
    size = 0
    for key, nbytes in sources:
        if batches[-1] and size + nbytes > target_bytes:
            batches.append([])
            size = 0
        batches[-1].append(key)
        size += nbytes

    report.groups += 1
    report.chunks += len(sources)
    report.files_before += len(parts) + len(old_compact)
    report.bytes_before += sum(p.stat().st_size for p in parts) + sum(
        (root / rel).stat().st_size for rel in old_compact
    )
    report.files_after += len(batches)
    if dry_run:
        return

    indices = [
        int(p.stem.removeprefix(COMPACT_PREFIX))
        for p in folder.glob(f"{COMPACT_PREFIX}*.parquet")
        if p.stem.removeprefix(COMPACT_PREFIX).isdigit()
    ]
    next_index = max(indices, default=0) + 1
    written: list[tuple[Path, list[str]]] = []
    try:
        for offset, batch in enumerate(batches):
            path = folder / compact_file_name(next_index + offset)
            tables = [(key, _read_source(store, spec, key, season)) for key in batch]
            spans = write_compacted(path, spec.schema, tables)
            written.append((path, batch))  # so a failed check below removes it too
            back = _read_file(path)
            for key, source in tables:
                first, count = spans[key]
                expected = source if source.schema.equals(spec.schema) else source.cast(spec.schema)
                if count != int(entries[key]["records_count"]) or not _decoded(
                    back.slice(first, count)
                ).equals(_decoded(expected), check_metadata=False):
                    raise ValueError(f"{spec.key}: chunk {key} differs after compaction")
            report.rows += back.num_rows
            report.bytes_after += path.stat().st_size
    except Exception:
        for path, _ in written:
            path.unlink(missing_ok=True)
        raise

    # every new file is verified: now point the manifest at them (one save)
    manifest.put_entries(
        {key: {**entries[key], INTO: _rel(root, path)} for path, batch in written for key in batch}
    )
    for part in parts:
        part.unlink()
    still = {str(e[INTO]) for e in manifest.chunks().values() if e.get(INTO)}
    for rel in old_compact - still:
        (root / rel).unlink(missing_ok=True)


def _drop_empty_parts(
    spec: DatasetSpec,
    config: LakeConfig,
    chunks: dict[str, dict[str, Any]],
    report: CompactReport,
    *,
    dry_run: bool,
) -> None:
    """Delete zero-row part files of chunks recorded as downloaded and empty.

    The manifest already says "COMPLETED, 0 rows", which counts as stored without a file.
    A file is removed only when its own footer also says 0 rows.
    """
    for key, entry in chunks.items():
        if entry.get("status") != "COMPLETED" or entry.get("records_count") != 0:
            continue
        season = _group_key(key)
        name = key.split("/", 1)[1] if season is not None else key
        part = config.processed_dir(spec.source, spec.name, season) / _part_name(spec, name, season)
        if part.exists() and pq.read_metadata(part).num_rows == 0:
            report.empty_files += 1
            if not dry_run:
                part.unlink()


def compact_dataset(
    spec: DatasetSpec,
    config: LakeConfig | None = None,
    *,
    dry_run: bool = False,
    target_bytes: int = TARGET_BYTES,
    migrate: bool = True,
) -> CompactReport:
    """Compact one dataset (every season with at least two chunks and a small file to merge).

    Files written under an older schema are rewritten to the registered one first (ADR 87)."""
    cfg = config or LakeConfig()
    store = ProcessedStore(cfg)
    report = CompactReport(spec.key)
    root = cfg.processed_dir(spec.source, spec.name)
    if not root.exists():
        return report
    manifest = cfg.dataset_manifest(spec.source, spec.name, "processed")
    if not dry_run:
        _cleanup(root, manifest.chunks())
    _drop_empty_parts(spec, cfg, manifest.chunks(), report, dry_run=dry_run)
    # files from before the schema gained columns first: only then do their chunks match the spec
    if migrate:
        migrated = migrate_dataset(spec, cfg, dry_run=dry_run)
        report.migrated_files = migrated.files_rewritten
        report.migrate_failed = len(migrated.failed)
    groups: dict[int | None, list[str]] = {}
    for key, entry in manifest.chunks().items():
        if (
            entry.get("status") == "COMPLETED"
            and int(entry.get("records_count") or 0) > 0
            and schema_matches(spec, entry)
            and "/" not in (key.split("/", 1)[1] if key.startswith("season=") else key)
        ):
            groups.setdefault(_group_key(key), []).append(key)
    for season, keys in sorted(groups.items(), key=lambda kv: (kv[0] is None, kv[0] or 0)):
        _compact_group(
            store, spec, season, keys, dry_run=dry_run, target_bytes=target_bytes, report=report
        )
    return report


def compact_all(
    specs: Iterable[DatasetSpec],
    config: LakeConfig | None = None,
    *,
    dry_run: bool = False,
) -> list[CompactReport]:
    """Compact every dataset in ``specs``; datasets with nothing to merge report zeros."""
    return [compact_dataset(spec, config, dry_run=dry_run) for spec in specs]


__all__ = ["TARGET_BYTES", "CompactReport", "compact_all", "compact_dataset"]
