"""A schema that gained columns must not stop old compacted files from being rewritten."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.compacted import align_to_schema, chunk_map, write_compacted

NEW = pa.schema([("id", pa.int64()), ("name", pa.string()), ("name_slug", pa.string())])
OLD = pa.schema([("id", pa.int64()), ("name", pa.string())])


def test_old_rows_get_empty_new_columns() -> None:
    old = pa.table({"id": [1, 2], "name": ["a", "b"]}, schema=OLD)
    aligned = align_to_schema(old, NEW)
    assert aligned.schema.equals(NEW)
    assert aligned.column("name").to_pylist() == ["a", "b"]
    assert aligned.column("name_slug").to_pylist() == [None, None]


def test_a_column_the_schema_lacks_is_refused_not_dropped() -> None:
    wider = pa.table({"id": [1], "name": ["a"], "name_slug": ["a"], "extra": ["x"]})
    with pytest.raises(ValueError, match="extra"):
        align_to_schema(wider, NEW)


def test_old_and_new_chunks_are_written_into_one_file(tmp_path: Path) -> None:
    old = pa.table({"id": [1], "name": ["a"]}, schema=OLD)
    new = pa.table({"id": [2], "name": ["b"], "name_slug": ["b"]}, schema=NEW)
    path = tmp_path / "compact-0001.parquet"
    write_compacted(path, NEW, [("old", old), ("new", new)])
    stored = pq.read_table(path)
    assert stored.column("id").to_pylist() == [1, 2]
    assert stored.column("name_slug").to_pylist() == [None, "b"]
    assert chunk_map(path) == {"old": (0, 1), "new": (1, 1)}
