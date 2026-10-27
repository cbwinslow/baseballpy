"""Tests for DuckDB, Parquet, Polars, and dlt storage sinks."""

from pathlib import Path

import duckdb
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.sinks.dlt import DltSink
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sinks.polars import PolarsSink
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "statcast" / "sample_pitches.csv"


@pytest.fixture
def sample_table() -> pa.Table:
    normalizer = StatcastNormalizer()
    return normalizer.normalize(FIXTURE_PATH.read_bytes())


def test_duckdb_sink_append_and_replace(tmp_path: Path, sample_table: pa.Table) -> None:
    db_path = str(tmp_path / "test_baseball.duckdb")
    sink = DuckDBSink()

    # Initial append creates table
    rows1 = sink.write(sample_table, destination=db_path, table_name="pitches", mode="append")
    assert rows1 == 2

    con = duckdb.connect(db_path)
    res = con.execute("SELECT COUNT(*) FROM pitches").fetchone()
    count = res[0] if res else 0
    assert count == 2

    # Second append adds rows
    rows2 = sink.write(sample_table, destination=db_path, table_name="pitches", mode="append")
    assert rows2 == 2
    res2 = con.execute("SELECT COUNT(*) FROM pitches").fetchone()
    count_after_append = res2[0] if res2 else 0
    assert count_after_append == 4

    # Replace resets table to 2 rows
    sink.write(sample_table, destination=db_path, table_name="pitches", mode="replace")
    res3 = con.execute("SELECT COUNT(*) FROM pitches").fetchone()
    count_after_replace = res3[0] if res3 else 0
    assert count_after_replace == 2

    # Query metrics
    res_avg = con.execute("SELECT AVG(release_speed) FROM pitches").fetchone()
    avg_speed = res_avg[0] if res_avg else 0.0
    assert avg_speed > 90.0

    con.close()


def test_parquet_sink(tmp_path: Path, sample_table: pa.Table) -> None:
    parquet_path = str(tmp_path / "pitches.parquet")
    sink = ParquetSink()

    rows = sink.write(sample_table, destination=parquet_path)
    assert rows == 2
    assert Path(parquet_path).exists()

    # Read back and verify
    read_table = pq.read_table(parquet_path)
    assert len(read_table) == 2
    assert "game_pk" in read_table.column_names
    assert "bat_speed" in read_table.column_names


def test_polars_sink(sample_table: pa.Table) -> None:
    sink = PolarsSink()
    df = sink.to_dataframe(sample_table)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 2
    assert "game_pk" in df.columns

    lf = sink.to_lazyframe(sample_table)
    assert isinstance(lf, pl.LazyFrame)
    collected = lf.collect()
    assert len(collected) == 2


def test_dlt_sink(tmp_path: Path, sample_table: pa.Table) -> None:
    import dlt

    pipeline = dlt.pipeline(
        pipeline_name="test_baseball_dlt",
        destination=dlt.destinations.duckdb(str(tmp_path / "dlt_baseball.duckdb")),
        dataset_name="test_data",
    )
    sink = DltSink(pipeline=pipeline)
    rows = sink.write(sample_table, destination="test_pitches")
    assert rows == 2
    assert sink.last_load_info is not None
