"""Audit telemetry tests for PolarsSink and DltSink."""

from pathlib import Path

import dlt
import polars as pl
import pyarrow as pa
import pytest

from baseballpy.core.audit import default_audit_logger
from baseballpy.sinks.dlt import DltSink
from baseballpy.sinks.polars import PolarsSink


def _sample_table() -> pa.Table:
    """Return a small, strongly-typed Arrow table for testing."""
    return pa.table(
        {
            "id": pa.array([1, 2, 3], pa.int32()),
            "name": pa.array(["a", "b", "c"], pa.string()),
            "val": pa.array([10.5, 20.0, 30.5], pa.float64()),
        }
    )


def test_polars_sink_write_audited() -> None:
    """PolarsSink.write emits a single polars_write audit event on success."""
    table = _sample_table()
    sink = PolarsSink()
    rows = sink.write(table, destination="memory")
    assert rows == 3
    assert sink.last is not None
    assert len(sink.last) == 3

    events = default_audit_logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event.operation == "polars_write"
    assert event.source == "sink"
    assert event.destination == "memory"
    assert event.status == "SUCCESS"
    assert event.records_count == 3
    assert event.error is None


def test_polars_sink_write_stream_audited() -> None:
    """PolarsSink.write_stream emits a single polars_write_stream audit event on success."""
    table = _sample_table()
    reader = pa.RecordBatchReader.from_batches(table.schema, table.to_batches(max_chunksize=1))
    sink = PolarsSink()
    rows = sink.write_stream(reader, destination="memory_stream")
    assert rows == 3
    assert sink.last is not None
    assert len(sink.last) == 3

    events = default_audit_logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event.operation == "polars_write_stream"
    assert event.source == "sink"
    assert event.destination == "memory_stream"
    assert event.status == "SUCCESS"
    assert event.records_count == 3
    assert event.error is None


def test_polars_sink_failing_write_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    """PolarsSink.write records FAILURE and propagates the exception when write fails."""
    table = _sample_table()
    sink = PolarsSink()

    def _fail(t: pa.Table) -> pl.DataFrame:
        raise ValueError("simulated polars failure")

    monkeypatch.setattr(sink, "to_dataframe", _fail)

    with pytest.raises(ValueError, match="simulated polars failure"):
        sink.write(table, destination="memory_fail")

    events = default_audit_logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event.operation == "polars_write"
    assert event.source == "sink"
    assert event.destination == "memory_fail"
    assert event.status == "FAILURE"
    assert "ValueError: simulated polars failure" in (event.error or "")


def test_dlt_sink_write_audited(tmp_path: Path) -> None:
    """DltSink.write emits a single dlt_write audit event on success."""
    pipeline = dlt.pipeline(
        pipeline_name="test_dlt_write_audit",
        destination=dlt.destinations.duckdb(str(tmp_path / "dlt_audit.duckdb")),
        dataset_name="test_audit_ds",
    )
    sink = DltSink(pipeline=pipeline)
    table = _sample_table()
    rows = sink.write(table, destination="sample_table")
    assert rows == 3
    assert sink.last_load_info is not None

    events = default_audit_logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event.operation == "dlt_write"
    assert event.source == "sink"
    assert event.destination == "sample_table"
    assert event.status == "SUCCESS"
    assert event.records_count == 3
    assert event.error is None


def test_dlt_sink_write_stream_audited(tmp_path: Path) -> None:
    """DltSink.write_stream emits a single dlt_write_stream audit event on success."""
    pipeline = dlt.pipeline(
        pipeline_name="test_dlt_stream_audit",
        destination=dlt.destinations.duckdb(str(tmp_path / "dlt_stream_audit.duckdb")),
        dataset_name="test_audit_ds",
    )
    sink = DltSink(pipeline=pipeline)
    table = _sample_table()
    reader = pa.RecordBatchReader.from_batches(table.schema, table.to_batches(max_chunksize=1))
    rows = sink.write_stream(reader, destination="stream_table")
    assert rows == 3

    events = default_audit_logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event.operation == "dlt_write_stream"
    assert event.source == "sink"
    assert event.destination == "stream_table"
    assert event.status == "SUCCESS"
    assert event.records_count == 3
    assert event.error is None


def test_dlt_sink_failing_write_audited(tmp_path: Path) -> None:
    """DltSink.write records FAILURE and propagates the exception on invalid options."""
    pipeline = dlt.pipeline(
        pipeline_name="test_dlt_fail_audit",
        destination=dlt.destinations.duckdb(str(tmp_path / "dlt_fail_audit.duckdb")),
        dataset_name="test_audit_ds",
    )
    sink = DltSink(pipeline=pipeline)
    table = _sample_table()

    with pytest.raises(ValueError, match="unsupported write_disposition"):
        sink.write(table, destination="bad_table", write_disposition="unsupported_disposition")

    events = default_audit_logger.read_events()
    assert len(events) == 1
    event = events[0]
    assert event.operation == "dlt_write"
    assert event.source == "sink"
    assert event.destination == "bad_table"
    assert event.status == "FAILURE"
    assert "ValueError" in (event.error or "")
