"""Live streamer: JSON patch, timestamps/diffPatch polling, lifecycle, resume, Arrow mapping."""

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig, RateLimitConfig, StreamingConfig
from baseballpy.core.http import HttpClient
from baseballpy.core.protocols import StreamExtractorProtocol
from baseballpy.sources.mlb_api import stream as stream_mod
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS
from baseballpy.sources.mlb_api.stream import (
    GamedayLiveStreamer,
    LiveEvent,
    PatchError,
    apply_patch,
    patch_ops,
    to_arrow,
)


def fast_rates(*hosts: str) -> RateLimitConfig:
    return RateLimitConfig(
        host_rates={h: 1000.0 for h in hosts},
        default_requests_per_second=1000.0,
        backoff_factor=0.01,
    )


FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"
FIXTURE = Path(__file__).parent / "fixtures" / "mlb" / "game_feed_play_events.json"


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
        "pitchData": {
            "startSpeed": speed,
            "zone": 11,
            "coordinates": {"pX": 0.5, "pZ": 3.0},
            "breaks": {"spinRate": 2300},
        },
        "count": {"balls": 1, "strikes": 0, "outs": 0},
    }


def _feed(
    stamp: str, detailed: str, events: list[dict[str, Any]], complete: bool = False
) -> dict[str, Any]:
    abstract = {"In Progress": "Live", "Final": "Final", "Suspended": "Suspended"}.get(
        detailed, detailed
    )
    return {
        "metaData": {"timeStamp": stamp},
        "gameData": {"status": {"abstractGameState": abstract, "detailedState": detailed}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {
                            "atBatIndex": 0,
                            "inning": 1,
                            "isTopInning": True,
                            "isComplete": complete,
                            "endTime": "2024-06-23T18:01:00Z",
                        },
                        "matchup": {"batter": {"id": 1}, "pitcher": {"id": 2}},
                        "result": {"event": "Walk", "description": "A walks."},
                        "count": {"balls": 4, "strikes": 0, "outs": 0},
                        "playEvents": events,
                    }
                ]
            }
        },
    }


def _streamer(tmp_path: Path, http: HttpClient, **kw: Any) -> GamedayLiveStreamer:
    return GamedayLiveStreamer(poll_interval=0.001, http=http, lake=LakeConfig(home=tmp_path), **kw)


@pytest.fixture
def http() -> Any:
    client = HttpClient(fast_rates("statsapi.mlb.com"), http2=False)
    yield client
    client.close()


# ------------------------------------------------------------------ JSON patch


def test_apply_patch_all_operations() -> None:
    doc: Any = {"a": {"b": [1, 2, 3]}, "c": 1, "d": {"x": 1}}
    out = apply_patch(
        doc,
        [
            {"op": "replace", "path": "/c", "value": 2},
            {"op": "add", "path": "/a/b/1", "value": 9},
            {"op": "add", "path": "/a/b/-", "value": 7},
            {"op": "remove", "path": "/a/b/0"},
            {"op": "copy", "from": "/c", "path": "/e"},
            {"op": "move", "from": "/d/x", "path": "/f"},
            {"op": "test", "path": "/e", "value": 2},
            {"op": "replace", "path": "/a/b/0", "value": "z"},
        ],
    )
    assert out == {"a": {"b": ["z", 2, 3, 7]}, "c": 2, "d": {}, "e": 2, "f": 1}


@pytest.mark.parametrize(
    "ops",
    [
        [{"op": "replace", "path": "/missing", "value": 1}],
        [{"op": "remove", "path": "/a/9"}],
        [{"op": "add", "path": "/a/b/9", "value": 1}],
        [{"op": "test", "path": "/c", "value": 99}],
        [{"op": "explode", "path": "/c"}],
        [{"op": "add", "path": "no-slash", "value": 1}],
    ],
)
def test_apply_patch_rejects_inapplicable_operations(ops: list[dict[str, Any]]) -> None:
    with pytest.raises(PatchError):
        apply_patch({"a": {"b": [1]}, "c": 1}, ops)


def test_patch_ops_accepts_the_live_response_shape() -> None:
    assert patch_ops([{"diff": [{"op": "remove", "path": "/x"}]}, {"diff": []}]) == [
        {"op": "remove", "path": "/x"}
    ]
    assert patch_ops([]) == []
    with pytest.raises(PatchError):
        patch_ops(["nonsense"])


# ------------------------------------------------------------------ polling strategies


@respx.mock
@pytest.mark.asyncio
async def test_diff_patch_is_used_after_the_first_full_fetch(
    tmp_path: Path, http: HttpClient
) -> None:
    url = FEED.format(pk=1)
    full = respx.get(url).mock(
        return_value=httpx.Response(200, json=_feed("t1", "In Progress", [_pitch(0)]))
    )
    respx.get(f"{url}/timestamps").mock(
        side_effect=[
            httpx.Response(200, json=["t1"]),
            httpx.Response(200, json=["t1", "t2"]),
            httpx.Response(200, json=["t1", "t2", "t3"]),
        ]
    )
    patches = respx.get(f"{url}/diffPatch").mock(
        side_effect=[
            httpx.Response(
                200,
                json=[
                    {
                        "diff": [
                            {"op": "replace", "path": "/metaData/timeStamp", "value": "t2"},
                            {
                                "op": "add",
                                "path": "/liveData/plays/allPlays/0/playEvents/-",
                                "value": _pitch(1, 97.5),
                            },
                        ]
                    }
                ],
            ),
            httpx.Response(
                200,
                json=[
                    {
                        "diff": [
                            {"op": "replace", "path": "/metaData/timeStamp", "value": "t3"},
                            {
                                "op": "replace",
                                "path": "/gameData/status/detailedState",
                                "value": "Final",
                            },
                            {
                                "op": "replace",
                                "path": "/gameData/status/abstractGameState",
                                "value": "Final",
                            },
                        ]
                    }
                ],
            ),
        ]
    )
    events = [e async for e in _streamer(tmp_path, http).stream_live_events(1)]
    assert [e.event_index for e in events if e.event_kind == "pitch"] == [0, 1]
    pitches = [e for e in events if e.event_kind == "pitch"]
    assert pitches[1].start_speed == pytest.approx(97.5)
    assert full.call_count == 1 and patches.call_count == 2
    assert [e.event for e in events if e.event_kind == "game_status"] == ["In Progress", "Final"]
    assert (
        patches.calls[0].request.url.params["startTimecode"],
        patches.calls[0].request.url.params["endTimecode"],
    ) == ("t1", "t2")


@respx.mock
@pytest.mark.asyncio
async def test_patch_that_misses_the_announced_timestamp_falls_back_to_the_full_feed(
    tmp_path: Path, http: HttpClient
) -> None:
    url = FEED.format(pk=2)
    full = respx.get(url).mock(
        side_effect=[
            httpx.Response(200, json=_feed("t1", "In Progress", [_pitch(0)])),
            httpx.Response(200, json=_feed("t2", "Final", [_pitch(0), _pitch(1)])),
        ]
    )
    respx.get(f"{url}/timestamps").mock(return_value=httpx.Response(200, json=["t1", "t2"]))
    respx.get(f"{url}/diffPatch").mock(
        return_value=httpx.Response(
            200,
            json=[{"diff": [{"op": "replace", "path": "/metaData/timeStamp", "value": "wrong"}]}],
        )
    )
    events = [e async for e in _streamer(tmp_path, http).stream_live_events(2)]
    assert [e.event_index for e in events if e.event_kind == "pitch"] == [0, 1]
    assert full.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_missing_diff_patch_endpoint_falls_back(tmp_path: Path, http: HttpClient) -> None:
    url = FEED.format(pk=3)
    respx.get(url).mock(
        side_effect=[
            httpx.Response(200, json=_feed("t1", "In Progress", [_pitch(0)])),
            httpx.Response(200, json=_feed("t2", "Final", [_pitch(0), _pitch(1)])),
        ]
    )
    respx.get(f"{url}/timestamps").mock(return_value=httpx.Response(404))
    events = [e async for e in _streamer(tmp_path, http).stream_live_events(3)]
    assert len([e for e in events if e.event_kind == "pitch"]) == 2


# ------------------------------------------------------------------ events and lifecycle


@respx.mock
@pytest.mark.asyncio
async def test_event_kinds_play_result_and_microsecond_timestamps(
    tmp_path: Path, http: HttpClient
) -> None:
    pickoff = {
        "index": 1,
        "isPitch": False,
        "details": {"eventType": "pickoff_1b", "event": "Pickoff 1B"},
    }
    steal = {
        "index": 2,
        "isPitch": False,
        "details": {"eventType": "stolen_base_2b", "event": "Stolen Base 2B"},
    }
    sub = {
        "index": 3,
        "isPitch": False,
        "details": {"eventType": "pitching_substitution", "event": "Pitching Substitution"},
    }
    other = {
        "index": 4,
        "isPitch": False,
        "details": {"eventType": "no_pitch", "event": "No Pitch"},
    }
    respx.get(FEED.format(pk=4)).mock(
        return_value=httpx.Response(
            200, json=_feed("t1", "Final", [_pitch(0), pickoff, steal, sub, other], complete=True)
        )
    )
    events = [
        e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(4)
    ]
    assert [e.event_kind for e in events] == [
        "pitch",
        "pickoff",
        "stolen_base",
        "substitution",
        "action",
        "play_result",
        "game_status",
    ]
    pitch = events[0]
    assert pitch.ts_utc == 1_719_165_600_250_000 and pitch.received_utc > pitch.ts_utc
    assert (pitch.zone, pitch.spin_rate, pitch.batter_id, pitch.pitcher_id) == (11, 2300.0, 1, 2)
    result = events[5]
    assert (result.event_index, result.play_result, result.at_bat_index) == (-1, "Walk", 0)
    assert "raw_event" not in pitch.to_dict() and pitch.to_dict()["event_kind"] == "pitch"


@respx.mock
@pytest.mark.asyncio
async def test_suspended_game_is_emitted_ends_and_resumes_from_the_watermark(
    tmp_path: Path, http: HttpClient
) -> None:
    url = FEED.format(pk=5)
    respx.get(url).mock(
        return_value=httpx.Response(200, json=_feed("t1", "Suspended", [_pitch(0), _pitch(1)]))
    )
    first = [e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(5)]
    assert [e.event for e in first if e.event_kind == "game_status"] == ["Suspended"]
    assert len([e for e in first if e.event_kind == "pitch"]) == 2
    # the game resumes later: two old pitches must not be re-emitted, the new one is
    respx.get(url).mock(
        return_value=httpx.Response(
            200, json=_feed("t9", "Final", [_pitch(0), _pitch(1), _pitch(2)])
        )
    )
    second = [
        e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(5)
    ]
    assert [e.event_index for e in second if e.event_kind == "pitch"] == [2]
    assert [e.event for e in second if e.event_kind == "game_status"] == ["Final"]
    # without resume everything is emitted again
    third = [
        e
        async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(
            5, resume=False
        )
    ]
    assert len([e for e in third if e.event_kind == "pitch"]) == 3


@respx.mock
@pytest.mark.asyncio
async def test_delayed_game_backs_off_and_waiting_states_are_bounded(
    tmp_path: Path, http: HttpClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(stream_mod.asyncio, "sleep", fake_sleep)
    respx.get(FEED.format(pk=6)).mock(
        side_effect=[
            httpx.Response(200, json=_feed("t1", "Warmup", [])),
            httpx.Response(200, json=_feed("t2", "Delayed: Rain", [])),
            httpx.Response(200, json=_feed("t3", "Final", [])),
        ]
    )
    events = [
        e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(6)
    ]
    assert [e.event for e in events] == ["Warmup", "Delayed: Rain", "Final"]
    assert sleeps == [0.001, stream_mod.DELAYED_POLL_SECONDS]


@respx.mock
@pytest.mark.asyncio
async def test_postponed_game_is_emitted_and_ends(tmp_path: Path, http: HttpClient) -> None:
    respx.get(FEED.format(pk=7)).mock(
        return_value=httpx.Response(200, json=_feed("t1", "Postponed", []))
    )
    events = [
        e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(7)
    ]
    assert [e.event for e in events] == ["Postponed"]


@respx.mock
@pytest.mark.asyncio
async def test_idle_stream_stops(tmp_path: Path, http: HttpClient) -> None:
    respx.get(FEED.format(pk=8)).mock(
        return_value=httpx.Response(200, json=_feed("t1", "Preview", []))
    )
    streamer = _streamer(
        tmp_path, http, use_diff_patch=False, config=StreamingConfig(max_inactivity_minutes=0)
    )
    assert [e.event for e in [e async for e in streamer.stream_live_events(8)]] == ["Preview"]


# ------------------------------------------------------------------ contracts


def test_streamer_implements_the_protocol_without_owning_a_game(tmp_path: Path) -> None:
    streamer = GamedayLiveStreamer(lake=LakeConfig(home=tmp_path))
    assert isinstance(streamer, StreamExtractorProtocol)
    assert not hasattr(streamer, "game_pk")


@respx.mock
@pytest.mark.asyncio
async def test_to_arrow_shares_the_historical_schema_and_flattening(
    tmp_path: Path, http: HttpClient
) -> None:
    payload = json.loads(FIXTURE.read_text("utf-8"))
    expected = sum(len(p["playEvents"]) for p in payload["liveData"]["plays"]["allPlays"])
    doc = copy.deepcopy(payload)
    doc["metaData"] = {"timeStamp": "t1"}
    doc["gameData"] = {"status": {"abstractGameState": "Final", "detailedState": "Final"}}
    respx.get(FEED.format(pk=745000)).mock(return_value=httpx.Response(200, json=doc))
    events = [
        e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(745000)
    ]
    table = to_arrow([e for e in events if isinstance(e, LiveEvent)])
    schema = MLB_SCHEMAS["game_feed_play_events"]
    assert table.schema == schema
    assert table.num_rows == expected
    assert set(table.column("game_pk").to_pylist()) == {745000}
    assert to_arrow([]).num_rows == 0


@respx.mock
@pytest.mark.asyncio
async def test_wide_window_answered_with_the_full_feed_is_accepted(
    tmp_path: Path, http: HttpClient
) -> None:
    """Live finding: a wide diffPatch window returns the whole feed document, not a patch list."""
    url = FEED.format(pk=11)
    full = respx.get(url).mock(
        return_value=httpx.Response(200, json=_feed("t1", "In Progress", [_pitch(0)]))
    )
    respx.get(f"{url}/timestamps").mock(return_value=httpx.Response(200, json=["t1", "t2", "t3"]))
    respx.get(f"{url}/diffPatch").mock(
        return_value=httpx.Response(
            200, json=_feed("t3", "Final", [_pitch(0), _pitch(1), _pitch(2)])
        )
    )
    events = [e async for e in _streamer(tmp_path, http).stream_live_events(11)]
    assert [e.event_index for e in events if e.event_kind == "pitch"] == [0, 1, 2]
    assert full.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_third_out_emits_a_half_inning_end_once(tmp_path: Path, http: HttpClient) -> None:
    doc = _feed("t1", "Final", [_pitch(0)], complete=True)
    doc["liveData"]["plays"]["allPlays"][0]["count"] = {"balls": 0, "strikes": 3, "outs": 3}
    respx.get(FEED.format(pk=12)).mock(return_value=httpx.Response(200, json=doc))
    streamer = _streamer(tmp_path, http, use_diff_patch=False)
    events = [e async for e in streamer.stream_live_events(12)]
    ends = [e for e in events if e.event_kind == "half_inning_end"]
    assert len(ends) == 1
    assert (ends[0].event_index, ends[0].inning, ends[0].is_top_inning, ends[0].outs) == (
        -2,
        1,
        True,
        3,
    )
    assert "top of inning 1" in ends[0].description
    again = [
        e async for e in _streamer(tmp_path, http, use_diff_patch=False).stream_live_events(12)
    ]
    assert again == [], "a resumed stream re-emits nothing, including the half-inning end"
