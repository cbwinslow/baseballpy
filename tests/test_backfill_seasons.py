"""Tests for overriding seasons and scaling size estimates in backfill plans."""

import re
from collections.abc import Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner

import baseballpy as bp
from baseballpy.cli import main
from baseballpy.ingest.backfill import (
    GB,
    BackfillError,
    BackfillPlan,
    Stage,
    parse_plan,
    with_seasons,
)
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job


class Recorder:
    """Plans one job per season and records the selections received."""

    source = "fake"

    def __init__(self) -> None:
        self.selections: list[Selection] = []
        self.ran: list[int] = []

    def all_seasons(self) -> Sequence[int]:
        return [2000, 2001, 2002]

    def plan(self, selection: Selection) -> list[Job]:
        self.selections.append(selection)
        seasons = selection.seasons or (0,)
        return [make_job("fake", "season", season=s) for s in seasons]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        self.ran.append(int(job.param("season") or 0))
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=1)


def test_override_replaces_seasons_only_in_stages_that_have_them() -> None:
    s1 = Stage(name="with-seasons", sources=("fake",), seasons="2010-2015", estimate_gb=12.0)
    s2 = Stage(name="without-seasons", sources=("fake",), seasons=None, estimate_gb=1.0)
    plan = BackfillPlan((s1, s2))

    updated = with_seasons(plan, "2014-2015")
    assert updated.stages[0].seasons == "2014-2015"
    assert updated.stages[1].seasons is None


def test_estimate_scales_with_seasons_override() -> None:
    # A 10-season stage at 100 GB overridden to 2 seasons becomes 20 GB
    s_ten = Stage(name="ten", sources=("fake",), seasons="2000-2009", estimate_gb=100.0)
    p_two = with_seasons(BackfillPlan((s_ten,)), "2001-2002")
    assert p_two.stages[0].estimate_gb == pytest.approx(20.0)

    # A stage with "all" keeps its estimate when overridden
    s_all = Stage(name="all-stage", sources=("fake",), seasons="all", estimate_gb=50.0)
    p_all_overridden = with_seasons(BackfillPlan((s_all,)), "2001-2002")
    assert p_all_overridden.stages[0].seasons == "2001-2002"
    assert p_all_overridden.stages[0].estimate_gb == pytest.approx(50.0)

    # Overriding with "all" also keeps estimate unchanged
    p_override_all = with_seasons(BackfillPlan((s_ten,)), "all")
    assert p_override_all.stages[0].seasons == "all"
    assert p_override_all.stages[0].estimate_gb == pytest.approx(100.0)

    # A stage without seasons is untouched
    s_none = Stage(name="no-seasons", sources=("fake",), seasons=None, estimate_gb=15.0)
    p_untouched = with_seasons(BackfillPlan((s_none,)), "2001-2002")
    assert p_untouched.stages[0].seasons is None
    assert p_untouched.stages[0].estimate_gb == pytest.approx(15.0)


def test_estimate_scaling_supports_current_year_hook() -> None:
    # 2008-current with current_year=2024 is 17 seasons (2008..2024)
    # Overriding to 2020-current with current_year=2024 is 5 seasons (2020..2024)
    s = Stage(name="cur", sources=("fake",), seasons="2008-current", estimate_gb=170.0)
    plan = with_seasons(BackfillPlan((s,)), "2020-current", current_year=2024)
    assert plan.stages[0].estimate_gb == pytest.approx(50.0)


@pytest.mark.parametrize(
    "bad_text",
    [
        "not_a_season",
        "2024-2020",
        "",
        "   ",
        "2000,",
    ],
)
def test_bad_text_is_refused_with_message_starting_with_seasons(bad_text: str) -> None:
    plan = BackfillPlan((Stage(name="s", sources=("fake",), seasons="2000"),))
    with pytest.raises(BackfillError) as exc_info:
        with_seasons(plan, bad_text)
    assert str(exc_info.value).startswith("--seasons: ")


def test_options_order_names_and_attributes_survive() -> None:
    s1 = Stage(
        name="custom-stage",
        sources=("fake", "other"),
        seasons="2000-2005",
        datasets=("games", "stats"),
        limit=42,
        estimate_gb=60.0,
        options=(("sports", "all"), ("foo", "bar")),
        order="oldest-first",
    )
    s2 = Stage(name="ref", sources=("fake",), seasons=None, estimate_gb=3.0)
    plan = BackfillPlan((s1, s2))

    updated = with_seasons(plan, "2002-2003")
    assert len(updated.stages) == 2

    u1 = updated.stages[0]
    assert u1.name == "custom-stage"
    assert u1.sources == ("fake", "other")
    assert u1.seasons == "2002-2003"
    assert u1.datasets == ("games", "stats")
    assert u1.limit == 42
    assert u1.estimate_gb == pytest.approx(20.0)  # 60.0 * 2 / 6
    assert u1.options == (("sports", "all"), ("foo", "bar"))
    assert u1.order == "oldest-first"

    u2 = updated.stages[1]
    assert u2 == s2


def test_cli_backfill_minors_all_seasons_override_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    monkeypatch.setattr("baseballpy.cli_backfill._disk_usage", lambda _path: (50 * GB, 100 * GB))
    result = CliRunner().invoke(main, ["backfill", "minors-all", "--seasons", "2019", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "1 job(s)" in result.output
    assert "2019" in result.output
    match = re.search(r"estimated\s+([0-9.]+)\s+GB", result.output)
    assert match is not None
    assert float(match.group(1)) < 10.0


def test_cli_update_passes_through_seasons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    monkeypatch.setattr("baseballpy.cli_backfill._disk_usage", lambda _path: (50 * GB, 100 * GB))
    result = CliRunner().invoke(main, ["update", "--seasons", "2024", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "2024" in result.output


def test_python_api_backfill_seasons_override() -> None:
    fake = Recorder()
    plan = parse_plan(
        {
            "stage": [
                {
                    "name": "a",
                    "sources": ["fake"],
                    "seasons": "2000-2002",
                    "estimate_gb": 30.0,
                }
            ]
        }
    )
    report = bp.backfill(
        plan, seasons="2001", adapters={"fake": fake}, free_bytes=lambda: 50 * GB, dry_run=True
    )
    assert report.stages[0].planned == 1
    assert report.stages[0].stage.seasons == "2001"
    assert report.stages[0].stage.estimate_gb == pytest.approx(10.0)
    assert fake.ran == []
