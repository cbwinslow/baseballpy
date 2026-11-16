"""The Python interface: baseballpy.download, update and backfill do what the commands do, in one call."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

import baseballpy as bp
from baseballpy import easy as api
from baseballpy.core.config import LakeConfig
from baseballpy.ingest.backfill import GB, BackfillError, parse_plan
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job


class Fake:
    """One job per season; keeps what it was asked and the order it ran in."""

    def __init__(self, name: str = "fake", fail: bool = False) -> None:
        self.source = name
        self.fail = fail
        self.selections: list[Selection] = []
        self.ran: list[int] = []

    def all_seasons(self) -> Sequence[int]:
        return [2000, 2001, 2002]

    def plan(self, selection: Selection) -> list[Job]:
        self.selections.append(selection)
        seasons = selection.seasons or (0,)
        return [make_job(self.source, "season", season=s) for s in seasons]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        self.ran.append(int(job.param("season") or 0))
        status = JobStatus.FAILED if self.fail else JobStatus.COMPLETED
        return JobResult(job=job, status=status, rows=5, error="boom" if self.fail else None)


@pytest.fixture
def synced(monkeypatch: pytest.MonkeyPatch) -> list[LakeConfig | None]:
    """Replaces the DuckDB sync and records how often it was asked for."""
    calls: list[LakeConfig | None] = []
    monkeypatch.setattr(
        api, "sync_database", lambda cache_config=None: calls.append(cache_config) or 1
    )
    return calls


def test_the_functions_are_at_the_top_of_the_package() -> None:
    assert bp.download is api.download and bp.update is api.update and bp.backfill is api.backfill


def test_download_runs_the_seasons_newest_first_and_returns_the_report(synced: list[Any]) -> None:
    fake = Fake()
    report = bp.download("fake", seasons="2000-2002", adapters={"fake": fake})
    assert fake.ran == [2002, 2001, 2000]
    assert [r.status for r in report.results] == [JobStatus.COMPLETED] * 3 and report.exit_code == 0


@pytest.mark.parametrize(
    ("seasons", "expected"), [(2001, [2001]), ([2000, 2002], [2002, 2000]), ("2001", [2001])]
)
def test_seasons_may_be_a_year_a_list_or_text(
    seasons: Any, expected: list[int], synced: list[Any]
) -> None:
    fake = Fake()
    bp.download("fake", seasons=seasons, adapters={"fake": fake})
    assert fake.ran == expected


def test_datasets_options_and_refresh_reach_the_adapter(synced: list[Any]) -> None:
    fake = Fake()
    bp.download(
        "fake",
        seasons=2001,
        datasets=["games"],
        refresh=True,
        adapters={"fake": fake},
        sports="all",
        levels=3,
    )
    selection = fake.selections[0]
    assert selection.datasets == ("games",) and selection.refresh is True
    assert dict(selection.options) == {"sports": "all", "levels": "3"}


def test_an_unknown_source_is_a_clear_error_that_lists_the_known_ones() -> None:
    with pytest.raises(ValueError, match="unknown source 'nope'.*statcast"):
        bp.download("nope", seasons=2024)


def test_the_views_are_synced_after_a_download_that_stored_something(
    synced: list[Any], tmp_path: Path
) -> None:
    config = LakeConfig(home=tmp_path)
    bp.download("fake", seasons=2001, adapters={"fake": Fake()}, config=config)
    assert synced == [config]


def test_nothing_is_synced_when_every_job_failed_or_sync_is_off(synced: list[Any]) -> None:
    report = bp.download("fake", seasons=2001, adapters={"fake": Fake(fail=True)})
    assert report.exit_code == 1 and synced == []
    bp.download("fake", seasons=2001, adapters={"fake": Fake()}, sync=False)
    assert synced == []


def test_backfill_runs_a_plan_object_with_the_disk_guard(synced: list[Any]) -> None:
    fake = Fake()
    plan = parse_plan(
        {"stage": [{"name": "a", "sources": ["fake"], "seasons": "2000-2001", "estimate_gb": 1}]}
    )
    report = bp.backfill(plan, adapters={"fake": fake}, free_bytes=lambda: 50 * GB)
    assert fake.ran == [2001, 2000] and report.exit_code == 0 and report.stages[0].planned == 2
    with pytest.raises(BackfillError, match="not enough free space"):
        bp.backfill(plan, adapters={"fake": fake}, free_bytes=lambda: 3 * GB, min_free_gb=5)


def test_backfill_dry_run_plans_and_runs_nothing(synced: list[Any]) -> None:
    fake = Fake()
    plan = parse_plan({"stage": [{"name": "a", "sources": ["fake"], "seasons": "2000-2002"}]})
    report = bp.backfill(plan, adapters={"fake": fake}, free_bytes=lambda: 50 * GB, dry_run=True)
    assert fake.ran == [] and report.stages[0].planned == 3 and report.stages[0].results == []


def test_backfill_takes_the_name_of_a_built_in_plan_and_selects_stages(synced: list[Any]) -> None:
    adapters = {
        name: Fake(name)
        for name in (
            "lahman",
            "chadwick",
            "retrosheet",
            "bref",
            "statcast",
            "mlb_api",
            "kalshi",
            "polymarket",
        )
    }
    report = bp.backfill(
        "full", stages=["reference"], adapters=adapters, free_bytes=lambda: 500 * GB, dry_run=True
    )
    assert [s.stage.name for s in report.stages] == ["reference"]


def test_update_is_the_daily_plan(synced: list[Any]) -> None:
    adapters = {name: Fake(name) for name in ("statcast", "mlb_api", "kalshi", "polymarket")}
    report = bp.update(adapters=adapters, free_bytes=lambda: 50 * GB)
    assert {s.stage.name for s in report.stages} == {"markets", "statcast-current", "mlb-current"}
    assert all(a.ran for a in adapters.values())
