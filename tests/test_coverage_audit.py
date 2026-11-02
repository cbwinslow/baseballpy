"""Tests for expected vs held coverage auditing and CLI gap remediation."""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import LakeConfig
from baseballpy.coverage import audit_season_coverage, check_mlb_games, check_statcast_pitches


def test_catalog_coverage_season_report(tmp_path: Path) -> None:
    """Verify that expected vs held entities are correctly calculated with remediation commands."""
    lake = LakeConfig(home=tmp_path)
    season = 2024

    # Initially empty lake
    report = audit_season_coverage(season=season, config=lake)
    assert report.season == season
    assert report.total_expected > 0
    assert report.total_held == 0
    assert report.overall_percent == 0.0

    # Write a mocked schedule with 3 final games and 1 preview game
    sched_dir = lake.processed_dir("mlb_api", "schedule_hydrated", season)
    sched_dir.mkdir(parents=True, exist_ok=True)
    sched_tbl = pa.table(
        {
            "game_pk": [101, 102, 103, 104],
            "status_abstract_game_state": ["Final", "Final", "Final", "Preview"],
        }
    )
    pq.write_table(sched_tbl, sched_dir / "part-sched.parquet")

    # Write 2 held boxscores
    box_dir = lake.processed_dir("mlb_api", "game_boxscores", season)
    box_dir.mkdir(parents=True, exist_ok=True)
    box_tbl = pa.table({"game_pk": [101, 102]})
    pq.write_table(box_tbl, box_dir / "part-box.parquet")

    mlb_item = check_mlb_games(season, lake)
    assert mlb_item.expected_count == 3
    assert mlb_item.held_count == 2
    assert mlb_item.missing_count == 1
    assert mlb_item.held_percent == 66.7
    assert mlb_item.missing_ids == (103,)
    assert "baseballpy ingest mlb_api --seasons 2024 -d games" in mlb_item.remediation_cmd

    # Add the missing game 103
    box_tbl_complete = pa.table({"game_pk": [101, 102, 103]})
    pq.write_table(box_tbl_complete, box_dir / "part-box.parquet")

    mlb_item_complete = check_mlb_games(season, lake)
    assert mlb_item_complete.expected_count == 3
    assert mlb_item_complete.held_count == 3
    assert mlb_item_complete.missing_count == 0
    assert mlb_item_complete.held_percent == 100.0
    assert mlb_item_complete.remediation_cmd == "(up to date)"


def test_catalog_coverage_statcast_chunks(tmp_path: Path) -> None:
    """Verify Statcast pitch chunk tracking."""
    lake = LakeConfig(home=tmp_path)
    season = 2024

    item = check_statcast_pitches(season, lake)
    assert item.expected_count == 31
    assert item.held_count == 0
    assert "ingest statcast" in item.remediation_cmd

    # Write 31 chunk files
    pitch_dir = lake.processed_dir("statcast", "pitches", season)
    pitch_dir.mkdir(parents=True, exist_ok=True)
    tbl = pa.table({"pitch_type": ["FF"]})
    for i in range(31):
        pq.write_table(tbl, pitch_dir / f"part-w{i:02d}.parquet")

    item_done = check_statcast_pitches(season, lake)
    assert item_done.held_count == 31
    assert item_done.missing_count == 0
    assert item_done.held_percent == 100.0
    assert item_done.remediation_cmd == "(up to date)"


def test_catalog_coverage_cli(monkeypatch: object, tmp_path: Path) -> None:
    """Verify CLI catalog coverage table and JSON execution."""
    runner = CliRunner()

    result = runner.invoke(main, ["catalog", "coverage", "--season", "2024"])
    assert result.exit_code == 0
    assert "Coverage Audit" in result.output
    assert "mlb_api" in result.output
    assert "Remediation" in result.output and "Command" in result.output

    result_json = runner.invoke(main, ["catalog", "coverage", "--season", "2024", "--json"])
    assert result_json.exit_code == 0
    data = json.loads(result_json.output)
    assert data["season"] == 2024
    assert "items" in data
    assert any(item["source"] == "mlb_api" for item in data["items"])
