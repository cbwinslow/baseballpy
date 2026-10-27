"""Layout v1 -> v2 migration: synthetic v1 tree, idempotency, dry-run, verification, hints."""

import json
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy import migrate_layout as public_migrate_layout
from baseballpy.core import layout, migrate
from baseballpy.core.config import LakeConfig
from baseballpy.core.stores import ProcessedStore
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog


def _pq(path: Path, rows: dict[str, list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(rows), path)


def _manifest(path: Path, chunks: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"chunks": chunks}), encoding="utf-8")


def _entry(rows: int = 1) -> dict[str, object]:
    return {
        "status": "COMPLETED",
        "records_count": rows,
        "fetched_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:00:00+00:00",
    }


@pytest.fixture
def v1(tmp_path: Path) -> LakeConfig:
    """A representative v1 lake covering every source."""
    cfg = LakeConfig(home=tmp_path)
    c = tmp_path / "cache"

    # statcast: hive season dir, legacy flat file, leaderboard
    _pq(c / "statcast" / "season=2024" / "2024-04-01_2024-04-05.parquet", {"game_pk": [1, 2, 3]})
    _pq(c / "statcast" / "2023-04-01_2023-04-05.parquet", {"game_pk": [9]})
    _pq(c / "statcast" / "leaderboards" / "bat_tracking_2024.parquet", {"id": [1, 2]})
    _pq(
        c / "statcast" / "leaderboards" / "expected_statistics_2024_type=batter.parquet",
        {"id": [5]},
    )
    _manifest(
        c / "statcast" / "manifest.json",
        {"2024-04-01_2024-04-05": _entry(3), "2023-04-01_2023-04-05": _entry(1)},
    )
    _manifest(
        c / "statcast" / "leaderboards" / "manifest.json",
        {"bat_tracking_2024": _entry(2), "expected_statistics_2024_type=batter": _entry(1)},
    )

    # retrosheet raw + processed
    raw = c / "retrosheet" / "raw"
    (raw / "2023").mkdir(parents=True)
    (raw / "2023" / "2023BOS.EVA").write_text("id,BOS\n")
    (raw / "2023" / "TEAM2023").write_text("BOS,A\n")
    (raw / "2023" / "BOS2023.ROS").write_text("r\n")
    (raw / "gamelogs").mkdir()
    (raw / "gamelogs" / "gl2023.txt").write_text("a\n")
    (raw / "reference").mkdir()
    (raw / "reference" / "teams.csv").write_text("t\n")
    _manifest(
        raw / "manifest.json",
        {"season_2023": _entry(1), "gamelog_2023": _entry(1), "reference_teams": _entry(1)},
    )
    proc = c / "retrosheet" / "processed"
    _pq(proc / "events" / "season=2023" / "events.parquet", {"GAME_ID": ["A", "B"]})
    # events_all duplicates the regular-season games A and B and adds postseason game P
    _pq(proc / "events" / "season=2023" / "events_all.parquet", {"GAME_ID": ["A", "B", "P"]})
    _pq(proc / "boxscores_batting" / "season=2023" / "batting.parquet", {"game_id": ["A"]})
    _pq(proc / "gamelogs" / "gl2023.parquet", {"date": ["20230401"]})
    _pq(proc / "gamelogs" / "postseason" / "gl_world_series.parquet", {"date": ["20231028"]})
    _pq(proc / "rosters" / "rosters_2023.parquet", {"player_id": ["x"]})
    _pq(proc / "reference" / "teams.parquet", {"team_id": ["BOS"]})
    _manifest(
        proc / "manifest.json",
        {
            "events_2023": _entry(2),
            "events_2023_postseason": _entry(3),
            "box_batting_2023": _entry(1),
        },
    )

    # lahman
    (c / "lahman" / "raw").mkdir(parents=True)
    (c / "lahman" / "raw" / "Batting.csv").write_text("playerID\na\n")
    _pq(c / "lahman" / "processed" / "Batting.parquet", {"playerID": ["a"]})
    _manifest(c / "lahman" / "manifest.json", {"Batting": _entry(1)})

    # chadwick
    (c / "chadwick" / "shards").mkdir(parents=True)
    (c / "chadwick" / "shards" / "people-0.csv").write_text("key_person\nx\n")
    (c / "chadwick" / "names.csv").write_text("n\n")
    _pq(c / "chadwick" / "people.parquet", {"key_person": ["x"]})
    _manifest(c / "chadwick" / "manifest.json", {"commit_sha": {**_entry(1), "sha": "abc"}})

    # mlb_api: schedule gives game_pk -> season for boxscores
    _pq(c / "mlb_api" / "schedule" / "schedule_2024.parquet", {"game_pk": [100], "season": [2024]})
    _pq(c / "mlb_api" / "teams" / "teams_mlb.parquet", {"team_id": [1]})
    _pq(c / "mlb_api" / "boxscores_batting" / "100.parquet", {"game_pk": [100]})
    _pq(c / "mlb_api" / "boxscores_pitching" / "100.parquet", {"game_pk": [100]})
    _pq(c / "mlb_api" / "boxscores_batting" / "999.parquet", {"game_pk": [999]})  # unknown season
    _manifest(
        c / "mlb_api" / "manifest.json",
        {
            "schedule_2024": _entry(1),
            "teams_mlb": _entry(1),
            "box_100": {**_entry(2), "final": True},
        },
    )

    # a stray file nobody maps
    (c / "statcast" / "notes.txt").write_text("hello")
    return cfg


def test_dry_run_changes_nothing_and_reports_plan(v1: LakeConfig) -> None:
    before = sorted(p for p in v1.home.rglob("*"))
    report = migrate.migrate_layout(v1, dry_run=True)
    assert report.dry_run
    assert len(report.steps) >= 20
    assert [p.name for p in report.unknown if p.name == "notes.txt"] == ["notes.txt"]
    assert sorted(p for p in v1.home.rglob("*")) == before
    assert not v1.version_file.exists()


def test_full_migration_maps_every_dataset_and_verifies_rows(v1: LakeConfig) -> None:
    report = migrate.migrate_layout(v1)
    assert report.version_written and v1.version_file.read_text().strip() == "2"
    raw, proc = v1.raw_root, v1.processed_root

    assert (proc / "statcast/pitches/season=2024/part-2024-04-01_2024-04-05.parquet").exists()
    assert (proc / "statcast/pitches/season=2023/part-2023-04-01_2023-04-05.parquet").exists()
    assert (
        proc / "statcast/leaderboard_bat_tracking/season=2024/part-bat_tracking_2024.parquet"
    ).exists()
    assert (
        proc
        / "statcast/leaderboard_expected_statistics/season=2024"
        / "part-expected_statistics_2024_type-batter.parquet"
    ).exists()
    assert (raw / "retrosheet/event_files/season=2023/2023BOS.EVA").exists()
    assert (raw / "retrosheet/event_files/season=2023/TEAM2023").exists()
    assert (raw / "retrosheet/rosters/season=2023/BOS2023.ROS").exists()
    assert (raw / "retrosheet/gamelogs/season=2023/GL2023.TXT").exists()
    assert (raw / "retrosheet/reference_teams/teams.csv").exists()
    assert (proc / "retrosheet/events/season=2023/part-events.parquet").exists()
    assert (proc / "retrosheet/boxscores_batting/season=2023/part-batting.parquet").exists()
    assert (proc / "retrosheet/gamelogs/season=2023/part-gl2023.parquet").exists()
    assert (proc / "retrosheet/gamelogs_postseason/part-world_series.parquet").exists()
    assert (proc / "retrosheet/rosters/season=2023/part-rosters_2023.parquet").exists()
    assert (proc / "retrosheet/reference_teams/part-data.parquet").exists()
    assert (raw / "lahman/Batting/Batting.csv").exists()
    assert (proc / "lahman/Batting/part-data.parquet").exists()
    assert (raw / "chadwick/register/people-0.csv").exists()
    assert (raw / "chadwick/register_names/names.csv").exists()
    assert (proc / "chadwick/register/part-data.parquet").exists()
    assert (proc / "mlb_api/schedule/season=2024/part-schedule_2024.parquet").exists()
    assert (proc / "mlb_api/teams/part-teams_mlb.parquet").exists()
    assert (proc / "mlb_api/box_batting/season=2024/part-100.parquet").exists()
    assert (proc / "mlb_api/box_pitching/season=2024/part-100.parquet").exists()
    assert not (proc / "mlb_api/box_batting/season=2024/part-999.parquet").exists()

    unknown = {p.name for p in report.unknown}
    assert unknown == {"notes.txt", "999.parquet"}
    assert report.rows_verified > 0


def test_events_all_is_deduplicated_into_events_postseason(v1: LakeConfig) -> None:
    report = migrate.migrate_layout(v1)
    post = pq.read_table(
        v1.processed_dir("retrosheet", "events_postseason", 2023) / "part-events.parquet"
    )
    assert post["GAME_ID"].to_pylist() == ["P"]
    assert report.postseason_duplicate_rows_dropped == 2
    catalog.register_all()
    con = BaseballDatabase(db_path=":memory:", cache_config=v1).connect()
    assert con.execute("SELECT count(*) FROM retrosheet_events").fetchone() == (2,)
    assert con.execute("SELECT count(*) FROM retrosheet_events_postseason").fetchone() == (1,)


def test_manifest_entries_are_carried_so_freshness_survives(v1: LakeConfig) -> None:
    migrate.migrate_layout(v1)
    statcast = v1.dataset_manifest("statcast", "pitches").get_chunk(
        "season=2024/2024-04-01_2024-04-05"
    )
    assert statcast is not None and statcast["fetched_at"] == "2024-01-01T00:00:00+00:00"
    assert v1.dataset_manifest("lahman", "Batting", "raw").is_completed("Batting")
    sha = v1.dataset_manifest("chadwick", "register", "raw").get_chunk("commit_sha")
    assert sha is not None and sha["sha"] == "abc"
    assert v1.dataset_manifest("retrosheet", "event_files", "raw").is_completed("season_2023")
    assert v1.dataset_manifest("retrosheet", "events").is_completed("season=2023/events")
    box = v1.dataset_manifest("mlb_api", "box_batting").get_chunk("box_100")
    assert box is not None and box["final"] is True
    assert v1.dataset_manifest("statcast", "leaderboard_bat_tracking").is_completed(
        "season=2024/bat_tracking_2024"
    )


def test_migration_is_idempotent(v1: LakeConfig) -> None:
    first = migrate.migrate_layout(v1)
    assert first.copied
    second = migrate.migrate_layout(v1)
    assert not second.copied or all(s.kind == "events_postseason" for s in second.copied)
    assert len(second.skipped) >= len(first.copied) - 1
    # processed data is unchanged by the second run
    post = pq.read_table(
        v1.processed_dir("retrosheet", "events_postseason", 2023) / "part-events.parquet"
    )
    assert post.num_rows == 1


def test_v1_data_is_never_deleted_unless_requested(v1: LakeConfig) -> None:
    migrate.migrate_layout(v1)
    assert (v1.home / "cache/statcast/season=2024/2024-04-01_2024-04-05.parquet").exists()

    report = migrate.migrate_layout(v1, delete_old=True)
    assert report.deleted_files > 0
    assert not (v1.home / "cache/statcast/season=2024/2024-04-01_2024-04-05.parquet").exists()
    assert (v1.home / "cache/statcast/notes.txt").exists()  # unknown files are never touched
    assert (v1.processed_root / "statcast/pitches/season=2024").exists()


def test_corrupt_copy_aborts_without_version_stamp(
    v1: LakeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = migrate._sha256
    calls = {"n": 0}

    def flaky(path: Path) -> str:
        calls["n"] += 1
        return "bad" if calls["n"] == 4 else real(path)

    monkeypatch.setattr(migrate, "_sha256", flaky)
    with pytest.raises(migrate.MigrationError):
        migrate.migrate_layout(v1)
    assert not v1.version_file.exists()
    assert (v1.home / "cache/statcast/season=2024/2024-04-01_2024-04-05.parquet").exists()


def test_empty_lake_needs_no_migration(tmp_path: Path) -> None:
    cfg = LakeConfig(home=tmp_path)
    report = migrate.migrate_layout(cfg)
    assert not report.steps and not report.version_written
    assert layout.detect_layout(cfg) is None


def test_detect_layout_and_first_use_hint_logged_once(
    v1: LakeConfig, caplog: pytest.LogCaptureFixture
) -> None:
    layout.reset_hints()
    assert layout.detect_layout(v1) == 1
    with caplog.at_level(logging.WARNING, logger="baseballpy.core.layout"):
        ProcessedStore(v1)
        ProcessedStore(v1)
    hints = [r for r in caplog.records if "migrate-layout" in r.getMessage()]
    assert len(hints) == 1
    assert not v1.version_file.exists()  # nothing auto-moved or stamped
    migrate.migrate_layout(v1)
    assert layout.detect_layout(v1) == 2


def test_fresh_lake_is_stamped_v2_on_first_write(tmp_path: Path) -> None:
    from baseballpy.core.datasets import get_dataset

    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    ProcessedStore(cfg).put(get_dataset("lahman", "People"), pa.table({"playerID": ["a"]}))
    assert layout.detect_layout(cfg) == 2


def test_public_api_exposes_migrate_layout(v1: LakeConfig) -> None:
    report = public_migrate_layout(v1, dry_run=True)
    assert report.dry_run


def test_migrated_raw_files_get_manifest_entries_so_the_downloader_skips_them(
    v1: LakeConfig,
) -> None:
    migrate.migrate_layout(v1)
    entry = v1.dataset_manifest("retrosheet", "event_files", "raw", 2023).get_chunk("2023BOS.EVA")
    assert entry is not None and entry["bytes"] == 8 and len(entry["sha256"]) == 64
    assert entry["source_ref"] is None and entry["migrated_from"] == "v1"
    gl = v1.dataset_manifest("retrosheet", "gamelogs", "raw", 2023).get_chunk("GL2023.TXT")
    assert gl is not None and gl["season"] == 2023
