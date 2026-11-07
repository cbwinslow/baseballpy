"""Compacted Parquet files: many download chunks merged into a few big files, still resumable.

A compacted file holds the rows of many chunks one after another. The file itself records where
each chunk sits (a JSON map in its Parquet footer: manifest key -> ``[first row, row count]``), so
the footer is the single source of truth and a crash can never leave a position wrong. The
manifest entry of a compacted chunk only says which file holds it (``compacted_into``, a path
relative to the dataset folder).
"""

import json
import threading
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write

INTO = "compacted_into"
CHUNK_MAP_KEY = b"baseballpy.chunks"
COMPACT_PREFIX = "compact-"
#: rows per row group (DuckDB advises 100,000 to 1,000,000; its default is 122,880)
ROW_GROUP_ROWS = 122_880


_LOCKS_GUARD = threading.Lock()
_FILE_LOCKS: dict[str, threading.RLock] = {}


def _file_lock(path: Path) -> threading.RLock:
    """One lock per compacted file: threads that refresh chunks stored in the same file rewrite
    it one at a time (two rewrites at once would lose one chunk's removal), and readers never see
    the file mid-replace."""
    with _LOCKS_GUARD:
        return _FILE_LOCKS.setdefault(str(path), threading.RLock())


def compact_file_name(index: int) -> str:
    """``compact-0001.parquet``: cannot clash with a chunk part, which is ``part-<chunk>.parquet``."""
    return f"{COMPACT_PREFIX}{index:04d}.parquet"


def is_compacted(entry: Mapping[str, Any] | None) -> bool:
    """True when a manifest entry says its rows live in a compacted file."""
    return bool(entry and entry.get(INTO))


@lru_cache(maxsize=256)
def _chunk_map(path: str, mtime_ns: int, size: int) -> dict[str, tuple[int, int]]:
    metadata = pq.read_schema(path).metadata or {}
    raw = json.loads(metadata.get(CHUNK_MAP_KEY, b"{}"))
    return {key: (int(span[0]), int(span[1])) for key, span in raw.items()}


def chunk_map(path: Path) -> dict[str, tuple[int, int]]:
    """``manifest key -> (first row, row count)`` read from a compacted file's footer.

    Kept in memory while the file is unchanged (a lookup per cached chunk would otherwise read
    the footer thousands of times).
    """
    stat = path.stat()
    return _chunk_map(str(path), stat.st_mtime_ns, stat.st_size)


def holds_chunk(dataset_dir: Path, entry: Mapping[str, Any] | None, key: str) -> bool:
    """True when the compacted file named by ``entry`` exists and still holds ``key``."""
    if entry is None or not is_compacted(entry):
        return False
    path = dataset_dir / str(entry[INTO])
    return path.exists() and key in chunk_map(path)


def read_chunk(dataset_dir: Path, entry: Mapping[str, Any], key: str) -> pa.Table:
    """Read one chunk's rows out of its compacted file (only the row groups that cover it)."""
    path = dataset_dir / str(entry[INTO])
    with _file_lock(path):
        return _read_chunk_locked(path, key)


def _read_chunk_locked(path: Path, key: str) -> pa.Table:
    first, count = chunk_map(path)[key]
    groups: list[int] = []
    group_start = 0
    lead = 0
    with pq.ParquetFile(
        path
    ) as file:  # closed before any rewrite (Windows cannot replace an open file)
        for index in range(file.metadata.num_row_groups):
            rows = file.metadata.row_group(index).num_rows
            if group_start + rows > first and group_start < first + count:
                if not groups:
                    lead = first - group_start
                groups.append(index)
            group_start += rows
        return file.read_row_groups(groups).slice(lead, count)


def write_compacted(
    path: Path,
    schema: pa.Schema,
    tables: list[tuple[str, pa.Table]],
    *,
    compression: str = "zstd",
) -> dict[str, tuple[int, int]]:
    """Write chunk tables one after another into ``path`` atomically; returns the chunk map.

    Rows are gathered into full row groups so small chunks do not make small row groups.
    """
    spans: dict[str, tuple[int, int]] = {}
    position = 0
    for key, table in tables:
        spans[key] = (position, table.num_rows)
        position += table.num_rows
    meta = {CHUNK_MAP_KEY: json.dumps({k: list(v) for k, v in spans.items()}).encode()}
    with atomic_write(path) as part:
        writer = pq.ParquetWriter(
            part,
            schema.with_metadata(meta),
            compression=compression,
            store_decimal_as_integer=True,
        )
        try:
            aligned = [t if t.schema.equals(schema) else t.cast(schema) for _, t in tables]
            everything = pa.concat_tables(aligned).replace_schema_metadata(meta)
            writer.write_table(everything, ROW_GROUP_ROWS)  # full row groups across chunk borders
        finally:
            writer.close()
        footer_rows = pq.ParquetFile(part).metadata.num_rows
        if footer_rows != position:
            raise ValueError(f"compacted footer has {footer_rows} rows, wrote {position}")
    return spans


def release_chunk(dataset_dir: Path, entry: Mapping[str, Any], key: str, schema: pa.Schema) -> None:
    """Take one chunk's rows out of its compacted file (before the chunk is rewritten).

    The file is rewritten atomically without the chunk; an emptied file is deleted.
    """
    path = dataset_dir / str(entry[INTO])
    with _file_lock(path):
        _release_locked(path, key, schema)


def _release_locked(path: Path, key: str, schema: pa.Schema) -> None:
    if not path.exists():
        return
    spans = chunk_map(path)
    if key not in spans:
        return
    whole = pq.read_table(path)
    keep: list[tuple[str, pa.Table]] = [
        (other, whole.slice(first, count))
        for other, (first, count) in spans.items()
        if other != key
    ]
    if not any(t.num_rows for _, t in keep):
        path.unlink()
        return
    write_compacted(path, schema, keep)
