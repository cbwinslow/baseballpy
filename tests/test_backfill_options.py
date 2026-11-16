"""Plan stages carry source options and run seasons newest first; the built-in plans for every level of MLB games."""

from collections.abc import Sequence
from typing import Any

import pytest

from baseballpy.ingest.backfill import (
    BackfillError,
    builtin_plans,
    load_plan,
    parse_plan,
    plan_stage,
)
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job


class Recorder:
    """Plans one job per season and keeps the selection it was given."""

    source = "fake"

    def __init__(self) -> None:
        self.selections: list[Selection] = []

    def all_seasons(self) -> Sequence[int]:
        return [2000, 2001, 2002]

    def plan(self, selection: Selection) -> list[Job]:
        self.selections.append(selection)
        return [make_job("fake", "season", season=s) for s in selection.seasons]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)


def _stage(**extra: Any) -> Any:
    return parse_plan(
        {"stage": [{"name": "s", "sources": ["fake"], "seasons": "2000-2002", **extra}]}
    ).stages[0]


def test_stage_options_reach_the_adapter_as_option_pairs() -> None:
    recorder = Recorder()
    plan_stage(
        _stage(options={"sports": "all", "storage_note": "x"}), {"fake": recorder}, refresh=False
    )
    assert recorder.selections[0].options == (("sports", "all"), ("storage_note", "x"))
    assert recorder.selections[0].option("sports") == "all"


def test_a_stage_without_options_passes_none() -> None:
    recorder = Recorder()
    plan_stage(_stage(), {"fake": recorder}, refresh=False)
    assert recorder.selections[0].options == ()


@pytest.mark.parametrize(
    "bad",
    [
        {"options": ["sports=all"]},
        {"options": {"sports": ["all"]}},
        {"options": {"": "x"}},
        {"options": "sports=all"},
    ],
)
def test_bad_options_are_refused(bad: dict[str, Any]) -> None:
    with pytest.raises(BackfillError, match="options"):
        _stage(**bad)


def test_numbers_and_booleans_in_options_become_text() -> None:
    recorder = Recorder()
    plan_stage(_stage(options={"download": True, "levels": 3}), {"fake": recorder}, refresh=False)
    assert dict(recorder.selections[0].options) == {"download": "true", "levels": "3"}


def test_seasons_of_a_stage_run_newest_first() -> None:
    recorder = Recorder()
    jobs = plan_stage(_stage(), {"fake": recorder}, refresh=False)
    assert [int(j.param("season") or 0) for j in jobs] == [2002, 2001, 2000]


def test_the_oldest_first_order_can_be_asked_for() -> None:
    recorder = Recorder()
    jobs = plan_stage(_stage(order="oldest-first"), {"fake": recorder}, refresh=False)
    assert [int(j.param("season") or 0) for j in jobs] == [2000, 2001, 2002]
    with pytest.raises(BackfillError, match="order"):
        _stage(order="sideways")


def test_the_built_in_plans_for_minor_leagues_load_and_ask_for_every_level() -> None:
    assert {"daily", "full", "minors", "minors-all"} <= set(builtin_plans())
    for name, first in (("minors", 2021), ("minors-all", 2008)):
        plan = load_plan(name)
        stage = next(s for s in plan.stages if "mlb_api" in s.sources)
        assert dict(stage.options).get("sports") == "all" and stage.seasons == f"{first}-current"
        assert stage.estimate_gb > 0
