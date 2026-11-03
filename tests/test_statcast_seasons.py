"""Statcast season bounds (ADR 56): the floor is 2008, the top follows the lake clock."""

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig
from baseballpy.ingest.types import JobStatus, make_job
from baseballpy.sources import catalog
from baseballpy.sources.statcast.access import table
from baseballpy.sources.statcast.adapter import StatcastAdapter
from baseballpy.sources.statcast.extractor import MLB_SEASONS_URL, StatcastExtractor
from baseballpy.sources.statcast.game_feed import StatcastGameFeed
from baseballpy.sources.statcast.leaderboards import StatcastLeaderboardExtractor
from baseballpy.sources.statcast.seasons import season_floor, season_skip_reason


def _lake(tmp_path: Path, today: date = date(2026, 11, 3)) -> LakeConfig:
    catalog.register_all()
    return LakeConfig(home=tmp_path, today=today)


def test_the_floor_is_the_latest_applicable_lower_bound() -> None:
    assert season_floor() == 2008
    assert season_floor(minors=True) == 2021
    assert season_floor(first_with_data=2015) == 2015
    assert season_floor(first_with_data=1995) == 2008


@respx.mock
def test_a_season_before_2008_is_skipped_without_any_request(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    extractor = StatcastExtractor(cache_config=lake)
    for minors in (False, True):
        report = extractor.ingest_season(1990, minors=minors)
        assert report.chunks == 0 and "2008" in (report.skipped_reason or "")
    assert all("2008" in (r.skipped_reason or "") for r in extractor.ingest_all(1990, 1991))

    boards = StatcastLeaderboardExtractor(cache_config=lake)
    report_lb = boards.ingest_leaderboard("sprint_speed", years=[1850, 1990])
    assert report_lb.seasons == {} and set(report_lb.skipped) == {1850, 1990}
    assert "2008" in report_lb.skipped[1990]

    feed = StatcastGameFeed(cache_config=lake)
    assert "2008" in (feed.ingest_season(1990).skipped_reason or "")
    assert respx.calls.call_count == 0


@respx.mock
def test_the_top_end_follows_the_lake_clock(tmp_path: Path) -> None:
    assert season_skip_reason(2027, date(2027, 6, 1)) is None
    assert "future" in (season_skip_reason(2028, date(2027, 6, 1)) or "")
    assert season_skip_reason(2028, date(2028, 6, 1)) is None

    extractor = StatcastExtractor(cache_config=_lake(tmp_path, date(2027, 6, 1)))
    report = extractor.ingest_season(2028)
    assert "future" in (report.skipped_reason or "") and report.chunks == 0
    assert respx.calls.call_count == 0

    # the current year before spring training: the calendar starts after today
    early = StatcastExtractor(cache_config=_lake(tmp_path / "early", date(2027, 1, 15)))
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2027-02-20", "postSeasonEndDate": "2027-10-31"}]
            },
        )
    )
    unstarted = early.ingest_season(2027)
    assert "has not started" in (unstarted.skipped_reason or "")
    assert unstarted.chunks == 0


@respx.mock
def test_the_adapter_skips_an_excluded_season_instead_of_failing(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    adapter = StatcastAdapter(
        extractor=StatcastExtractor(cache_config=lake),
        leaderboards=StatcastLeaderboardExtractor(cache_config=lake),
        game_feed=StatcastGameFeed(cache_config=lake),
    )
    for task in ("pitches", "leaderboards", "game_feed"):
        result = adapter.run(make_job("statcast", task, season=1990))
        assert result.status is JobStatus.SKIPPED, task
        assert "2008" in result.detail, task
    assert respx.calls.call_count == 0


@respx.mock
def test_single_fetches_raise_for_an_excluded_season(tmp_path: Path) -> None:
    lake = _lake(tmp_path)
    extractor = StatcastExtractor(cache_config=lake)
    with pytest.raises(ValueError, match="2008"):
        extractor.extract("1990-04-01", "1990-04-05")
    with pytest.raises(ValueError, match="2008"):
        StatcastLeaderboardExtractor(cache_config=lake).get_leaderboard("sprint_speed", year=1990)
    with pytest.raises(ValueError, match="2008"):
        table("pitches", 1990, cache_config=lake)
    assert respx.calls.call_count == 0
