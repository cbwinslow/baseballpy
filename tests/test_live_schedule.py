"""The schedule source of the live supervisor: one small request, a tolerant parse, nothing skipped silently."""

import logging
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.sources.mlb_api.live.schedule import SCHEDULE_URL, MlbScheduleSource, parse_schedule


@pytest.fixture
def http() -> Any:
    rates = RateLimitConfig(
        host_rates={"statsapi.mlb.com": 1000.0},
        default_requests_per_second=1000.0,
        backoff_factor=0.01,
    )
    client = HttpClient(rates, http2=False)
    yield client
    client.close()


PAYLOAD = {
    "dates": [
        {
            "date": "2026-06-23",
            "games": [
                {
                    "gamePk": 745000,
                    "season": "2026",
                    "gameDate": "2026-06-23T23:10:00Z",
                    "status": {"abstractGameState": "Preview", "detailedState": "Scheduled"},
                },
                {
                    "gamePk": 745001,
                    "season": "2026",
                    "gameDate": "2026-06-23T17:05:00Z",
                    "status": {"abstractGameState": "Live"},
                },
                {"season": "2026"},
            ],
        }
    ]
}


def test_games_are_parsed_and_an_entry_without_a_game_pk_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        games = parse_schedule(PAYLOAD, 2026)
    assert [(g.game_pk, g.season, g.state) for g in games] == [
        (745000, 2026, "Preview"),
        (745001, 2026, "Live"),
    ]
    assert games[0].start_utc == datetime(2026, 6, 23, 23, 10, tzinfo=UTC)
    assert any("without a usable gamePk" in m for m in caplog.messages)


def test_an_odd_answer_gives_no_games() -> None:
    assert parse_schedule([], 2026) == [] and parse_schedule({"dates": []}, 2026) == []


@respx.mock
@pytest.mark.asyncio
async def test_one_request_per_day_with_the_levels_and_the_date(http: HttpClient) -> None:
    route = respx.get(SCHEDULE_URL).mock(return_value=httpx.Response(200, json=PAYLOAD))
    games = await MlbScheduleSource(http, (1, 11)).games(date(2026, 6, 23))
    assert len(games) == 2 and route.call_count == 1
    params = route.calls[0].request.url.params
    assert params["sportId"] == "1,11" and params["date"] == "2026-06-23"
