"""Tests for audit logging, execution benchmarking, concurrency safety, and telemetry persistence."""

import asyncio
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
    assert ev.started_at_utc != ""
    assert ev.completed_at_utc != ""
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


def test_audit_logger_download_and_processing_split(tmp_path: Path) -> None:
    config = AuditConfig(base_dir=tmp_path)
    logger = AuditLogger(config=config)

    with logger.track(operation="two_phase_op", source="retrosheet") as tracker:
        tracker.set_records(100)
        tracker.mark_download_complete()

    events = logger.read_events()
    assert len(events) == 1
    ev = events[0]
    assert ev.download_seconds is not None
    assert ev.processing_seconds is not None
    assert ev.duration_seconds >= ev.download_seconds


@pytest.mark.asyncio
async def test_audit_logger_async_track(tmp_path: Path) -> None:
    config = AuditConfig(base_dir=tmp_path)
    logger = AuditLogger(config=config)

    async with logger.async_track(operation="async_fetch", source="mlb_api") as tracker:
        await asyncio.sleep(0.01)
        tracker.set_records(42)

    events = logger.read_events()
    assert len(events) == 1
    assert events[0].operation == "async_fetch"
    assert events[0].records_count == 42


@pytest.mark.asyncio
async def test_audit_logger_high_concurrency_no_clobbering(tmp_path: Path) -> None:
    """Stress test: 50 concurrent async tasks writing simultaneously to audit.jsonl."""
    config = AuditConfig(base_dir=tmp_path)
    logger = AuditLogger(config=config)

    async def worker(idx: int) -> None:
        async with logger.async_track(operation=f"concurrent_op_{idx}", source="worker") as tracker:
            tracker.set_records(idx)
            tracker.set_endpoint(f"https://worker/{idx}")
            await asyncio.sleep(0.005)

    # Launch 50 concurrent tasks
    tasks = [worker(i) for i in range(50)]
    await asyncio.gather(*tasks)

    # Read back all events
    events = logger.read_events()
    assert len(events) == 50

    # Ensure all operations were recorded without data loss or corrupted lines
    operations = {ev.operation for ev in events}
    expected = {f"concurrent_op_{i}" for i in range(50)}
    assert operations == expected

    # Verify log file has exactly 50 non-empty lines
    lines = [
        line.strip()
        for line in logger.log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 50
