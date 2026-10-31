"""Every MLB Stats API path that downloads or stores data leaves an audit trail (ADR 22)."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.audit import get_audit_logger
from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, HttpStatusError
from baseballpy.sources.mlb_api.endpoints import BY_NAME, MLB_BASE_URL, Context
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
FEED = "https://statsapi.mlb.com/api/v1.1/game/{pk}/feed/live"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _events(operation: str) -> list[Any]:
    return [e for e in get_audit_logger().read_events(source="mlb_api") if e.operation == operation]


def fast_rates() -> RateLimitConfig:
    return RateLimitConfig(
        host_rates={"statsapi.mlb.com": 1000.0},
        default_requests_per_second=1000.0,
        backoff_factor=0.01,
    )


@respx.mock
def test_a_declarative_endpoint_is_audited_cold_and_cached(tmp_path: Path) -> None:
    ep = BY_NAME["ref_game_types"]
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    respx.get(f"{MLB_BASE_URL}/{ep.path}").mock(
        return_value=httpx.Response(200, json=_fixture(ep.name))
    )
    first = extractor.ingest(ep, Context(season=2024))
    second = extractor.ingest(ep, Context(season=2024))

    events = _events(f"mlb_{ep.name}")
    assert len(events) == 2, "one event per ingest, not one per HTTP call"
    cold, cached = events
    assert cold.cache_hit is False and cold.records_count == first.rows > 0
    assert cached.cache_hit is True and cached.records_count == second.rows == first.rows
    assert cold.status == cached.status == "SUCCESS"
    assert cold.endpoint == f"{MLB_BASE_URL}/{ep.path}"
    assert "processed" in cold.destination and ep.name in cold.destination
    assert cold.duration_seconds >= 0 and cold.throughput_rps > 0


@respx.mock
def test_a_raw_only_endpoint_is_audited_cold_and_cached(tmp_path: Path) -> None:
    ep = BY_NAME["standings_postseason"]
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    route = respx.get(f"{MLB_BASE_URL}/{ep.path}").mock(
        return_value=httpx.Response(200, json={"records": [{"team": {"id": 1}}]})
    )
    first = extractor.ingest(ep, Context(season=2024))
    second = extractor.ingest(ep, Context(season=2024))

    events = _events(f"mlb_{ep.name}")
    assert len(events) == 2, "a raw-only endpoint downloads too, so it leaves one event per run"
    cold, cached = events
    assert route.call_count == 1
    assert cold.cache_hit is False and cold.records_count == first.raw_only > 0
    assert cached.cache_hit is True and cached.records_count == second.raw_only == first.raw_only
    assert cold.endpoint == f"{MLB_BASE_URL}/{ep.path}"
    assert "raw" in cold.destination and ep.name in cold.destination


@respx.mock
def test_the_pool_fallback_records_its_rows_and_refused_url(tmp_path: Path) -> None:
    ep = BY_NAME["stats_stat_splits_hitting"]
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    extractor = MlbEndpointExtractor(cache_config=lake)
    base = _fixture(ep.name)["stats"][0]["splits"][0]
    player_id = int(base["player"]["id"])
    splits = [{**base, "split": {**base.get("split", {}), "code": code}} for code in ("vr", "vl")]
    respx.get(f"{MLB_BASE_URL}/v1/stats").mock(return_value=httpx.Response(406))
    respx.get(f"{MLB_BASE_URL}/v1/sports/1/players").mock(
        return_value=httpx.Response(200, json={"people": [{"id": player_id}]})
    )
    respx.get(f"{MLB_BASE_URL}/v1/people").mock(
        return_value=httpx.Response(
            200, json={"people": [{"id": player_id, "stats": [{"splits": splits}]}]}
        )
    )
    report = extractor.ingest(ep, Context(season=2024, sport_ids=(1,), sit_codes=("vr", "vl")))

    (event,) = _events(f"mlb_{ep.name}")
    assert report.rows == len(splits) == 2
    assert event.status == "SUCCESS" and event.records_count == report.rows
    assert event.endpoint == f"{MLB_BASE_URL}/v1/stats", (
        "the refused pool route is what is recorded"
    )
    assert event.destination.endswith(".parquet")


@respx.mock
@pytest.mark.asyncio
async def test_a_projected_snapshot_is_audited_with_its_set_name(tmp_path: Path) -> None:
    doc = {
        "gameData": {"status": {"abstractGameState": "Live", "detailedState": "In Progress"}},
        "liveData": {"linescore": {"currentInning": 5, "teams": {"away": {"runs": 2}}}},
    }
    raw = json.dumps(doc).encode()
    respx.get(FEED.format(pk=7)).mock(return_value=httpx.Response(200, content=raw))
    http = HttpClient(fast_rates(), http2=False)
    try:
        streamer = GamedayLiveStreamer(http=http, lake=LakeConfig(home=tmp_path))
        await streamer.snapshot(7, fields="score")
        await streamer.snapshot_bytes(7)
    finally:
        http.close()

    (snapshot,) = _events("mlb_snapshot")
    (bytes_event,) = _events("mlb_snapshot_bytes")
    assert snapshot.destination == "score", "the set name, not the complete feed"
    assert bytes_event.destination == "complete"
    assert snapshot.records_count == bytes_event.records_count == 1
    assert snapshot.endpoint == FEED.format(pk=7)


@respx.mock
@pytest.mark.asyncio
async def test_a_finished_stream_is_audited_with_its_event_count(tmp_path: Path) -> None:
    feed = {
        "metaData": {"timeStamp": "t1"},
        "gameData": {"status": {"abstractGameState": "Final", "detailedState": "Final"}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {
                        "about": {"atBatIndex": 0},
                        "matchup": {},
                        "playEvents": [{"index": 0, "isPitch": True}],
                    }
                ]
            }
        },
    }
    respx.get(FEED.format(pk=8)).mock(return_value=httpx.Response(200, json=feed))
    http = HttpClient(fast_rates(), http2=False)
    try:
        streamer = GamedayLiveStreamer(
            poll_interval=0.001, http=http, lake=LakeConfig(home=tmp_path), use_diff_patch=False
        )
        seen = [e async for e in streamer.stream_live_events(8)]
    finally:
        http.close()

    emitted = [e for e in seen if e.event_kind == "pitch"] + [
        e for e in seen if e.event_kind == "game_status"
    ]
    (event,) = _events("mlb_stream")
    assert event.status == "SUCCESS" and event.records_count == len(emitted) > 0
    assert event.endpoint == FEED.format(pk=8)


@respx.mock
def test_a_refused_request_is_logged_as_a_failure(tmp_path: Path) -> None:
    ep = BY_NAME["ref_game_types"]
    extractor = MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path))
    respx.get(f"{MLB_BASE_URL}/{ep.path}").mock(return_value=httpx.Response(406))

    with pytest.raises(HttpStatusError):
        extractor.ingest(ep, Context(season=2024))

    (event,) = _events(f"mlb_{ep.name}")
    assert event.status == "FAILURE"
    assert "406" in (event.error or ""), "the HTTP status is in the event for `audit tail`"
    assert event.records_count == 0
