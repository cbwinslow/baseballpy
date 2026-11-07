"""Tests for audit log rotation, compression, and threshold enforcement."""

import gzip
from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.audit import AuditEvent, AuditLogger
from baseballpy.core.config import AuditConfig


def test_audit_logger_rotates_when_threshold_exceeded(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config = AuditConfig(log_dir_override=log_dir, max_bytes=100, auto_rotate=False)
    logger = AuditLogger(config)

    # Write a record
    ev = AuditEvent(
        timestamp_utc="2026-11-06T23:00:00Z",
        operation="test_op",
        source="test_src",
        status="SUCCESS",
        records_count=50,
    )
    for _ in range(5):
        logger.log(ev)

    assert logger.log_path.stat().st_size > 100

    rotated = logger.rotate(max_bytes=100)
    assert rotated is not None
    assert rotated.exists()
    assert rotated.name.endswith(".jsonl.gz")

    # Verify compressed contents match
    with gzip.open(rotated, "rb") as f:
        decompressed = f.read()
    assert b"test_op" in decompressed

    # Active log exists and is now empty
    assert logger.log_path.exists()
    assert logger.log_path.stat().st_size == 0


def test_audit_logger_force_rotate(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config = AuditConfig(log_dir_override=log_dir, max_bytes=10_000, auto_rotate=False)
    logger = AuditLogger(config)

    ev = AuditEvent(
        timestamp_utc="2026-11-06T23:00:00Z",
        operation="force_test",
        source="test_src",
        status="SUCCESS",
    )
    logger.log(ev)

    # Below threshold without force
    assert logger.rotate(force=False) is None

    # Forced rotation
    rotated = logger.rotate(force=True)
    assert rotated is not None
    assert rotated.exists()
    assert logger.log_path.stat().st_size == 0


def test_audit_logger_auto_rotate_during_log(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    config = AuditConfig(log_dir_override=log_dir, max_bytes=200, auto_rotate=True)
    logger = AuditLogger(config)

    ev = AuditEvent(
        timestamp_utc="2026-11-06T23:00:00Z",
        operation="auto_test_operation_with_longer_payload",
        source="test_src",
        status="SUCCESS",
        records_count=100,
    )
    # Logging multiple events pushes size past 200 bytes
    for _ in range(5):
        logger.log(ev)

    # Check that a rotated gzip file was automatically created
    rotated_files = list(log_dir.glob("audit-*.jsonl.gz"))
    assert len(rotated_files) >= 1


def test_cli_audit_rotate_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    audit_file = log_dir / "audit.jsonl"
    audit_file.write_text('{"event": "dummy"}\n' * 50, encoding="utf-8")

    monkeypatch.setenv("BASEBALLPY_AUDIT_LOG_DIR_OVERRIDE", str(log_dir))

    runner = CliRunner()
    result = runner.invoke(main, ["audit", "rotate", "--force"])
    assert result.exit_code == 0
    assert "Audit log rotated:" in result.output
