"""Regression tests for source-level hardening (freshness, truncation, absent files, drift)."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from baseballpy.core.audit import get_audit_logger
from baseballpy.core.config import LakeConfig, QuarantineConfig, RateLimitConfig, StreamingConfig
from baseballpy.core.http import HttpClient
from baseballpy.core.quarantine import Quarantine
from baseballpy.sources.chadwick.extractor import (
    CHADWICK_COMMITS_API,
    CHADWICK_DATA_BASE_URL,
    HEX_SHARDS,
    ChadwickExtractor,
)
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.mlb_api.extractor import MLB_BASE_URL, MlbApiExtractor
from baseballpy.sources.mlb_api.stream import GamedayLiveStreamer
from baseballpy.sources.retrosheet.downloader import GITHUB_RETROSHEET_BASE, RetrosheetDownloader
from baseballpy.sources.retrosheet.parser import RetrosheetReferenceParser
from baseballpy.sources.statcast import extractor as statcast_mod
from baseballpy.sources.statcast.extractor import (
    SAVANT_BASE_URL,
    StatcastExtractor,
    TruncatedResultError,
)

FIXTURES = Path(__file__).parent / "fixtures"
PITCH_LINES = (FIXTURES / "statcast" / "sample_pitches.csv").read_text().splitlines()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Send audit/quarantine output to tmp_path and reset the lazy audit logger."""
    home = tmp_path / "home"
    monkeypatch.setenv("BASEBALLPY_HOME", str(home))
    get_audit_logger.reset()
    yield home
    get_audit_logger.reset()


def fast_rates(*hosts: str, **kw: float | int) -> RateLimitConfig:
    return RateLimitConfig(
        host_rates={h: 1000.0 for h in hosts},
        default_requests_per_second=1000.0,
        backoff_factor=0.01,
        **kw,  # type: ignore[arg-type]
    )


def make_csv(rows: int) -> bytes:
    body = [PITCH_LINES[0]] + [PITCH_LINES[1 + (i % 2)] for i in range(rows)]
    return ("\n".join(body) + "\n").encode()


# ----------------------------------------------------------------------------- statcast


def _statcast(tmp_path: Path, today: date, **cfg: object) -> tuple[StatcastExtractor, HttpClient]:
    rates = fast_rates("baseballsavant.mlb.com")
    http = HttpClient(rates, http2=False)
    cache = LakeConfig(home=tmp_path / "cache", today=today, **cfg)  # type: ignore[arg-type]
    return StatcastExtractor(cache_config=cache, rate_limit_config=rates, http=http), http


@respx.mock
def test_statcast_bisects_when_row_cap_is_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(statcast_mod, "SAVANT_ROW_CAP", 3)
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params
        start, end = q["game_date_gt"], q["game_date_lt"]
        seen.append((start, end))
        return httpx.Response(200, content=make_csv(3 if start != end else 2))

    respx.get(SAVANT_BASE_URL).mock(side_effect=handler)
    extractor, http = _statcast(tmp_path, date(2026, 6, 1))
    try:
        table = extractor.extract("2024-04-01", "2024-04-05")
    finally:
        http.close()
    assert len(table) == 10  # five single-day leaves x 2 rows, no duplicates, nothing truncated
    leaves = {w for w in seen if w[0] == w[1]}
    assert leaves == {(f"2024-04-0{d}", f"2024-04-0{d}") for d in range(1, 6)}
    ops = [e.operation for e in get_audit_logger().read_events()]
    assert "statcast_row_cap_bisect" in ops


@respx.mock
def test_statcast_single_day_at_cap_raises_and_is_not_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(statcast_mod, "SAVANT_ROW_CAP", 3)
    respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=make_csv(3)))
    extractor, http = _statcast(tmp_path, date(2026, 6, 1))
    try:
        with pytest.raises(TruncatedResultError):
            extractor.extract("2024-04-01", "2024-04-01")
    finally:
        http.close()
    assert list((tmp_path / "cache").rglob("*.parquet")) == []
    assert extractor.manifest.get_chunk("season=2024/2024-04-01_2024-04-01") is None


@respx.mock
def test_statcast_empty_historical_chunk_is_cached_not_refetched(tmp_path: Path) -> None:
    route = respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=b""))
    extractor, http = _statcast(tmp_path, date(2026, 6, 1))
    try:
        assert len(extractor.extract("2024-01-01", "2024-01-03")) == 0
        assert len(extractor.extract("2024-01-01", "2024-01-03")) == 0
    finally:
        http.close()
    assert route.call_count == 1
    events = get_audit_logger().read_events()
    extract_events = [e for e in events if e.operation == "statcast_extract"]
    assert [e.cache_hit for e in extract_events] == [False, True]


@respx.mock
def test_statcast_current_season_chunk_expires_with_ttl(tmp_path: Path) -> None:
    route = respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=make_csv(2)))
    today = date(2026, 6, 1)
    extractor, http = _statcast(tmp_path, today)
    try:
        extractor.extract("2026-05-01", "2026-05-05")
        extractor.extract("2026-05-01", "2026-05-05")  # within TTL -> cache
        assert route.call_count == 1
        expired, http2 = _statcast(tmp_path, today, ttl_overrides={"statcast": 0})
        try:
            expired.extract("2026-05-01", "2026-05-05")
        finally:
            http2.close()
    finally:
        http.close()
    assert route.call_count == 2


@respx.mock
def test_statcast_recent_days_always_revalidated(tmp_path: Path) -> None:
    route = respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(200, content=make_csv(2)))
    extractor, http = _statcast(tmp_path, date(2026, 6, 1))
    try:
        extractor.extract("2026-05-30", "2026-05-31")
        extractor.extract("2026-05-30", "2026-05-31")
    finally:
        http.close()
    assert route.call_count == 2


@respx.mock
def test_statcast_does_not_retry_client_errors(tmp_path: Path) -> None:
    route = respx.get(SAVANT_BASE_URL).mock(return_value=httpx.Response(400))
    extractor, http = _statcast(tmp_path, date(2026, 6, 1))
    try:
        with pytest.raises(Exception, match="400"):
            extractor.extract("2024-04-01", "2024-04-01")
    finally:
        http.close()
    assert route.call_count == 1


def test_statcast_normalizer_quarantines_instead_of_truncating(tmp_path: Path) -> None:
    from baseballpy.sources.statcast.normalizer import StatcastNormalizer

    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    csv = (
        b"game_pk,game_date,at_bat_number,release_speed\n"
        b"1,2024-04-05,1.9,95.5\n"
        b"2,not-a-date,2,96.0\n"
    )
    table = StatcastNormalizer(quarantine=q).normalize(csv)
    assert table["at_bat_number"].to_pylist()[0] is None  # 1.9 never truncated to 1
    assert table["at_bat_number"].to_pylist()[1] == 2
    assert table["game_date"].to_pylist()[1] is None
    reasons = [
        json.loads(line)["reason"]
        for f in (tmp_path / "quarantine").rglob("*.jsonl")
        for line in f.read_text().splitlines()
    ]
    assert any("at_bat_number" in r for r in reasons)
    assert any("game_date" in r for r in reasons)


# ----------------------------------------------------------------------------- mlb


def _mlb(tmp_path: Path, **cfg: object) -> tuple[MlbApiExtractor, HttpClient]:
    rates = fast_rates("statsapi.mlb.com")
    http = HttpClient(rates, http2=False)
    cache = LakeConfig(home=tmp_path / "cache", today=date(2026, 6, 1), **cfg)  # type: ignore[arg-type]
    return MlbApiExtractor(cache_config=cache, rate_limit_config=rates, http=http), http


def _box_payload() -> dict[str, object]:
    return {
        "teams": {
            "away": {
                "team": {"id": 119},
                "players": {
                    "ID1": {
                        "person": {"id": 1, "fullName": "A Batter"},
                        "position": {"abbreviation": "DH"},
                        "stats": {"batting": {"atBats": 4, "hits": 1}},
                    }
                },
            },
            "home": {
                "team": {"id": 111},
                "players": {
                    "ID2": {
                        "person": {"id": 2, "fullName": "A Pitcher"},
                        "position": {"abbreviation": "P"},
                        "stats": {"pitching": {"inningsPitched": "6.0", "strikeOuts": 7}},
                    }
                },
            },
        }
    }


def _sched_payload(pk: int, state: str) -> dict[str, object]:
    return {
        "dates": [
            {
                "date": "2026-05-30",
                "games": [{"gamePk": pk, "status": {"abstractGameState": state}}],
            }
        ]
    }


@respx.mock
def test_mlb_boxscore_cached_forever_only_after_final(tmp_path: Path) -> None:
    box = respx.get(f"{MLB_BASE_URL}/v1/game/99/boxscore").mock(
        return_value=httpx.Response(200, json=_box_payload())
    )
    sched = respx.get(f"{MLB_BASE_URL}/v1/schedule").mock(
        return_value=httpx.Response(200, json=_sched_payload(99, "Live"))
    )
    extractor, http = _mlb(tmp_path, ttl_overrides={"boxscore": 0})
    try:
        extractor.extract_boxscore(99)
        extractor.extract_boxscore(99)  # live game: TTL 0 -> refetch, never frozen
        assert box.call_count == 2
        sched.mock(return_value=httpx.Response(200, json=_sched_payload(99, "Final")))
        extractor.extract_boxscore(99)  # refetch; now recorded final
        assert box.call_count == 3
        extractor.extract_boxscore(99)
        extractor.extract_boxscore(99)
        assert box.call_count == 3  # immutable once final
    finally:
        http.close()


@respx.mock
def test_mlb_current_season_schedule_expires_but_past_season_does_not(tmp_path: Path) -> None:
    payload = {"dates": [{"date": "2026-04-01", "games": [{"gamePk": 1, "gameType": "R"}]}]}
    route = respx.get(f"{MLB_BASE_URL}/v1/schedule").mock(
        return_value=httpx.Response(200, json=payload)
    )
    extractor, http = _mlb(tmp_path, ttl_overrides={"schedule": 0})
    try:
        extractor.extract_schedule(season=2026)
        extractor.extract_schedule(season=2026)
        assert route.call_count == 2  # current season, TTL 0
        extractor.extract_schedule(season=2024)
        extractor.extract_schedule(season=2024)
        assert route.call_count == 3  # historical season fetched once, then immutable
    finally:
        http.close()


@respx.mock
def test_mlb_cache_hit_is_audited(tmp_path: Path) -> None:
    respx.get(f"{MLB_BASE_URL}/v1/teams").mock(
        return_value=httpx.Response(200, json={"teams": [{"id": 1, "name": "X"}]})
    )
    extractor, http = _mlb(tmp_path)
    try:
        extractor.extract_teams()
        extractor.extract_teams()
    finally:
        http.close()
    hits = [e for e in get_audit_logger().read_events() if e.operation == "mlb_api_cache_read"]
    assert hits and hits[0].cache_hit is True


# ----------------------------------------------------------------------------- streamer


def _live(ts: str, state: str, events: list[dict[str, object]]) -> dict[str, object]:
    return {
        "metaData": {"timeStamp": ts},
        "gameData": {"status": {"abstractGameState": state, "detailedState": state}},
        "liveData": {
            "plays": {
                "allPlays": [
                    {"about": {"atBatIndex": 0}, "matchup": {}, "playEvents": events},
                ]
            }
        },
    }


@respx.mock
@pytest.mark.asyncio
async def test_streamer_skips_unchanged_timestamp_and_stops_on_final() -> None:
    ev0 = {"index": 0, "isPitch": True}
    ev1 = {"index": 1, "isPitch": True}
    url = "https://statsapi.mlb.com/api/v1.1/game/7/feed/live"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(200, json=_live("t1", "Live", [ev0])),
            httpx.Response(200, json=_live("t1", "Live", [ev0, ev1])),  # same stamp: not parsed
            httpx.Response(200, json=_live("t2", "Final", [ev0, ev1])),
        ]
    )
    http = HttpClient(fast_rates("statsapi.mlb.com"), http2=False)
    try:
        streamer = GamedayLiveStreamer(7, poll_interval=0.001, http=http)
        events = [e async for e in streamer.stream_events()]
    finally:
        http.close()
    assert [e["event_index"] for e in events] == [0, 1]


@respx.mock
@pytest.mark.asyncio
async def test_streamer_propagates_network_failure_instead_of_swallowing() -> None:
    respx.get("https://statsapi.mlb.com/api/v1.1/game/8/feed/live").mock(
        return_value=httpx.Response(503)
    )
    http = HttpClient(fast_rates("statsapi.mlb.com", max_retries=2), http2=False)
    try:
        streamer = GamedayLiveStreamer(8, poll_interval=0.001, http=http)
        with pytest.raises(Exception, match="503"):
            async for _ in streamer.stream_events():
                pass
    finally:
        http.close()
    statuses = [e.status for e in get_audit_logger().read_events() if e.operation == "mlb_stream"]
    assert statuses == ["FAILURE"]


@respx.mock
@pytest.mark.asyncio
async def test_streamer_quarantines_malformed_payload(tmp_path: Path) -> None:
    respx.get("https://statsapi.mlb.com/api/v1.1/game/9/feed/live").mock(
        side_effect=[
            httpx.Response(200, content=b"{not json"),
            httpx.Response(200, json=_live("t1", "Final", [{"index": 0}])),
        ]
    )
    http = HttpClient(fast_rates("statsapi.mlb.com"), http2=False)
    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    try:
        streamer = GamedayLiveStreamer(9, poll_interval=0.001, http=http, quarantine=q)
        events = [e async for e in streamer.stream_events()]
    finally:
        http.close()
    assert len(events) == 1
    assert list((tmp_path / "quarantine" / "mlb_api").rglob("*.jsonl"))


@respx.mock
@pytest.mark.asyncio
async def test_streamer_stops_after_inactivity_limit() -> None:
    respx.get("https://statsapi.mlb.com/api/v1.1/game/10/feed/live").mock(
        return_value=httpx.Response(200, json=_live("t1", "Preview", []))
    )
    http = HttpClient(fast_rates("statsapi.mlb.com"), http2=False)
    try:
        streamer = GamedayLiveStreamer(
            10, poll_interval=0.001, http=http, config=StreamingConfig(max_inactivity_minutes=0)
        )
        assert [e async for e in streamer.stream_events()] == []
    finally:
        http.close()


# ----------------------------------------------------------------------------- retrosheet


def _retro(tmp_path: Path) -> tuple[RetrosheetDownloader, HttpClient]:
    rates = fast_rates("raw.githubusercontent.com")
    http = HttpClient(rates, http2=False)
    cache = LakeConfig(home=tmp_path / "cache")
    return RetrosheetDownloader(cache_config=cache, rate_limit_config=rates, http=http), http


@respx.mock
def test_retrosheet_missing_event_file_is_absent_not_completed(tmp_path: Path) -> None:
    base = f"{GITHUB_RETROSHEET_BASE}/seasons/2001"
    respx.get(f"{base}/TEAM2001").mock(
        return_value=httpx.Response(200, text="BOS,A,Boston,Red Sox\nNYN,N,New York,Mets\n")
    )
    respx.get(f"{base}/2001BOS.EVA").mock(return_value=httpx.Response(200, content=b"id,x\n"))
    respx.get(f"{base}/BOS2001.ROS").mock(return_value=httpx.Response(200, content=b"r\n"))
    respx.get(f"{base}/NYN2001.ROS").mock(return_value=httpx.Response(200, content=b"r\n"))
    respx.get(f"{base}/2001NYN.EVN").mock(return_value=httpx.Response(404))
    dl, http = _retro(tmp_path)
    try:
        files = dl.download_season(2001)
    finally:
        http.close()
    assert [f.name for f in files] == ["2001BOS.EVA"]
    chunk = dl.manifest.get_chunk("season_2001")
    assert chunk is not None and chunk["status"] == "ABSENT"
    assert "2001NYN.EVN" in chunk["reason"]
    assert not dl.manifest.is_completed("season_2001")


@respx.mock
def test_retrosheet_complete_season_is_recorded_and_resumes(tmp_path: Path) -> None:
    base = f"{GITHUB_RETROSHEET_BASE}/seasons/2002"
    respx.get(f"{base}/TEAM2002").mock(
        return_value=httpx.Response(200, text="BOS,A,Boston,Red Sox\n")
    )
    ev = respx.get(f"{base}/2002BOS.EVA").mock(return_value=httpx.Response(200, content=b"id,x\n"))
    respx.get(f"{base}/BOS2002.ROS").mock(return_value=httpx.Response(200, content=b"r\n"))
    dl, http = _retro(tmp_path)
    try:
        dl.download_season(2002)
        assert dl.manifest.is_completed("season_2002")
        again = dl.download_season(2002)
    finally:
        http.close()
    assert ev.call_count == 1
    assert [f.name for f in again] == ["2002BOS.EVA"]
    assert [e.cache_hit for e in get_audit_logger().read_events()][-1] is True


@respx.mock
def test_retrosheet_missing_team_file_is_absent(tmp_path: Path) -> None:
    respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/1800/TEAM1800").mock(
        return_value=httpx.Response(404)
    )
    dl, http = _retro(tmp_path)
    try:
        assert dl.download_season(1800) == []
    finally:
        http.close()
    chunk = dl.manifest.get_chunk("season_1800")
    assert chunk is not None and chunk["status"] == "ABSENT"


@respx.mock
def test_retrosheet_missing_gamelog_raises_not_silently_empty(tmp_path: Path) -> None:
    for cand in (
        "seasons/1800/GL1800.TXT",
        "seasons/1800/gl1800.txt",
        "gamelog/gl1800.txt",
        "gamelog/GL1800.TXT",
    ):
        respx.get(f"{GITHUB_RETROSHEET_BASE}/{cand}").mock(return_value=httpx.Response(404))
    dl, http = _retro(tmp_path)
    try:
        with pytest.raises(FileNotFoundError):
            dl.download_gamelog(1800)
    finally:
        http.close()
    assert not dl.manifest.is_completed("gamelog_1800")


def test_retrosheet_reference_header_drift_preserves_extra_columns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    csv = tmp_path / "ballparks.csv"
    csv.write_text(
        "PARKID,NAME,AKA,CITY,STATE,START,END,LEAGUE,NOTES,CAPACITY\n"
        "BOS07,Fenway,,Boston,MA,1912,,AL,,37755\n",
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        table = RetrosheetReferenceParser().parse_file("ballparks", csv)
    assert "capacity" in table.column_names
    assert table["capacity"].to_pylist() == ["37755"]
    assert table["park_id"].to_pylist() == ["BOS07"]
    assert any("header has 10" in r.message for r in caplog.records)


def test_retrosheet_parser_quarantines_uncoercible_ints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path / "qhome"))
    from baseballpy.core.quarantine import get_quarantine

    get_quarantine.reset()
    csv = tmp_path / "teams.csv"
    csv.write_text("TEAM,LEAGUE,CITY,NICKNAME,FIRST,LAST\nBOS,AL,Boston,Red Sox,notayear,2025\n")
    try:
        table = RetrosheetReferenceParser().parse_file("teams", csv)
        assert table["first_year"].to_pylist() == [None]
        assert table["last_year"].to_pylist() == [2025]
        assert list((tmp_path / "qhome" / "quarantine" / "retrosheet").rglob("*.jsonl"))
    finally:
        get_quarantine.reset()


# ----------------------------------------------------------------------------- lahman


def test_lahman_normalizer_preserves_unknown_columns_and_quarantines_bad_cells(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    csv = (
        "playerID,yearID,stint,teamID,lgID,G,newMetric\n"
        "aaronha01,1957,1,ML1,NL,151,7\n"
        "badrow01,notayear,1,ML1,NL,1,8\n"
    )
    with caplog.at_level("WARNING"):
        table = LahmanNormalizer(quarantine=q).normalize(csv, table_name="Batting")
    assert "newMetric" not in table.column_names
    assert [json.loads(x) for x in table["_extras"].to_pylist()] == [
        {"newMetric": "7"},
        {"newMetric": "8"},
    ]
    assert table["yearID"].to_pylist() == [1957, None]
    assert any("schema_drift" in r.message for r in caplog.records)
    assert list((tmp_path / "quarantine" / "lahman").rglob("*.jsonl"))


@respx.mock
def test_lahman_cache_requires_manifest_completion(tmp_path: Path) -> None:
    from baseballpy.sources.lahman.extractor import LAHMAN_GITHUB_BASE, LahmanExtractor

    route = respx.get(f"{LAHMAN_GITHUB_BASE}/Parks.csv").mock(
        return_value=httpx.Response(200, content=b"parkkey\nBOS07\n")
    )
    rates = fast_rates("raw.githubusercontent.com")
    http = HttpClient(rates, http2=False)
    ext = LahmanExtractor(
        cache_config=LakeConfig(home=tmp_path / "c"), rate_limit_config=rates, http=http
    )
    try:
        # A leftover, never-completed file must NOT be trusted as a cache hit.
        ext.get_raw_path("Parks").parent.mkdir(parents=True)
        ext.get_raw_path("Parks").write_bytes(b"corrupt partial")
        assert ext.extract_table("Parks") == b"parkkey\nBOS07\n"
        assert ext.extract_table("Parks") == b"parkkey\nBOS07\n"
    finally:
        http.close()
    assert route.call_count == 1


def test_lahman_source_url_is_owner_repo_only() -> None:
    from baseballpy.sources.lahman.extractor import LAHMAN_GITHUB_BASE

    assert "cbwinslow/lahman-database-csv" in LAHMAN_GITHUB_BASE
    assert "baseballdatabank" not in LAHMAN_GITHUB_BASE


# ----------------------------------------------------------------------------- chadwick


FLOATING_CHADWICK = "https://raw.githubusercontent.com/chadwickbureau/register/master/data"


def _mock_register(
    sha: str = "sha1", status: int = 200, base: str = CHADWICK_DATA_BASE_URL
) -> None:
    respx.get(CHADWICK_COMMITS_API).mock(return_value=httpx.Response(200, json=[{"sha": sha}]))
    for shard in HEX_SHARDS:
        respx.get(f"{base}/{shard}").mock(
            return_value=httpx.Response(status, content=b"key_person\nx\n")
        )
    respx.get(f"{base}/names.csv").mock(
        return_value=httpx.Response(200, content=b"key_person\nx\n")
    )
    respx.get(f"{base}/links.csv").mock(return_value=httpx.Response(404))


def _chadwick(
    tmp_path: Path, ref: str | None = None, **cfg: object
) -> tuple[ChadwickExtractor, HttpClient]:
    rates = fast_rates("raw.githubusercontent.com", "api.github.com")
    http = HttpClient(rates, http2=False)
    cache = LakeConfig(home=tmp_path / "c", **cfg)  # type: ignore[arg-type]
    return ChadwickExtractor(cache_config=cache, rate_limit_config=rates, http=http, ref=ref), http


@respx.mock
def test_chadwick_missing_shard_is_hard_error(tmp_path: Path) -> None:
    _mock_register()
    respx.get(f"{CHADWICK_DATA_BASE_URL}/people-7.csv").mock(return_value=httpx.Response(404))
    ext, http = _chadwick(tmp_path)
    try:
        with pytest.raises(Exception, match="404"):
            ext.extract(refresh=True)
    finally:
        http.close()
    assert not ext.manifest.is_completed("commit_sha")


@respx.mock
def test_chadwick_revalidates_sha_after_ttl_and_refetches_on_change(tmp_path: Path) -> None:
    _mock_register("sha1", base=FLOATING_CHADWICK)
    ext, http = _chadwick(tmp_path, ref="master", ttl_overrides={"chadwick": 0})
    try:
        ext.extract(refresh=True)
        shard = respx.get(f"{FLOATING_CHADWICK}/people-0.csv")
        before = shard.call_count
        ext.extract()  # TTL 0 -> revalidate; same sha -> served from cache, no shard download
        assert shard.call_count == before
        respx.get(CHADWICK_COMMITS_API).mock(
            return_value=httpx.Response(200, json=[{"sha": "sha2"}])
        )
        ext.extract()  # sha changed -> full re-download
        assert shard.call_count == before + 1
        assert ext.manifest.get_chunk("commit_sha")["sha"] == "sha2"  # type: ignore[index]
    finally:
        http.close()


@respx.mock
def test_chadwick_sha_failure_is_logged_and_cache_served(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_register("sha1", base=FLOATING_CHADWICK)
    ext, http = _chadwick(tmp_path, ref="master", ttl_overrides={"chadwick": 0})
    try:
        ext.extract(refresh=True)
        respx.get(CHADWICK_COMMITS_API).mock(return_value=httpx.Response(403))
        with caplog.at_level("WARNING"):
            files = ext.extract()
    finally:
        http.close()
    assert "people-0.csv" in files
    assert any("Chadwick" in r.message for r in caplog.records)


@respx.mock
def test_retrosheet_allstar_pseudo_teams_may_be_absent(tmp_path: Path) -> None:
    base = f"{GITHUB_RETROSHEET_BASE}/seasons/2003"
    respx.get(f"{base}/TEAM2003").mock(
        return_value=httpx.Response(
            200, text="BOS,A,Boston,Red Sox\nALS,A,All-Star,AL\nNLS,N,All-Star,NL\n"
        )
    )
    respx.get(f"{base}/2003BOS.EVA").mock(return_value=httpx.Response(200, content=b"id,x\n"))
    respx.get(f"{base}/BOS2003.ROS").mock(return_value=httpx.Response(200, content=b"r\n"))
    for name in ("2003ALS.EVA", "ALS2003.ROS", "2003NLS.EVN", "NLS2003.ROS"):
        respx.get(f"{base}/{name}").mock(return_value=httpx.Response(404))
    dl, http = _retro(tmp_path)
    try:
        files = dl.download_season(2003)
    finally:
        http.close()
    assert [f.name for f in files] == ["2003BOS.EVA"]
    assert dl.manifest.is_completed("season_2003")


@respx.mock
def test_chadwick_pinned_ref_needs_no_api_call_and_records_source_ref(tmp_path: Path) -> None:
    from baseballpy.core.sources_lock import get_source_ref

    _mock_register("ignored")
    api = respx.get(CHADWICK_COMMITS_API)
    ext, http = _chadwick(tmp_path, ttl_overrides={"chadwick": 0})
    try:
        ext.extract(refresh=True)
        ext.extract()  # pinned + same ref: current regardless of TTL
    finally:
        http.close()
    ref = get_source_ref("chadwick_register").ref
    assert api.call_count == 0
    assert ext.manifest.get_chunk("commit_sha")["sha"] == ref  # type: ignore[index]
    entry = ext.manifest.get_chunk("people-0.csv")
    assert entry is not None and entry["source_ref"] == ref


@respx.mock
def test_chadwick_changed_pinned_ref_invalidates_cache(tmp_path: Path) -> None:
    other = "https://raw.githubusercontent.com/chadwickbureau/register/" + "a" * 40 + "/data"
    _mock_register()
    _mock_register(base=other)
    ext, http = _chadwick(tmp_path)
    ext2, http2 = _chadwick(tmp_path, ref="a" * 40)
    try:
        ext.extract(refresh=True)
        shard = respx.get(f"{other}/people-0.csv")
        assert not ext2.is_cache_current(refresh=False)  # different ref -> stale
        ext2.extract()
        assert shard.call_count == 1
        assert ext2.is_cache_current(refresh=False)
    finally:
        http.close()
        http2.close()
