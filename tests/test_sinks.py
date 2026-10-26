"""Tests for DuckDB and Parquet storage sinks."""

from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
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
    count = con.execute("SELECT COUNT(*) FROM pitches").fetchone()[0]
    assert count == 2

    # Second append adds rows
    rows2 = sink.write(sample_table, destination=db_path, table_name="pitches", mode="append")
    assert rows2 == 2
    count_after_append = con.execute("SELECT COUNT(*) FROM pitches").fetchone()[0]
    assert count_after_append == 4

    # Replace resets table to 2 rows
    sink.write(sample_table, destination=db_path, table_name="pitches", mode="replace")
    count_after_replace = con.execute("SELECT COUNT(*) FROM pitches").fetchone()[0]
    assert count_after_replace == 2

    # Query metrics
    avg_speed = con.execute("SELECT AVG(release_speed) FROM pitches").fetchone()[0]
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
