"""Tests for CLI ingest, catalog status, and doctor commands."""

import json
from collections.abc import Generator, Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from baseballpy.cli import catalog, main
from baseballpy.cli_ingest import find_orphans, register_commands, scan_lake
from baseballpy.core.config import LakeConfig, reset_config
from baseballpy.ingest.adapters import ADAPTERS
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

register_commands(main, catalog)


@pytest.fixture(autouse=True)
def isolated_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Isolate lake home directory and restore adapter registry."""
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    reset_config()
    saved_adapters = dict(ADAPTERS)
    yield
    ADAPTERS.clear()
    ADAPTERS.update(saved_adapters)
    reset_config()


class SpyAdapter:
    """Test adapter tracking run invocations."""

    source = "spy_source"

    def __init__(self) -> None:
        self.calls: list[Job] = []

    def all_seasons(self) -> Sequence[int]:
        return [2023]

    def plan(self, selection: Selection) -> list[Job]:
        seasons = selection.seasons or (2023,)
        return [make_job(self.source, "pitches", season=s) for s in seasons]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        self.calls.append(job)
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=100, seconds=0.05)


class MultiOutcomeAdapter:
    """Test adapter returning completed and skipped job outcomes."""

    source = "multi_source"

    def all_seasons(self) -> Sequence[int]:
        return [2021, 2022]

    def plan(self, selection: Selection) -> list[Job]:
        return [
            make_job(self.source, "completed_task", season=2021),
            make_job(self.source, "skipped_task", season=2022),
        ]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        if job.task == "completed_task":
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=42, seconds=0.1)
        return JobResult(
            job=job, status=JobStatus.SKIPPED, rows=None, seconds=0.01, detail="already complete"
        )


class FailingAdapter:
    """Test adapter returning a failed job result."""

    source = "failing_source"

    def all_seasons(self) -> Sequence[int]:
        return [2023]

    def plan(self, selection: Selection) -> list[Job]:
        return [make_job(self.source, "bad_task", season=2023)]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        return JobResult(
            job=job,
            status=JobStatus.FAILED,
            rows=None,
            seconds=0.02,
            error="simulated failure",
            detail="detail error",
        )


def test_dry_run_makes_zero_run_calls() -> None:
    spy = SpyAdapter()
    ADAPTERS["spy_source"] = lambda: spy

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "spy_source", "--dry-run", "--seasons", "2023"])

    assert result.exit_code == 0, result.output
    assert len(spy.calls) == 0
    assert "planned" in result.output
    assert "spy_source" in result.output


def test_real_run_completed_and_skipped_exit_code_zero() -> None:
    adapter = MultiOutcomeAdapter()
    ADAPTERS["multi_source"] = lambda: adapter

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "multi_source", "--seasons", "2021,2022"])

    assert result.exit_code == 0, result.output
    assert "completed" in result.output
    assert "skipped" in result.output
    assert "42" in result.output


def test_real_run_failing_sets_exit_code_one() -> None:
    adapter = FailingAdapter()
    ADAPTERS["failing_source"] = lambda: adapter

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "failing_source", "--seasons", "2023"])

    assert result.exit_code == 1, result.output
    assert "failed" in result.output


def test_ingest_json_output_parses_line_by_line() -> None:
    adapter = MultiOutcomeAdapter()
    ADAPTERS["multi_source"] = lambda: adapter

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "multi_source", "--seasons", "2021,2022", "--json"])

    assert result.exit_code == 0, result.output
    lines = [json.loads(line) for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 2

    assert lines[0]["status"] == "completed"
    assert lines[0]["rows"] == 42
    assert "job_id" in lines[0]
    assert "seconds" in lines[0]

    assert lines[1]["status"] == "skipped"
    assert lines[1]["rows"] is None
    assert lines[1]["detail"] == "already complete"


def test_dry_run_json_output_parses_line_by_line() -> None:
    spy = SpyAdapter()
    ADAPTERS["spy_source"] = lambda: spy

    runner = CliRunner()
    result = runner.invoke(
        main, ["ingest", "spy_source", "--dry-run", "--json", "--seasons", "2023"]
    )

    assert result.exit_code == 0, result.output
    assert len(spy.calls) == 0
    lines = [json.loads(line) for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["status"] == "planned"
    assert lines[0]["rows"] is None


def test_bad_seasons_exits_code_two() -> None:
    spy = SpyAdapter()
    ADAPTERS["spy_source"] = lambda: spy

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "spy_source", "--seasons", "invalid-season"])

    assert result.exit_code == 2
    assert "non-numeric" in result.output or "Error:" in result.output


def test_unknown_source_exits_code_two() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "totally_nonexistent_source"])

    assert result.exit_code == 2
    assert "unknown source" in result.output or "Error:" in result.output


def test_ingest_no_jobs_exits_zero() -> None:
    class EmptyAdapter:
        source = "empty_source"

        def all_seasons(self) -> Sequence[int]:
            return []

        def plan(self, selection: Selection) -> list[Job]:
            return []

        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            return JobResult(job=job, status=JobStatus.COMPLETED)

    ADAPTERS["empty_source"] = lambda: EmptyAdapter()

    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "empty_source"])
    assert result.exit_code == 0
    assert "No jobs to run" in result.output


def test_scan_lake_and_catalog_status_fabricated_parquet(tmp_path: Path) -> None:
    lake_cfg = LakeConfig()
    target_dir = lake_cfg.processed_dir("statcast", "pitches", season=2023)
    target_dir.mkdir(parents=True, exist_ok=True)

    dummy_table = pa.table({"col1": [1, 2, 3, 4, 5, 6, 7]})
    pq.write_table(dummy_table, target_dir / "data.parquet")

    statuses = scan_lake(lake_cfg)
    statcast_status = next(s for s in statuses if s.source == "statcast" and s.dataset == "pitches")
    assert statcast_status.status == "INGESTED"
    assert statcast_status.rows == 7
    assert statcast_status.files == 1
    assert statcast_status.seasons == (2023,)

    missing_status = next(s for s in statuses if s.source == "lahman" and s.dataset == "People")
    assert missing_status.status == "MISSING"
    assert missing_status.rows == 0
    assert missing_status.files == 0

    runner = CliRunner()
    cli_res = runner.invoke(main, ["catalog", "status"])
    assert cli_res.exit_code == 0, cli_res.output
    assert "INGESTED" in cli_res.output
    assert "MISSING" in cli_res.output
    assert "2023" in cli_res.output
    assert "7" in cli_res.output


def test_catalog_status_missing_filter(tmp_path: Path) -> None:
    lake_cfg = LakeConfig()
    target_dir = lake_cfg.processed_dir("statcast", "pitches", season=2023)
    target_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"id": [1, 2]}), target_dir / "test.parquet")

    runner = CliRunner()
    res = runner.invoke(main, ["catalog", "status", "--missing"])
    assert res.exit_code == 0, res.output
    assert "MISSING" in res.output
    assert "INGESTED" not in res.output


def test_catalog_status_source_filter() -> None:
    runner = CliRunner()
    res = runner.invoke(main, ["catalog", "status", "--source", "statcast"])
    assert res.exit_code == 0, res.output
    assert "statcast" in res.output
    assert "lahman" not in res.output


def test_catalog_status_json_output(tmp_path: Path) -> None:
    lake_cfg = LakeConfig()
    target_dir = lake_cfg.processed_dir("statcast", "pitches", season=2024)
    target_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"x": [10, 20]}), target_dir / "data.parquet")

    runner = CliRunner()
    res = runner.invoke(main, ["catalog", "status", "--json"])
    assert res.exit_code == 0, res.output
    json_lines = [json.loads(line) for line in res.output.strip().splitlines() if line.strip()]
    assert len(json_lines) > 0

    pitches_item = next(
        item for item in json_lines if item["source"] == "statcast" and item["dataset"] == "pitches"
    )
    assert pitches_item["status"] == "INGESTED"
    assert pitches_item["rows"] == 2
    assert pitches_item["seasons"] == [2024]
    assert pitches_item["newest_mtime"] is not None


def test_doctor_finds_and_clean_removes_only_part_files(tmp_path: Path) -> None:
    lake_cfg = LakeConfig()
    raw_sub = lake_cfg.raw_root / "statcast" / "pitches"
    raw_sub.mkdir(parents=True, exist_ok=True)

    orphan_file = raw_sub / "x.parquet.part"
    orphan_file.write_text("in-flight stream", encoding="utf-8")

    keep_file = raw_sub / "keep.txt"
    keep_file.write_text("do not delete me", encoding="utf-8")

    orphans = find_orphans(lake_cfg)
    assert orphan_file in orphans
    assert keep_file not in orphans

    runner = CliRunner()
    res_doc = runner.invoke(main, ["doctor"])
    assert res_doc.exit_code == 1, res_doc.output
    assert "x.parquet.part" in res_doc.output
    assert orphan_file.exists()
    assert keep_file.exists()

    res_clean = runner.invoke(main, ["doctor", "--clean"])
    assert res_clean.exit_code == 0, res_clean.output
    assert not orphan_file.exists()
    assert keep_file.exists()
    assert keep_file.read_text(encoding="utf-8") == "do not delete me"

    res_doc_again = runner.invoke(main, ["doctor"])
    assert res_doc_again.exit_code == 0, res_doc_again.output


def test_doctor_json_output() -> None:
    runner = CliRunner()
    res = runner.invoke(main, ["doctor", "--json"])
    assert res.exit_code == 0, res.output
    doc_json = json.loads(res.output)

    assert "lake" in doc_json
    assert "home" in doc_json["lake"]
    assert "raw_root" in doc_json["lake"]
    assert "processed_root" in doc_json["lake"]
    assert "disk" in doc_json
    assert "free_bytes" in doc_json["disk"]
    assert "versions" in doc_json
    assert "python" in doc_json["versions"]
    assert "pyarrow" in doc_json["versions"]
    assert "duckdb" in doc_json["versions"]
    assert "baseballpy" in doc_json["versions"]
    assert "registered_datasets" in doc_json
    assert "registered_adapters" in doc_json
    assert "orphans" in doc_json
    assert doc_json["orphans"]["count"] == 0


def test_split_datasets_needs_source_prefix_when_ambiguous() -> None:
    import click

    from baseballpy.cli_ingest import split_datasets

    assert split_datasets(("gamelogs,box_accounts",), ("retrosheet",)) == {
        "retrosheet": ("gamelogs", "box_accounts")
    }
    assert split_datasets(("lahman:People", "retrosheet:gamelogs"), ("lahman", "retrosheet")) == {
        "lahman": ("People",),
        "retrosheet": ("gamelogs",),
    }
    with pytest.raises(click.BadParameter, match="ambiguous"):
        split_datasets(("People",), ("lahman", "retrosheet"))
    with pytest.raises(click.BadParameter, match="not selected"):
        split_datasets(("mlb_api:season",), ("lahman",))


def _status_lines(*args: str) -> list[dict[str, object]]:
    res = CliRunner().invoke(main, ["catalog", "status", "--json", *args])
    assert res.exit_code == 0, res.output
    return [json.loads(line) for line in res.output.strip().splitlines() if line.strip()]


def test_catalog_status_labels_why_a_dataset_is_not_ingested() -> None:
    rows = {(r["source"], r["dataset"]): r for r in _status_lines()}
    assert rows[("mlb_api", "game_play_by_play")]["ingest"] == "opt_in"
    assert rows[("mlb_api", "people_stats_season_hitting")]["ingest"] == "opt_in"
    assert rows[("mlb_api", "people_changes")]["ingest"] == "on_demand"
    assert rows[("mlb_api", "venues")]["ingest"] == "api_only"
    assert rows[("mlb_api", "teams_season")]["ingest"] == "default"
    assert "1968" in str(rows[("retrosheet", "events_deduced")]["note"])
    for row in rows.values():
        if row["ingest"] in ("opt_in", "on_demand", "api_only"):
            assert row["note"], f"{row['source']}.{row['dataset']} has no ingest note"


def test_catalog_status_gaps_only_lists_default_datasets() -> None:
    gaps = _status_lines("--gaps")
    assert gaps
    assert {g["ingest"] for g in gaps} == {"default"}
    assert {g["status"] for g in gaps} == {"MISSING"}
    assert len(gaps) < len(_status_lines("--missing"))


def test_catalog_status_gaps_shrinks_when_a_default_dataset_is_ingested() -> None:
    before = {(g["source"], g["dataset"]) for g in _status_lines("--gaps")}
    target = LakeConfig().processed_dir("chadwick", "register_names")
    target.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"x": [1]}), target / "data.parquet")
    after = {(g["source"], g["dataset"]) for g in _status_lines("--gaps")}
    assert ("chadwick", "register_names") in before
    assert after == before - {("chadwick", "register_names")}


def test_catalog_status_table_shows_the_note_for_missing_rows() -> None:
    res = CliRunner().invoke(main, ["catalog", "status", "--source", "retrosheet", "--missing"])
    assert res.exit_code == 0, res.output
    assert "1968" in res.output or "ED" in res.output


def test_catalog_show_reports_the_ingest_mode() -> None:
    res = CliRunner().invoke(main, ["catalog", "show", "mlb_api.venues", "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.output)
    assert data["ingest"] == "api_only"
    assert data["ingest_note"]


def test_limit_option_reaches_the_planned_opt_in_jobs() -> None:
    result = CliRunner().invoke(
        main,
        [
            "ingest",
            "mlb_api",
            "--seasons",
            "2023",
            "--datasets",
            "games,people_stats",
            "--limit",
            "5",
            "--dry-run",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    ids = [json.loads(line)["job_id"] for line in result.output.strip().splitlines()]
    assert "mlb_api:people_stats:limit=5:season=2023" in ids
    assert any(i.startswith("mlb_api:season:games=True:limit=5") for i in ids)


def test_limit_must_be_positive() -> None:
    result = CliRunner().invoke(main, ["ingest", "mlb_api", "--limit", "0", "--dry-run"])
    assert result.exit_code == 2
