"""The dlt sink keeps our Arrow types and merges on the key, in DuckDB and in PostgreSQL."""

import datetime as dt
import uuid
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.sinks.dlt import DltSink, allowed_sql_types, type_mismatches


def _table(keys: list[str], i32: int = 3) -> pa.Table:
    n = len(keys)
    return pa.table(
        {
            "key": pa.array(keys),
            "s": pa.array(["x"] * (n - 1) + [None]),
            "i8": pa.array([1] * (n - 1) + [None], pa.int8()),
            "i16": pa.array([2] * (n - 1) + [None], pa.int16()),
            "i32": pa.array([i32] * (n - 1) + [None], pa.int32()),
            "i64": pa.array([2**40] * (n - 1) + [None], pa.int64()),
            "f32": pa.array([0.5] * (n - 1) + [None], pa.float32()),
            "f64": pa.array([0.25] * (n - 1) + [None], pa.float64()),
            "b": pa.array([True] * (n - 1) + [None], pa.bool_()),
            "d": pa.array([dt.date(2024, 1, 1)] * (n - 1) + [None], pa.date32()),
            "ts": pa.array(
                [dt.datetime(2024, 1, 1, tzinfo=dt.UTC)] * (n - 1) + [None],
                pa.timestamp("us", "UTC"),
            ),
            "dict": pa.array(["a"] * n)
            .dictionary_encode()
            .cast(pa.dictionary(pa.int8(), pa.string())),
        }
    )


@pytest.fixture(scope="module")
def postgres_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    pgserver = pytest.importorskip("pgserver")
    server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"), cleanup_mode="stop")
    try:
        yield str(server.get_uri())
    finally:
        server.cleanup()


@pytest.fixture(params=["duckdb", "postgres"])
def sink(request: pytest.FixtureRequest, tmp_path: Path) -> DltSink:
    name = uuid.uuid4().hex[:8]
    if request.param == "duckdb":
        return DltSink(
            destination="duckdb",
            dataset_name="baseballpy",
            credentials=str(tmp_path / "t.duckdb"),
            pipelines_dir=str(tmp_path / "pipes"),
            pipeline_name=f"t_{name}",
        )
    return DltSink(
        destination="postgres",
        dataset_name=f"t_{name}",
        credentials=request.getfixturevalue("postgres_url"),
        pipelines_dir=str(tmp_path / "pipes"),
        pipeline_name=f"t_{name}",
    )


def _values(sink: DltSink, column: str) -> dict[str, object]:
    with sink.pipeline.sql_client() as client:
        qualified = client.make_qualified_table_name("probe")
        query = f"select key, {column} from {qualified} order by key"  # noqa: S608 - test-only
        rows = client.execute_sql(query)
    return {key: value for key, value in rows}


def test_types_survive_the_load_and_the_read_back_reports_no_mismatch(sink: DltSink) -> None:
    table = _table(["k0", "k1", "k2"])
    assert sink.write(table, "probe", write_disposition="replace", primary_key=["key"]) == 3
    info = sink.table_info("probe")
    assert info.rows == 3
    assert type_mismatches(table.schema, info.columns) == []


def test_merge_updates_matching_keys_and_never_duplicates(sink: DltSink) -> None:
    sink.write(_table(["k0", "k1", "k2"], i32=3), "probe", "replace", primary_key=["key"])
    sink.write(_table(["k1", "k2", "k3"], i32=99), "probe", "merge", primary_key=["key"])
    assert sink.table_info("probe").rows == 4  # k0 stays, k1 and k2 updated, k3 new
    assert _values(sink, "i32") == {"k0": 3, "k1": 99, "k2": 99, "k3": None}


def test_append_adds_rows_and_replace_starts_over(sink: DltSink) -> None:
    sink.write(_table(["k0", "k1"]), "probe", "replace", primary_key=["key"])
    sink.write(_table(["k2", "k3"]), "probe", "append")
    assert sink.table_info("probe").rows == 4
    sink.write(_table(["z0"]), "probe", "replace", primary_key=["key"])
    assert sink.table_info("probe").rows == 1


def test_bad_dispositions_are_refused(sink: DltSink) -> None:
    with pytest.raises(ValueError, match="requires primary_key"):
        sink.write(_table(["a", "b"]), "probe", "merge")
    with pytest.raises(ValueError, match="unsupported write_disposition"):
        sink.write(_table(["a", "b"]), "probe", "upsert")


def test_sql_type_table_and_mismatch_report() -> None:
    schema = _table(["a", "b"]).schema
    assert allowed_sql_types(pa.int16()) == {"smallint"}
    assert "double precision" in allowed_sql_types(pa.float32())  # lossless widening
    ok = {f.name: sorted(allowed_sql_types(f.type))[0] for f in schema}
    assert type_mismatches(schema, ok) == []
    bad = {**ok, "i16": "bigint"}
    assert type_mismatches(schema, bad) == ["i16: arrow int16 became database type bigint"]
    assert "columns differ" in type_mismatches(schema, {"key": "varchar"})[0]
    assert type_mismatches(schema, {**ok, "_dlt_id": "varchar"}) == []  # bookkeeping is ignored
