"""Tests for audit logging, execution benchmarking, and telemetry persistence."""

from pathlib import Path

import pytest

from baseballpy.core.audit import AuditConfig, AuditLogger


def test_audit_logger_tracking_success(tmp_path: Path) -> None:
    config = AuditConfig(base_dir=tmp_path)
    logger = AuditLogger(config=config)

    with logger.track(operation="statcast_fetch", source="statcast") as tracker:
        tracker.set_records(500)
        tracker.set_cache_hit(False)
        tracker.set_endpoint("https://baseballsavant.mlb.com/statcast_search")
        tracker.set_destination("statcast.parquet")

    events = logger.read_events()
    assert len(events) == 1
    ev = events[0]
    assert ev.operation == "statcast_fetch"
    assert ev.source == "statcast"
    assert ev.status == "SUCCESS"
    assert ev.records_count == 500
    assert ev.cache_hit is False
    assert ev.duration_seconds >= 0.0
    assert ev.throughput_rps > 0.0
    assert ev.endpoint == "https://baseballsavant.mlb.com/statcast_search"
    assert ev.error is None


def test_audit_logger_tracking_failure(tmp_path: Path) -> None:
    config = AuditConfig(base_dir=tmp_path)
    logger = AuditLogger(config=config)

    with (
        pytest.raises(ValueError, match="simulated failure"),
        logger.track(operation="mlb_api_sync", source="mlb_api") as tracker,
    ):
        tracker.set_records(10)
        raise ValueError("simulated failure")

    events = logger.read_events()
    assert len(events) == 1
    ev = events[0]
    assert ev.operation == "mlb_api_sync"
    assert ev.status == "FAILURE"
    assert "ValueError: simulated failure" in (ev.error or "")


def test_audit_logger_stats(tmp_path: Path) -> None:
    config = AuditConfig(base_dir=tmp_path)
    logger = AuditLogger(config=config)

    with logger.track(operation="op1", source="statcast") as t1:
        t1.set_records(100)
        t1.set_cache_hit(True)

    with logger.track(operation="op2", source="chadwick") as t2:
        t2.set_records(200)
        t2.set_cache_hit(False)

    stats = logger.get_stats()
    assert stats["total_operations"] == 2
    assert stats["total_records"] == 300
    assert stats["success_rate"] == 1.0
    assert stats["cache_hit_rate"] == 0.5
    assert "statcast" in stats["by_source"]
    assert "chadwick" in stats["by_source"]
