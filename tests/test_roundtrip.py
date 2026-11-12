"""The round-trip check (change data-validation-roundtrip, tasks 1.1 and 1.2). Written first.

The interface these tests fix (``baseballpy.core.roundtrip``):

* ``roundtrip_dataset(config, spec, *, sample_files=3) -> DatasetCheck`` reads raw CSV files of the dataset (plain or
  gzipped, header row), keeps each cell as text, finds each row in the processed Parquet (by the registered key
  columns, else by position when one raw file made one processed file) and compares every cell.
* ``DatasetCheck``: ``status`` (``ok``, ``loss`` or ``skipped``), ``reason`` (why skipped), ``raw_rows``,
  ``compared``, ``losses`` (a list of ``Loss(kind, column, count, example)``) and ``quarantined`` (quarantine rows
  of the dataset). Loss kinds: ``changed_cell`` (a stored value differs from the raw text: a 32-bit float, a dropped
  leading zero), ``lost_to_null`` (a non-empty raw cell is NULL), ``row_missing`` (a raw row is not in the processed
  data), ``unmapped_raw_column`` (a raw column no schema column reads).
* A float column is compared by value as a 64-bit float; an integer column by its text (so a dropped leading zero is
  caught), a date by its format, text exactly.
"""

import gzip
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.core.roundtrip import roundtrip_dataset
from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.core.stores import ProcessedStore, RawStore

SOURCE = "rt_fake"
RAW = (
    b"id,speed,npb,day,note,extra\n"
    b"1,85.8,01405134,20240301,a,x\n"
    b"2,94.25,00000012,20240302,b,y\n"
    b"3,,7,20240303,,z\n"
)


def _spec(
    monkeypatch: pytest.MonkeyPatch,
    columns: list[tuple[str, str]],
    name: str = "ds",
    keys: tuple[str, ...] = ("id",),
) -> DatasetSpec:
    schema = schema_from_columns(columns)
    spec = DatasetSpec(
        source=SOURCE,
        name=name,
        view=f"{SOURCE}_{name}",
        schema=schema,
        partition="none",
        keys=keys,
        description="fake",
        endpoint_doc="x",
    )
    monkeypatch.setitem(DATASETS, spec.key, spec)
    return spec


def _lake(
    tmp_path: Path, spec: DatasetSpec, raw: bytes, table: pa.Table, gz: bool = False
) -> LakeConfig:
    config = LakeConfig(home=tmp_path)
    RawStore(config).put(
        SOURCE, spec.name, "file.csv" + (".gz" if gz else ""), gzip.compress(raw) if gz else raw
    )
    ProcessedStore(config).put(spec, table)
    return config


GOOD_COLUMNS = [
    ("id", "int32"),
    ("speed", "float64"),
    ("npb", "string"),
    ("day", "date32:%Y%m%d"),
    ("note", "string"),
]


def _good_table(
    spec: DatasetSpec, npb: tuple[object, object, object] = ("01405134", "00000012", "7")
) -> pa.Table:
    return pa.Table.from_pylist(
        [
            {
                "id": 1,
                "speed": 85.8,
                "npb": npb[0],
                "day": _d(2024, 3, 1),
                "note": "a",
                "_extras": '{"extra": "x"}',
            },
            {
                "id": 2,
                "speed": 94.25,
                "npb": npb[1],
                "day": _d(2024, 3, 2),
                "note": "b",
                "_extras": '{"extra": "y"}',
            },
            {
                "id": 3,
                "speed": None,
                "npb": npb[2],
                "day": _d(2024, 3, 3),
                "note": None,
                "_extras": '{"extra": "z"}',
            },
        ],
        schema=spec.schema,
    )


def _d(y: int, m: int, d: int):  # type: ignore[no-untyped-def]
    import datetime

    return datetime.date(y, m, d)


def test_equal_cells_pass_and_the_extra_column_is_accounted_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(monkeypatch, GOOD_COLUMNS)
    check = roundtrip_dataset(_lake(tmp_path, spec, RAW, _good_table(spec)), spec)
    assert check.status == "ok", check
    assert check.raw_rows == 3 and check.compared == 3 and not check.losses
    # the raw column `extra` is read by no column, but `_extras` holds it: not a loss
    gz = roundtrip_dataset(_lake(tmp_path / "gz", spec, RAW, _good_table(spec), gz=True), spec)
    assert gz.status == "ok", "a gzipped raw file is read the same way"


def test_a_32_bit_float_is_a_changed_cell(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    columns = [("speed", "float32") if c[0] == "speed" else c for c in GOOD_COLUMNS]
    spec = _spec(monkeypatch, columns)
    table = _good_table(spec).set_column(1, "speed", pa.array([85.8, 94.25, None], pa.float32()))
    check = roundtrip_dataset(_lake(tmp_path, spec, RAW, table), spec)
    assert check.status == "loss"
    loss = next(x for x in check.losses if x.column == "speed")
    assert loss.kind == "changed_cell" and loss.count == 1, "94.25 is exact in 32 bits, 85.8 is not"
    assert "85.8" in loss.example


def test_a_dropped_leading_zero_is_a_changed_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    columns = [("npb", "int32") if c[0] == "npb" else c for c in GOOD_COLUMNS]
    spec = _spec(monkeypatch, columns)
    table = _good_table(spec, npb=(1405134, 12, 7))
    check = roundtrip_dataset(_lake(tmp_path, spec, RAW, table), spec)
    loss = next(x for x in check.losses if x.column == "npb")
    assert loss.kind == "changed_cell" and loss.count == 2, (
        "01405134 and 00000012 lost their zeros; 7 is fine"
    )
    assert "01405134" in loss.example


def test_a_value_turned_into_null_and_a_missing_row_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(monkeypatch, GOOD_COLUMNS)
    table = _good_table(spec)
    table = table.set_column(
        1, "speed", pa.array([None, 94.25, None], pa.float64())
    )  # 85.8 became NULL
    table = table.slice(0, 2)  # row 3 was dropped
    check = roundtrip_dataset(_lake(tmp_path, spec, RAW, table), spec)
    kinds = {(x.kind, x.column): x.count for x in check.losses}
    assert kinds[("lost_to_null", "speed")] == 1
    assert kinds[("row_missing", "")] == 1
    assert check.compared == 2


def test_a_raw_column_nothing_reads_is_a_loss_unless_extras_holds_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(monkeypatch, GOOD_COLUMNS)
    table = _good_table(spec).set_column(5, "_extras", pa.array([None, None, None], pa.string()))
    check = roundtrip_dataset(_lake(tmp_path, spec, RAW, table), spec)
    unmapped = [x for x in check.losses if x.kind == "unmapped_raw_column"]
    assert [x.column for x in unmapped] == ["extra"], (
        "the raw column `extra` is in neither a column nor _extras"
    )


def test_a_dataset_without_csv_raw_files_is_skipped_with_a_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(monkeypatch, GOOD_COLUMNS)
    config = LakeConfig(home=tmp_path)
    RawStore(config).put(SOURCE, spec.name, "page.json", b"{}")
    ProcessedStore(config).put(spec, _good_table(spec))
    check = roundtrip_dataset(config, spec)
    assert check.status == "skipped" and "csv" in check.reason.lower()
    empty = roundtrip_dataset(LakeConfig(home=tmp_path / "none"), spec)
    assert empty.status == "skipped" and "raw" in empty.reason.lower()


def test_repeating_keys_are_compared_as_multisets_and_overlapping_windows_are_not_a_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two raw files that overlap (a capped window and its halves) repeat rows; a key that repeats still works."""
    spec = _spec(
        monkeypatch, [("id", "int32"), ("speed", "float64"), ("note", "string")], keys=("id",)
    )
    config = LakeConfig(home=tmp_path)
    raw = RawStore(config)
    raw.put(SOURCE, spec.name, "a.csv", b"id,speed,note\n1,1.5,a\n1,2.5,b\n2,3.5,c\n")
    raw.put(SOURCE, spec.name, "b.csv", b"id,speed,note\n1,2.5,b\n2,3.5,c\n")  # overlaps a.csv
    table = pa.table(
        {"id": pa.array([1, 1, 2], pa.int32()), "speed": [1.5, 2.5, 3.5], "note": ["a", "b", "c"]}
    )
    ProcessedStore(config).put(
        spec, table.append_column("_extras", pa.array([None] * 3, pa.string()))
    )
    check = roundtrip_dataset(config, spec)
    assert check.status == "ok", check.losses
    wrong = pa.table(
        {"id": pa.array([1, 1, 2], pa.int32()), "speed": [1.5, 2.75, 3.5], "note": ["a", "b", "c"]}
    )
    ProcessedStore(config).put(
        spec, wrong.append_column("_extras", pa.array([None] * 3, pa.string()))
    )
    bad = roundtrip_dataset(config, spec)
    assert [x.column for x in bad.losses if x.kind == "changed_cell"] == ["speed"]
