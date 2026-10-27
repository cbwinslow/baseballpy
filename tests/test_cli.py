"""CLI tests (click CliRunner)."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from baseballpy.cli import main


def test_licenses_flag_lists_every_source() -> None:
    result = CliRunner().invoke(main, ["--licenses"])
    assert result.exit_code == 0
    for needle in ("GPL-3.0-or-later", "Retrosheet", "Lahman", "Chadwick", "MLB"):
        assert needle in result.output


def test_help_lists_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "statcast" in result.output and "audit" in result.output


def test_help_lists_layout_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert "migrate-layout" in result.output and "db" in result.output


def test_migrate_layout_dry_run_and_real_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    src = tmp_path / "cache" / "lahman" / "processed"
    src.mkdir(parents=True)
    pq.write_table(pa.table({"playerID": ["a"]}), src / "Batting.parquet")

    dry = CliRunner().invoke(main, ["migrate-layout", "--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert "dry run" in dry.output and "planned" in dry.output
    assert not (tmp_path / "VERSION").exists()

    real = CliRunner().invoke(main, ["migrate-layout"])
    assert real.exit_code == 0, real.output
    assert (tmp_path / "processed" / "lahman" / "Batting" / "part-data.parquet").exists()
    assert (tmp_path / "VERSION").read_text().strip() == "2"

    again = CliRunner().invoke(main, ["migrate-layout"])
    assert again.exit_code == 0 and "skipped (identical)" in again.output


def test_db_sync_creates_views(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baseballpy.core.config import LakeConfig, reset_config
    from baseballpy.core.datasets import get_dataset
    from baseballpy.core.stores import ProcessedStore
    from baseballpy.sources import catalog

    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    reset_config()
    catalog.register_all()
    ProcessedStore(LakeConfig()).put(get_dataset("lahman", "People"), pa.table({"playerID": ["a"]}))
    result = CliRunner().invoke(main, ["db", "sync"])
    assert result.exit_code == 0, result.output
    assert "views" in result.output
    assert (tmp_path / "databases" / "baseball.duckdb").exists()
