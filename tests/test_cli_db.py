"""Tests for CLI db views, query, and shell subcommands."""

import json
from collections.abc import Generator
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import reset_config
from baseballpy.database import BaseballDatabase


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


def test_db_views_and_query_with_fabricated_parquet(tmp_path: Path, runner: CliRunner) -> None:
    """Verify db views and query against a temporary lake with synced Parquet views."""
    target_dir = tmp_path / "processed" / "statcast" / "pitches" / "season=2020"
    target_dir.mkdir(parents=True, exist_ok=True)
    sample_table = pa.table(
        {
            "game_pk": [1001, 1002, 1003],
            "at_bat_number": [1, 1, 2],
            "pitch_number": [1, 2, 1],
        }
    )
    pq.write_table(sample_table, target_dir / "pitches.parquet")

    database = BaseballDatabase()
    count = database.sync_views()
    assert count > 0

    res_views = runner.invoke(main, ["db", "views"])
    assert res_views.exit_code == 0, res_views.output
    assert "statcast_pitches" in res_views.output
    assert "3" in res_views.output

    res_views_json = runner.invoke(main, ["db", "views", "--json"])
    assert res_views_json.exit_code == 0, res_views_json.output
    lines = [
        json.loads(line) for line in res_views_json.output.strip().splitlines() if line.strip()
    ]
    statcast_view = next(v for v in lines if v["view"] == "statcast_pitches")
    assert statcast_view["rows"] == 3

    res_query = runner.invoke(
        main,
        [
            "db",
            "query",
            "SELECT game_pk, at_bat_number, pitch_number FROM statcast_pitches ORDER BY pitch_number",
        ],
    )
    assert res_query.exit_code == 0, res_query.output
    assert "1001" in res_query.output
    assert "1002" in res_query.output

    res_q_json = runner.invoke(
        main,
        ["db", "query", "SELECT game_pk FROM statcast_pitches ORDER BY game_pk", "--json"],
    )
    assert res_q_json.exit_code == 0, res_q_json.output
    q_rows = [json.loads(line) for line in res_q_json.output.strip().splitlines() if line.strip()]
    assert len(q_rows) == 3
    assert [r["game_pk"] for r in q_rows] == [1001, 1002, 1003]

    res_csv = runner.invoke(
        main,
        ["db", "query", "SELECT game_pk FROM statcast_pitches ORDER BY game_pk", "--csv"],
    )
    assert res_csv.exit_code == 0, res_csv.output
    assert "game_pk" in res_csv.output
    assert "1001" in res_csv.output

    res_limit = runner.invoke(
        main,
        [
            "db",
            "query",
            "SELECT game_pk FROM statcast_pitches ORDER BY game_pk",
            "--limit",
            "2",
            "--json",
        ],
    )
    assert res_limit.exit_code == 0, res_limit.output
    limited_rows = [
        json.loads(line) for line in res_limit.output.strip().splitlines() if line.strip()
    ]
    assert len(limited_rows) == 2


def test_db_query_write_fails(tmp_path: Path, runner: CliRunner) -> None:
    """Verify DuckDB read-only connection refuses writes and raises ClickException."""
    BaseballDatabase().sync_views()

    res = runner.invoke(main, ["db", "query", "CREATE TABLE write_test AS SELECT 1"])
    assert res.exit_code != 0
    assert (
        "read-only" in res.output.lower()
        or "cannot execute" in res.output.lower()
        or "error" in res.output.lower()
    )


def test_db_missing_gives_click_exception(runner: CliRunner) -> None:
    """Verify missing database file raises ClickException with sync hint."""
    res_views = runner.invoke(main, ["db", "views"])
    assert res_views.exit_code != 0
    assert "baseballpy db sync" in res_views.output

    res_query = runner.invoke(main, ["db", "query", "SELECT 1"])
    assert res_query.exit_code != 0
    assert "baseballpy db sync" in res_query.output


def test_db_shell_missing_executable_error(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify db shell raises ClickException when duckdb executable is absent from PATH."""
    BaseballDatabase().sync_views()
    monkeypatch.setattr("shutil.which", lambda _: None)

    res = runner.invoke(main, ["db", "shell"])
    assert res.exit_code != 0
    assert "not found on PATH" in res.output
    assert "db query" in res.output


def test_db_shell_executes_when_found(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify db shell invokes exec_duckdb with resolved executable and database path."""
    database = BaseballDatabase()
    database.sync_views()
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/duckdb")

    invoked_calls: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        "baseballpy.cli_db.exec_duckdb",
        lambda exe, path: invoked_calls.append((exe, path)),
    )

    res = runner.invoke(main, ["db", "shell"])
    assert res.exit_code == 0
    assert len(invoked_calls) == 1
    assert invoked_calls[0][0] == "/usr/local/bin/duckdb"
    assert invoked_calls[0][1] == database.db_path
