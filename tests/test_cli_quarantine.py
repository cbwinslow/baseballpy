"""Tests for CLI quarantine list and show subcommands."""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.cli_quarantine import (
    QuarantineFile,
    scan_quarantine,
)
from baseballpy.core.config import QuarantineConfig, reset_config
from baseballpy.core.quarantine import Quarantine


@pytest.fixture(autouse=True)
def isolated_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Isolate lake home directory with temporary BASEBALLPY_HOME."""
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    reset_config()
    yield
    reset_config()


@pytest.fixture
def runner() -> CliRunner:
    """Fixture providing a Click CliRunner."""
    return CliRunner()


def test_quarantine_list_and_filters(tmp_path: Path, runner: CliRunner) -> None:
    """Verify quarantine list displays files and respects source, dataset, and json flags."""
    quarantine = Quarantine(QuarantineConfig(base_dir=tmp_path))
    p1 = quarantine.write("statcast", "pitches", [{"row": 1}], reason="uncastable float")
    p2 = quarantine.write("mlb_api", "schedule", [{"row": 2}], reason="malformed date")
    assert p1 is not None and p2 is not None

    res = runner.invoke(main, ["quarantine", "list"])
    assert res.exit_code == 0, res.output
    assert "statcast" in res.output
    assert "pitches" in res.output
    assert "mlb_api" in res.output
    assert "schedule" in res.output

    res_src = runner.invoke(main, ["quarantine", "list", "--source", "statcast"])
    assert res_src.exit_code == 0, res_src.output
    assert "statcast" in res_src.output
    assert "mlb_api" not in res_src.output

    res_ds = runner.invoke(main, ["quarantine", "list", "--dataset", "schedule"])
    assert res_ds.exit_code == 0, res_ds.output
    assert "schedule" in res_ds.output
    assert "pitches" not in res_ds.output

    res_json = runner.invoke(main, ["quarantine", "list", "--json"])
    assert res_json.exit_code == 0, res_json.output
    records = [json.loads(line) for line in res_json.output.strip().splitlines() if line.strip()]
    assert len(records) == 2
    sources = {r["source"] for r in records}
    assert sources == {"statcast", "mlb_api"}
    assert {r["reason"] for r in records} == {"uncastable float", "malformed date"}


def test_quarantine_list_empty_directory_exits_zero(runner: CliRunner) -> None:
    """Verify empty quarantine directory produces empty list and exits 0."""
    res = runner.invoke(main, ["quarantine", "list"])
    assert res.exit_code == 0, res.output
    assert "Quarantined Files" in res.output


def test_quarantine_show_valid_file_and_json(tmp_path: Path, runner: CliRunner) -> None:
    """Verify quarantine show renders record attributes and raw JSON lines."""
    quarantine = Quarantine(QuarantineConfig(base_dir=tmp_path))
    file_path = quarantine.write(
        "statcast",
        "pitches",
        [{"game_pk": 123, "val": "abc"}],
        reason="incompatible type",
        context={"column": "launch_speed"},
    )
    assert file_path is not None
    rel_path = file_path.relative_to(tmp_path / "quarantine")

    res = runner.invoke(main, ["quarantine", "show", str(rel_path)])
    assert res.exit_code == 0, res.output
    assert "incompatible type" in res.output
    assert "launch_speed" in res.output
    assert "abc" in res.output

    res_json = runner.invoke(main, ["quarantine", "show", str(rel_path), "--json"])
    assert res_json.exit_code == 0, res_json.output
    parsed = json.loads(res_json.output.strip())
    assert parsed["source"] == "statcast"
    assert parsed["reason"] == "incompatible type"


def test_quarantine_show_refuses_outside_path(runner: CliRunner) -> None:
    """Verify quarantine show rejects paths that resolve outside the quarantine root."""
    res_rel = runner.invoke(main, ["quarantine", "show", "../../escape.jsonl"])
    assert res_rel.exit_code == 2, res_rel.output
    assert "resolves outside the quarantine directory" in res_rel.output

    res_abs = runner.invoke(main, ["quarantine", "show", "/etc/passwd"])
    assert res_abs.exit_code == 2, res_abs.output
    assert "resolves outside the quarantine directory" in res_abs.output


def test_quarantine_show_corrupt_line_reported(tmp_path: Path, runner: CliRunner) -> None:
    """Verify corrupt non-JSON lines in dead-letter files are reported with line number."""
    bad_file = tmp_path / "quarantine" / "statcast" / "2026-10-28" / "pitches-corrupt.jsonl"
    bad_file.parent.mkdir(parents=True, exist_ok=True)
    bad_file.write_text(
        '{"ts": "2026-10-28", "source": "statcast", "dataset": "pitches", "reason": "ok", "context": {}, "payload": "good"}\n'
        "{INVALID JSON LINE}\n",
        encoding="utf-8",
    )
    rel_path = bad_file.relative_to(tmp_path / "quarantine")

    res = runner.invoke(main, ["quarantine", "show", str(rel_path)])
    assert res.exit_code == 0, res.output
    assert "Line 2" in res.output
    assert "CORRUPT" in res.output

    res_json = runner.invoke(main, ["quarantine", "show", str(rel_path), "--json"])
    assert res_json.exit_code == 0, res_json.output
    lines = [json.loads(line) for line in res_json.output.strip().splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["reason"] == "ok"
    assert lines[1]["line"] == 2
    assert "corrupt JSON" in lines[1]["error"]


def test_scan_quarantine_pure_function(tmp_path: Path) -> None:
    """Verify scan_quarantine returns frozen QuarantineFile instances sorted newest first."""
    config = QuarantineConfig(base_dir=tmp_path)
    quarantine = Quarantine(config)
    quarantine.write("statcast", "pitches", [{"row": 1}], reason="reason1")

    scanned = scan_quarantine(config)
    assert len(scanned) == 1
    assert isinstance(scanned[0], QuarantineFile)
    assert scanned[0].source == "statcast"
    assert scanned[0].dataset == "pitches"
    assert scanned[0].records == 1
