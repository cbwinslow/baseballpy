"""Which seasons exist: the MLB calendar decides, so January and February never plan a new season (ADR 66)."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig
from baseballpy.core.season_calendar import SEASONS_ALL_URL, SeasonCalendar, parse_calendar
from baseballpy.ingest.types import JobStatus, make_job
from baseballpy.sources.mlb_api.adapter import MlbApiAdapter
from baseballpy.sources.statcast.adapter import StatcastAdapter


def _season(year: int, spring: str, opening: str, end: str) -> dict[str, Any]:
    return {
        "seasonId": str(year),
        "springStartDate": spring,
        "regularSeasonStartDate": opening,
        "postSeasonEndDate": end,
        "seasonEndDate": end,
    }


CALENDAR = {
    "seasons": [
        {  # 1876 has no spring training: opening day is the first day
            "seasonId": "1876",
            "regularSeasonStartDate": "1876-04-22",
            "seasonEndDate": "1876-10-09",
        },
        _season(2026, "2026-02-20", "2026-03-25", "2026-10-31"),
        _season(2027, "2027-02-19", "2027-03-25", "2027-10-31"),
        {"seasonId": "2099"},  # no dates: left out
    ]
}


def _mock() -> respx.Route:
    return respx.get(SEASONS_ALL_URL).mock(return_value=httpx.Response(200, json=CALENDAR))


def _lake(tmp_path: Path, today: date) -> LakeConfig:
    return LakeConfig(home=tmp_path, today=today)


def test_parse_keeps_spring_start_else_opening_day_and_drops_seasons_without_dates() -> None:
    seasons = parse_calendar(json.dumps(CALENDAR))
    assert seasons[2027].start == date(2027, 2, 19) and seasons[2027].end == date(2027, 10, 31)
    assert seasons[1876].start == date(1876, 4, 22)
    assert 2099 not in seasons


@respx.mock
def test_in_january_the_new_season_has_not_started_and_the_last_one_is_the_latest(
    tmp_path: Path,
) -> None:
    route = _mock()
    calendar = SeasonCalendar(_lake(tmp_path, date(2027, 1, 15)))
    assert calendar.latest_started_season() == 2026
    reason = calendar.not_started_reason(2027)
    assert reason is not None and "has not started" in reason and "2027-02-19" in reason
    assert calendar.not_started_reason(2026) is None
    assert route.call_count == 1


@respx.mock
def test_once_spring_training_begins_the_new_season_counts(tmp_path: Path) -> None:
    _mock()
    calendar = SeasonCalendar(_lake(tmp_path, date(2027, 2, 19)))
    assert calendar.latest_started_season() == 2027
    assert calendar.not_started_reason(2027) is None


@respx.mock
def test_past_and_future_seasons_need_no_request_and_the_calendar_is_cached(tmp_path: Path) -> None:
    route = _mock()
    calendar = SeasonCalendar(_lake(tmp_path, date(2027, 1, 15)))
    assert calendar.not_started_reason(2008) is None  # before this year: always started
    assert "future" in (calendar.not_started_reason(2028) or "")
    assert route.call_count == 0
    calendar.latest_started_season()
    SeasonCalendar(_lake(tmp_path, date(2027, 1, 15))).latest_started_season()
    assert route.call_count == 1  # the second calendar read the twelve-hour cache


@respx.mock
def test_a_season_the_calendar_does_not_list_is_not_started(tmp_path: Path) -> None:
    respx.get(SEASONS_ALL_URL).mock(
        return_value=httpx.Response(200, json={"seasons": CALENDAR["seasons"][:2]})
    )
    reason = SeasonCalendar(_lake(tmp_path, date(2027, 1, 15))).not_started_reason(2027)
    assert reason is not None and "does not list" in reason


@respx.mock
def test_a_season_is_finished_after_the_postseason_ends(tmp_path: Path) -> None:
    _mock()
    calendar = SeasonCalendar(_lake(tmp_path, date(2026, 11, 5)))
    assert calendar.is_finished(2026) and not calendar.is_finished(2027)


class _NeverCalled:
    """An extractor or source that fails the test if a skipped job reaches it."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"a not-started season must not reach the provider code ({name})")


@respx.mock
def test_statcast_adapter_plans_to_last_season_and_skips_a_new_one_in_january(
    tmp_path: Path,
) -> None:
    _mock()
    calendar = SeasonCalendar(_lake(tmp_path, date(2027, 1, 15)))
    adapter = StatcastAdapter(
        extractor=_NeverCalled(), leaderboards=_NeverCalled(), game_feed=_NeverCalled(),
        calendar=calendar,
    )  # fmt: skip
    seasons = list(adapter.all_seasons())
    assert seasons[0] == 2008 and seasons[-1] == 2026
    for task in ("pitches", "leaderboards", "game_feed"):
        result = adapter.run(make_job("statcast", task, season=2027))
        assert result.status == JobStatus.SKIPPED
        assert "has not started" in (result.detail or "")


@respx.mock
def test_mlb_adapter_plans_to_last_season_and_skips_a_new_one_in_january(tmp_path: Path) -> None:
    _mock()
    calendar = SeasonCalendar(_lake(tmp_path, date(2027, 1, 15)))
    adapter = MlbApiAdapter(_NeverCalled(), calendar=calendar)
    seasons = list(adapter.all_seasons())
    assert seasons[0] == 1876 and seasons[-1] == 2026
    for task in ("season", "history", "people_stats", "endpoint"):
        result = adapter.run(make_job("mlb_api", task, season=2027))
        assert result.status == JobStatus.SKIPPED
        assert "has not started" in (result.detail or "")


@respx.mock
def test_a_calendar_that_cannot_be_read_fails_loudly_not_silently(tmp_path: Path) -> None:
    respx.get(SEASONS_ALL_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(Exception, match="500|HTTP|status"):
        SeasonCalendar(_lake(tmp_path, date(2027, 1, 15))).latest_started_season()
