"""End to end without the network: schedule -> real streamer (journal on) -> supervisor -> sink -> lake -> DuckDB."""

import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig, QuarantineConfig, RateLimitConfig, StreamingConfig
from baseballpy.core.http import HttpClient
from baseballpy.core.quarantine import Quarantine
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.live.journal import LiveJournal
from baseballpy.sources.mlb_api.live.replay import replay_events
from baseballpy.sources.mlb_api.live.sink import LiveGameSink
from baseballpy.sources.mlb_api.live.supervisor import LiveSupervisor, ScheduledGame
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer

FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"
TODAY = datetime(2026, 6, 23, 18, 0, tzinfo=UTC)


def _pitch(index: int) -> dict[str, Any]:
    return {
        "index": index,
        "isPitch": True,
        "playId": f"p{index}",
        "startTime": f"2026-06-23T18:00:{index:02d}.250Z",
        "details": {"type": {"code": "FF"}, "call": {"code": "B"}, "description": "Ball"},
        "pitchData": {"startSpeed": 95.0, "zone": 11, "coordinates": {"pX": 0.5, "pZ": 3.0}},
        "count": {"balls": 1, "strikes": 0, "outs": 0},
    }


def _feed(stamp: str, detailed: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    abstract = {"In Progress": "Live", "Final": "Final"}[detailed]
    return {
        "metaData": {"timeStamp": stamp},
        "gameData": {"status": {"abstractGameState": abstract, "detailedState": detailed}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {"atBatIndex": 0, "inning": 1, "isTopInning": True},
                        "matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}},
                        "result": {"event": "Walk"},
                        "count": {"balls": 4, "strikes": 0, "outs": 0},
                        "playEvents": events,
                    }
                ]
            }
        },
    }


def _mock_game(pk: int, pitches: int) -> None:
    """A game that is already over when first read: one full feed with ``pitches`` pitches and a Final status."""
    respx.get(FEED.format(pk=pk)).mock(
        return_value=httpx.Response(
            200, json=_feed("t1", "Final", [_pitch(i) for i in range(pitches)])
        )
    )


class Schedule:
    def __init__(self, stop: asyncio.Event) -> None:
        self.stop = stop
        self.looks = 0
        self.done: Any = lambda: False  # set to "both games finished" once the supervisor exists

    async def games(self, day: date) -> list[ScheduledGame]:
        if day != TODAY.date():
            return []
        self.looks += 1
        if self.looks >= 3 and self.done():
            self.stop.set()
        return [
            ScheduledGame(745000, 2026, "Live", TODAY),
            ScheduledGame(745001, 2026, "Live", TODAY),
        ]


@respx.mock
@pytest.mark.asyncio
async def test_two_games_flow_from_the_feed_into_the_lake_and_back_out_through_duckdb(
    tmp_path: Path,
) -> None:
    catalog.register_all()
    lake = LakeConfig(home=tmp_path)
    rates = RateLimitConfig(
        host_rates={"statsapi.mlb.com": 1000.0},
        default_requests_per_second=1000.0,
        backoff_factor=0.01,
    )
    http = HttpClient(rates, http2=False)
    _mock_game(745000, 3)
    _mock_game(745001, 5)
    config = StreamingConfig(journal=True, commit_seconds=0.01, schedule_interval_seconds=0.01)
    streamer = GamedayLiveStreamer(
        poll_interval=0.001,
        http=http,
        config=config,
        lake=lake,
        quarantine=Quarantine(QuarantineConfig(base_dir=tmp_path)),
    )
    stop = asyncio.Event()
    schedule = Schedule(stop)
    supervisor = LiveSupervisor(
        sink=LiveGameSink(lake),
        schedule=schedule,
        stream=streamer.stream_live_events,
        config=config,
        now=lambda: TODAY,
    )
    schedule.done = lambda: supervisor.report.finished == 2
    try:
        report = await asyncio.wait_for(supervisor.run(stop), timeout=30)
    finally:
        http.close()

    assert report.started == 2 and report.finished == 2 and not report.failed
    for pk, pitches in ((745000, 3), (745001, 5)):
        assert lake.live_journal_path("mlb_api", pk).is_file(), "every poll answer is journalled"
        assert len(LiveJournal(lake, pk).records()) >= 1
        replayed = [e async for e in replay_events(lake, pk)]
        assert len([e for e in replayed if e.event_kind == "pitch"]) == pitches

    con = BaseballDatabase(cache_config=lake).connect()
    try:
        rows = con.execute(
            "SELECT game_pk, count(*) FROM mlb_game_live_events GROUP BY 1 ORDER BY 1"
        ).fetchall()
    finally:
        con.close()
    assert rows == [(745000, 3), (745001, 5)]
