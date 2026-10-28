"""Backfill: plan files, the disk budget, and resuming an interrupted plan with the real adapter."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import LakeConfig
from baseballpy.ingest.backfill import (
    GB,
    BackfillError,
    load_plan,
    parse_plan,
    plan_stage,
    preflight,
    run_backfill,
)
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job
from baseballpy.sources.lahman.adapter import LahmanAdapter
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.lahman.extractor import LAHMAN_GITHUB_BASE

PEOPLE_CSV = (
    "playerID,birthYear,nameFirst,nameLast\n"
    "ohtansh01,1994,Shohei,Ohtani\n"
    "judgaa01,1992,Aaron,Judge\n"
)
BATTING_CSV = (
    "playerID,yearID,stint,teamID,lgID,G,AB,R,H,2B,3B,HR,RBI,SB,CS,BB,SO,IBB,HBP,SH,SF,GIDP\n"
    "ohtansh01,2024,1,LAD,NL,159,636,134,197,38,7,54,130,59,4,81,162,20,6,0,5,5\n"
)


class FakeAdapter:
    """Plans one job per season; each run costs ``cost`` bytes of the fake disk."""

    source = "fake"

    def __init__(self, disk: list[int], cost: int = 0, fail_on: int | None = None) -> None:
        self.disk = disk
        self.cost = cost
        self.fail_on = fail_on
        self.ran: list[int] = []

    def all_seasons(self) -> Sequence[int]:
        return [2000, 2001, 2002]

    def plan(self, selection: Selection) -> list[Job]:
        return [make_job("fake", "season", season=s) for s in selection.seasons]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        season = int(job.param("season") or 0)
        if season == self.fail_on:
            raise KeyboardInterrupt
        self.ran.append(season)
        self.disk[0] -= self.cost
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=10)


PLAN: dict[str, Any] = {
    "stage": [
        {"name": "a", "sources": ["fake"], "seasons": "2000-2001", "estimate_gb": 1},
        {"name": "b", "sources": ["fake"], "seasons": "2002", "estimate_gb": 1},
    ]
}


def test_plan_file_is_read_and_validated(tmp_path: Path) -> None:
    path = tmp_path / "plan.toml"
    path.write_text(
        '[[stage]]\nname = "x"\nsources = ["lahman"]\nestimate_gb = 0.5\n'
        '[[stage]]\nsources = ["statcast"]\nseasons = "2015-2016"\nlimit = 3\n',
        encoding="utf-8",
    )
    plan = load_plan(path)
    assert [s.name for s in plan.stages] == ["x", "stage 2"]
    assert plan.stages[1].limit == 3
    assert plan.estimate_gb == 0.5


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"stage": []},
        {"stage": [{"sources": []}]},
        {"stage": [{"sources": ["a"], "colour": 1}]},
        {"stage": [{"sources": ["a"], "seasons": "2024-2015"}]},
        {"stage": [{"sources": ["a"], "limit": 0}]},
        {"stage": [{"sources": ["a"], "estimate_gb": -1}]},
    ],
)
def test_bad_plans_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(BackfillError):
        parse_plan(bad)


def test_the_disk_preflight_refuses_a_plan_that_does_not_fit() -> None:
    plan = parse_plan(PLAN)
    preflight(plan, 10 * GB, min_free_gb=5)
    with pytest.raises(BackfillError, match="not enough free space"):
        preflight(plan, 6 * GB, min_free_gb=5)


def test_datasets_are_routed_to_their_source() -> None:
    plan = parse_plan({"stage": [{"sources": ["fake", "other"], "datasets": ["fake:x"]}]})
    with pytest.raises(BackfillError, match="unknown source"):
        plan_stage(plan.stages[0], {"fake": FakeAdapter([0])}, refresh=False)
    ambiguous = parse_plan({"stage": [{"sources": ["fake", "other"], "datasets": ["x"]}]})
    with pytest.raises(BackfillError, match="ambiguous"):
        plan_stage(
            ambiguous.stages[0],
            {"fake": FakeAdapter([0]), "other": FakeAdapter([0])},
            refresh=False,
        )


def test_max_gb_stops_the_run_after_the_batch_that_crossed_it() -> None:
    disk = [100 * GB]
    adapter = FakeAdapter(disk, cost=GB)
    report = run_backfill(
        parse_plan(PLAN),
        {"fake": adapter},
        free_bytes=lambda: disk[0],
        max_gb=1.5,
        min_free_gb=0,
    )
    assert adapter.ran == [2000, 2001]
    assert "--max-gb 1.5 reached" in report.stopped
    assert report.exit_code == 2
    assert report.grown_bytes == 2 * GB
    assert [s.grown_bytes for s in report.stages] == [2 * GB, 0]


def test_the_run_stops_when_free_space_falls_below_the_floor() -> None:
    disk = [6 * GB]
    adapter = FakeAdapter(disk, cost=2 * GB)
    report = run_backfill(
        parse_plan({"stage": [{"sources": ["fake"], "seasons": "2000-2002"}]}),
        {"fake": adapter},
        free_bytes=lambda: disk[0],
        min_free_gb=5,
    )
    assert adapter.ran == [2000]
    assert "free space fell below" in report.stopped


def test_an_interrupted_run_is_cancelled_and_a_rerun_finishes_the_rest() -> None:
    disk = [100 * GB]
    first = FakeAdapter(disk, fail_on=2001)
    report = run_backfill(
        parse_plan(PLAN), {"fake": first}, free_bytes=lambda: disk[0], min_free_gb=0
    )
    assert first.ran == [2000]
    assert report.stopped == "interrupted"
    assert report.exit_code == 130
    assert [s.stage.name for s in report.stages] == ["a"]


@respx.mock
def test_resume_with_the_real_adapter_fetches_only_what_is_incomplete(tmp_path: Path) -> None:
    class CtrlCOnPeople(LahmanAdapter):
        """Ctrl-C arrives in the main thread, before the People download starts."""

        armed = True

        def run(self, job: Job, *, refresh: bool = False) -> JobResult:
            if self.armed and job.param("name") == "People":
                self.armed = False
                raise KeyboardInterrupt
            return super().run(job, refresh=refresh)

    adapter = CtrlCOnPeople(source=LahmanSource(cache_config=LakeConfig(home=tmp_path)))
    plan = parse_plan({"stage": [{"sources": ["lahman"], "datasets": ["Batting", "People"]}]})
    batting = respx.get(f"{LAHMAN_GITHUB_BASE}/Batting.csv").mock(
        return_value=httpx.Response(200, content=BATTING_CSV.encode())
    )
    people = respx.get(f"{LAHMAN_GITHUB_BASE}/People.csv").mock(
        return_value=httpx.Response(200, content=PEOPLE_CSV.encode())
    )

    first = run_backfill(plan, {"lahman": adapter}, free_bytes=lambda: 100 * GB, min_free_gb=0)
    assert first.exit_code == 130
    assert (batting.call_count, people.call_count) == (1, 0)

    second = run_backfill(plan, {"lahman": adapter}, free_bytes=lambda: 100 * GB, min_free_gb=0)
    assert second.exit_code == 0
    assert batting.call_count == 1, "the finished table is served from the lake, not fetched again"
    assert people.call_count == 1
    assert second.stages[0].count(JobStatus.COMPLETED) == 2


def test_the_cli_dry_run_plans_without_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    path = tmp_path / "plan.toml"
    path.write_text(
        '[[stage]]\nname = "tables"\nsources = ["lahman"]\ndatasets = ["Batting"]\nestimate_gb = 0.1\n',
        encoding="utf-8",
    )
    result = CliRunner().invoke(main, ["backfill", str(path), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "tables" in result.output
    assert "1 job(s)" in result.output
    assert not (tmp_path / "raw").exists()


def test_the_cli_refuses_a_bad_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    path = tmp_path / "plan.toml"
    path.write_text('[[stage]]\nsources = ["nosuchsource"]\n', encoding="utf-8")
    result = CliRunner().invoke(main, ["backfill", str(path), "--dry-run"])
    assert result.exit_code != 0
    assert "nosuchsource" in result.output
