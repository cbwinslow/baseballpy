"""CSV sink: typed round trip through a schema sidecar, atomic writes, honest errors."""

import datetime as dt
import json
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.sinks.csv import CsvSink, read_csv_typed, sidecar_path


def _every_type() -> pa.Table:
    return pa.table(
        {
            "s": pa.array(
                ["plain", "with,comma", 'with "quote"', "multi\nline", "ünïcode ⚾", None]
            ),
            "i8": pa.array([1, -2, None, 4, 5, 6], pa.int8()),
            "i16": pa.array([1, 2, 3, None, 5, 6], pa.int16()),
            "i32": pa.array([1, 2, 3, 4, None, 6], pa.int32()),
            "i64": pa.array([2**40, 2, 3, 4, 5, None], pa.int64()),
            "f32": pa.array([0.1, 1.5, None, 3.3333333, 1e-7, 123456.79], pa.float32()),
            "f64": pa.array([0.1, 1.5, None, 3.3333333333333335, 1e-300, 1e300], pa.float64()),
            "b": pa.array([True, False, None, True, False, True], pa.bool_()),
            "d": pa.array(
                [dt.date(2024, 4, 1), None, dt.date(1871, 5, 4)] + [dt.date(2000, 2, 29)] * 3,
                pa.date32(),
            ),
            "ts": pa.array(
                [dt.datetime(2024, 4, 1, 12, 0, 0, 123456, tzinfo=dt.UTC), None]
                + [dt.datetime(2020, 1, 1, tzinfo=dt.UTC)] * 4,
                pa.timestamp("us", "UTC"),
            ),
            "dict": pa.array(["a", "b", "a", None, "b", "a"])
            .dictionary_encode()
            .cast(pa.dictionary(pa.int8(), pa.string())),
        }
    )


def test_every_registry_column_type_round_trips_exactly(tmp_path: Path) -> None:
    table = _every_type()
    path = tmp_path / "t.csv"
    assert CsvSink().write(table, str(path)) == 6
    back = read_csv_typed(path)
    assert back.schema.equals(table.schema) and back.equals(table)


def test_sidecar_describes_each_column_and_names_the_csv(tmp_path: Path) -> None:
    path = tmp_path / "register.csv"
    CsvSink().write(_every_type(), str(path))
    assert sidecar_path(path) == tmp_path / "register.schema.json"
    info = json.loads(sidecar_path(path).read_text(encoding="utf-8"))
    columns = {c["name"]: c for c in info["columns"]}
    assert columns["i16"]["type"] == "int16" and columns["ts"]["type"] == "timestamp[us, tz=UTC]"
    assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(f'"{n}"' for n in columns)


def test_an_empty_table_still_writes_header_and_schema(tmp_path: Path) -> None:
    empty = _every_type().slice(0, 0)
    path = tmp_path / "e.csv"
    assert CsvSink().write(empty, str(path)) == 0
    assert read_csv_typed(path).schema.equals(empty.schema)


def test_stream_writes_the_same_file_as_a_table(tmp_path: Path) -> None:
    table = _every_type()
    CsvSink().write(table, str(tmp_path / "a.csv"))
    reader = pa.RecordBatchReader.from_batches(table.schema, table.to_batches(max_chunksize=2))
    assert CsvSink().write_stream(reader, str(tmp_path / "b.csv")) == 6
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    assert read_csv_typed(tmp_path / "b.csv").equals(table)


def test_nested_columns_are_refused_with_a_clear_message(tmp_path: Path) -> None:
    nested = pa.table({"ok": [1], "tags": pa.array([["a", "b"]], pa.list_(pa.string()))})
    with pytest.raises(ValueError, match=r"nested column.*tags.*parquet"):
        CsvSink().write(nested, str(tmp_path / "n.csv"))
    assert not (tmp_path / "n.csv").exists()  # nothing half-written


def test_a_failed_write_leaves_no_part_file_and_keeps_the_old_file(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    CsvSink().write(pa.table({"a": [1]}), str(path))
    nested = pa.table({"tags": pa.array([["a"]], pa.list_(pa.string()))})
    with pytest.raises(ValueError):
        CsvSink().write(nested, str(path))
    assert read_csv_typed(path).to_pylist() == [{"a": 1}]
    assert not list(tmp_path.glob("*.part"))


def test_reading_without_or_with_a_mismatched_sidecar_fails_loudly(tmp_path: Path) -> None:
    path = tmp_path / "t.csv"
    CsvSink().write(pa.table({"a": [1], "b": ["x"]}), str(path))
    path.write_text("a,c\n1,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        read_csv_typed(path)
    sidecar_path(path).unlink()
    with pytest.raises(FileNotFoundError, match="schema"):
        read_csv_typed(path)


def test_empty_string_cells_read_back_as_null(tmp_path: Path) -> None:
    # the project rule (also used on import): an empty cell is NULL
    path = tmp_path / "t.csv"
    CsvSink().write(pa.table({"a": ["x", ""]}), str(path))
    assert read_csv_typed(path)["a"].to_pylist() == ["x", None]
