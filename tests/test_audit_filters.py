"""Audit log filters (``--source``, ``--status``, ``--since``) on the logger and the CLI."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy import cli
from baseballpy.core.audit import AuditEvent, AuditLogger
from baseballpy.core.config import AuditConfig


def _event(source: str, status: str, stamp: str, operation: str = "op") -> AuditEvent:
    return AuditEvent(timestamp_utc=stamp, operation=operation, source=source, status=status)


@pytest.fixture
def logger(tmp_path: Path) -> AuditLogger:
    audit = AuditLogger(AuditConfig(base_dir=tmp_path))
    audit.log(_event("statcast", "SUCCESS", "2026-10-01T10:00:00+00:00", "a"))
    audit.log(_event("mlb_api", "FAILURE", "2026-10-02T10:00:00+00:00", "b"))
    audit.log(_event("mlb_api", "SUCCESS", "2026-10-03T10:00:00+00:00", "c"))
    return audit


def test_filters_by_source_status_and_since(logger: AuditLogger) -> None:
    assert [e.operation for e in logger.read_events(source="mlb_api")] == ["b", "c"]
    assert [e.operation for e in logger.read_events(status="failure")] == ["b"]
    assert [e.operation for e in logger.read_events(since="2026-10-02")] == ["b", "c"]
    assert [e.operation for e in logger.read_events(source="mlb_api", status="SUCCESS")] == ["c"]


def test_filters_apply_before_limit(logger: AuditLogger) -> None:
    assert [e.operation for e in logger.read_events(limit=1, source="statcast")] == ["a"]
    assert [e.operation for e in logger.read_events(limit=1, source="mlb_api")] == ["c"]


def test_cli_summary_and_tail_accept_the_filters(
    logger: AuditLogger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "default_audit_logger", logger)
    runner = CliRunner()
    summary = runner.invoke(cli.main, ["audit", "summary", "--status", "FAILURE"])
    assert summary.exit_code == 0
    assert "FAILURE" in summary.output and "SUCCESS" not in summary.output
    tail = runner.invoke(
        cli.main, ["audit", "tail", "--source", "statcast", "--since", "2026-10-01"]
    )
    assert tail.exit_code == 0
    assert "statcast" in tail.output and "mlb_api" not in tail.output
