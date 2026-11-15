"""Live journal (ADR 138): every poll answer of a live game is on disk before it is used, and a replay is exact."""

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.audit import AuditLogger
from baseballpy.core.config import AuditConfig, LakeConfig, QuarantineConfig, RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.core.quarantine import Quarantine
from baseballpy.layout_audit import audit_layout
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api import stream as stream_mod
from baseballpy.sources.mlb_api.live.journal import LiveJournal
from baseballpy.sources.mlb_api.live.replay import replay_events
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer, LiveEvent

FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"


def _pitch(index: int, speed: float = 95.0) -> dict[str, Any]:
    return {
        "index": index,
        "isPitch": True,
        "playId": f"p{index}",
        "startTime": f"2024-06-23T18:00:{index:02d}.250Z",
        "details": {
            "type": {"code": "FF"},
            "call": {"code": "B"},
            "description": "Ball",
            "eventType": "ball",
        },
        "pitchData": {"startSpeed": speed, "zone": 11, "coordinates": {"pX": 0.5, "pZ": 3.0}},
        "count": {"balls": 1, "strikes": 0, "outs": 0},
    }


def _feed(stamp: str, detailed: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    abstract = {"In Progress": "Live", "Final": "Final", "Suspended": "Suspended"}[detailed]
    return {
        "metaData": {"timeStamp": stamp},
        "gameData": {"status": {"abstractGameState": abstract, "detailedState": detailed}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {"atBatIndex": 0, "inning": 1, "isTopInning": True},
                        "matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}},
                        "result": {"event": "Walk", "description": "A walks."},
                        "count": {"balls": 4, "strikes": 0, "outs": 0},
                        "playEvents": events,
                    }
                ]
            }
        },
    }


def _patch(stamp: str, extra: list[dict[str, Any]]) -> httpx.Response:
    return httpx.Response(
        200,
        json=[{"diff": [{"op": "replace", "path": "/metaData/timeStamp", "value": stamp}, *extra]}],
    )


def _game(pk: int, stamps_first: httpx.Response | None = None) -> None:
    """Full feed, one new pitch by patch, then Final by patch (optionally a failing first timestamps call)."""
    url = FEED.format(pk=pk)
    respx.get(url).mock(
        return_value=httpx.Response(200, json=_feed("t1", "In Progress", [_pitch(0)]))
    )
    stamps = [
        httpx.Response(200, json=["t1"]),
        httpx.Response(200, json=["t1", "t2"]),
        httpx.Response(200, json=["t1", "t2", "t3"]),
    ]
    if stamps_first is not None:
        stamps.insert(0, stamps_first)
    respx.get(f"{url}/timestamps").mock(side_effect=stamps)
    add = {"op": "add", "path": "/liveData/plays/allPlays/0/playEvents/-", "value": _pitch(1, 97.5)}
    final = [
        {"op": "replace", "path": "/gameData/status/detailedState", "value": "Final"},
        {"op": "replace", "path": "/gameData/status/abstractGameState", "value": "Final"},
    ]
    respx.get(f"{url}/diffPatch").mock(side_effect=[_patch("t2", [add]), _patch("t3", final)])


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


def _streamer(tmp_path: Path, http: HttpClient, **kw: Any) -> GamedayLiveStreamer:
    quarantine = Quarantine(QuarantineConfig(base_dir=tmp_path))
    return GamedayLiveStreamer(
        poll_interval=0.001,
        http=http,
        lake=LakeConfig(home=tmp_path),
        quarantine=quarantine,
        journal=True,
        **kw,
    )


def _plain(events: list[LiveEvent]) -> list[dict[str, Any]]:
    """The events without the wall-clock field (a replay is not received at the same moment)."""
    return [{**e.to_dict(), "received_utc": 0} for e in events]


@respx.mock
@pytest.mark.asyncio
async def test_every_poll_answer_is_on_disk_before_it_is_used(
    tmp_path: Path, http: HttpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _game(1)
    lake = LakeConfig(home=tmp_path)
    streamer = _streamer(tmp_path, http)
    seen: list[bool] = []
    real_decode = streamer._decode

    def checking_decode(game_pk: int, content: bytes) -> Any:
        bodies = [r.body for r in LiveJournal(lake, game_pk).records()]
        seen.append(content in bodies)
        return real_decode(game_pk, content)

    monkeypatch.setattr(streamer, "_decode", checking_decode)
    events = [e async for e in streamer.stream_live_events(1)]
    assert events and seen and all(seen), "each decoded answer was already in the journal"
    records = LiveJournal(lake, 1).records()
    assert [r.seq for r in records] == list(range(len(records)))
    assert records[0].url == FEED.format(pk=1) and records[0].status == 200
    assert any(r.url.endswith("/diffPatch?endTimecode=t2&startTimecode=t1") for r in records)


@respx.mock
@pytest.mark.asyncio
async def test_a_replay_gives_the_same_events(tmp_path: Path, http: HttpClient) -> None:
    _game(2)
    live = [e async for e in _streamer(tmp_path, http).stream_live_events(2)]
    replayed = [e async for e in replay_events(LakeConfig(home=tmp_path), 2)]
    assert len(live) >= 4
    assert _plain(replayed) == _plain(live)


@respx.mock
@pytest.mark.asyncio
async def test_a_failed_status_is_journalled_and_replayed(tmp_path: Path, http: HttpClient) -> None:
    """A status the client refuses (here 418 on the timestamps call) changes what the streamer does next, so it is kept."""
    _game(3, stamps_first=httpx.Response(418))
    live = [e async for e in _streamer(tmp_path, http).stream_live_events(3)]
    records = LiveJournal(LakeConfig(home=tmp_path), 3).records()
    assert any(r.error and r.status == 418 for r in records)
    replayed = [e async for e in replay_events(LakeConfig(home=tmp_path), 3)]
    assert _plain(replayed) == _plain(live)


@respx.mock
@pytest.mark.asyncio
async def test_a_torn_last_record_is_cut_logged_and_new_records_follow_whole_ones(
    tmp_path: Path, http: HttpClient, caplog: pytest.LogCaptureFixture
) -> None:
    _game(4)
    _ = [e async for e in _streamer(tmp_path, http).stream_live_events(4)]
    lake = LakeConfig(home=tmp_path)
    path = lake.live_journal_path("mlb_api", 4)
    whole = len(LiveJournal(lake, 4).records())
    path.write_bytes(path.read_bytes()[:-5])  # a power cut in the middle of the last write
    with caplog.at_level(logging.WARNING):
        journal = LiveJournal(lake, 4)
    assert len(journal.records()) == whole - 1
    assert any("torn" in message for message in caplog.messages), "the cut is not silent"
    seq = journal.append(FEED.format(pk=4), 200, b"{}", None)
    assert seq == whole - 1
    assert [r.seq for r in LiveJournal(lake, 4).records()] == list(range(whole))


@respx.mock
@pytest.mark.asyncio
async def test_a_restart_continues_the_journal_and_repeats_no_event(
    tmp_path: Path, http: HttpClient
) -> None:
    pk = 5
    url = FEED.format(pk=pk)
    respx.get(url).mock(
        side_effect=[
            httpx.Response(200, json=_feed("t1", "Suspended", [_pitch(0)])),
            httpx.Response(200, json=_feed("t2", "Final", [_pitch(0), _pitch(1)])),
        ]
    )
    first = [e async for e in _streamer(tmp_path, http).stream_live_events(pk)]
    after_first = len(LiveJournal(LakeConfig(home=tmp_path), pk).records())
    second = [e async for e in _streamer(tmp_path, http).stream_live_events(pk)]
    records = LiveJournal(LakeConfig(home=tmp_path), pk).records()
    assert after_first >= 1 and len(records) > after_first
    assert [r.seq for r in records] == list(range(len(records))), (
        "one journal, no gap, no restart at 0"
    )
    keys = [(e.game_pk, e.at_bat_index, e.event_index, e.event_kind) for e in first + second]
    assert len(keys) == len(set(keys)), "the resume watermark still suppresses repeats"


@respx.mock
@pytest.mark.asyncio
async def test_a_replay_does_not_touch_the_resume_state(tmp_path: Path, http: HttpClient) -> None:
    _game(6)
    _ = [e async for e in _streamer(tmp_path, http).stream_live_events(6)]
    state = tmp_path / "cache" / "stream" / "6.json"
    before = state.read_bytes()
    _ = [e async for e in replay_events(LakeConfig(home=tmp_path), 6)]
    assert state.read_bytes() == before


@respx.mock
@pytest.mark.asyncio
async def test_the_audit_log_names_the_journal(
    tmp_path: Path, http: HttpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    audit = AuditLogger(AuditConfig(base_dir=tmp_path))
    monkeypatch.setattr(stream_mod, "default_audit_logger", audit)
    _game(7)
    events = [e async for e in _streamer(tmp_path, http).stream_live_events(7)]
    lines = [line for line in audit.log_path.read_text(encoding="utf-8").splitlines() if line]
    stream_lines = [line for line in lines if '"mlb_stream"' in line]
    assert len(stream_lines) == 1 and "_live" in stream_lines[0]
    assert f'"records_count":{len(events)}' in stream_lines[0].replace(" ", "")
    replayed = [e async for e in replay_events(LakeConfig(home=tmp_path), 7)]
    assert replayed
    assert any('"mlb_stream_replay"' in line for line in audit.log_path.read_text().splitlines())


@respx.mock
@pytest.mark.asyncio
async def test_the_journal_folder_is_ignored_by_the_layout_audit(
    tmp_path: Path, http: HttpClient
) -> None:
    catalog.register_all()
    _game(8)
    _ = [e async for e in _streamer(tmp_path, http).stream_live_events(8)]
    lake = LakeConfig(home=tmp_path)
    assert lake.live_journal_path("mlb_api", 8).is_file()
    assert audit_layout(lake, ("mlb_api",)) == []
