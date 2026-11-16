"""A stored game that lacks some of its URLs (a unit converted from partial old raw files) is completed by the ingest."""

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.access import read
from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import release_all
from baseballpy.core.responselog import Response
from baseballpy.core.segments import SegmentWriter
from baseballpy.sources.mlb_api import game_segments
from baseballpy.sources.mlb_api.endpoints import MLB_BASE_URL
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
SEASON = 2026
ANSWERS = {
    "v1.1/game/{pk}/feed/live": "game_feed_plays",
    "v1/game/{pk}/boxscore": "game_boxscore_pitching_notes",
    "v1/game/{pk}/linescore": "game_linescore",
    "v1/game/{pk}/winProbability": "game_win_probability",
    "v1/game/{pk}/playByPlay": "game_play_by_play",
}
PK = 850001


@pytest.fixture(autouse=True)
def _free_locks() -> Any:
    yield
    release_all()


def _extractor(tmp_path: Path) -> MlbEndpointExtractor:
    return MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path, today=date(2027, 1, 1)))


def _body(template: str) -> bytes:
    return (FIXTURES / f"{ANSWERS[template]}.json").read_bytes()


def _url(template: str, pk: int = PK) -> str:
    return f"{MLB_BASE_URL}/{template.format(pk=pk)}"


def _store_partial(extractor: MlbEndpointExtractor, have: list[str]) -> None:
    """Commit game PK with only the URLs of ``have``, as a conversion of partial old raw files does."""
    writer = SegmentWriter(
        extractor.cache_config,
        "mlb_api",
        SEASON,
        game_segments.game_normalizer(extractor.normalizer),
    )
    now = datetime.now(UTC).isoformat()
    writer.add_unit(str(PK), [Response(_url(t), _body(t), now) for t in have])
    assert writer.commit() is not None
    release_all()


def _mock(missing_status: dict[str, int] | None = None) -> dict[str, respx.Route]:
    routes = {}
    for template in ANSWERS:
        status = (missing_status or {}).get(template, 200)
        response = (
            httpx.Response(200, content=_body(template))
            if status == 200
            else httpx.Response(status, json={"message": "x"})
        )
        routes[template] = respx.get(_url(template)).mock(return_value=response)
    return routes


def _rows(config: LakeConfig, dataset: str) -> int:
    try:
        return int(read(f"mlb_api.{dataset}", SEASON, backend="pyarrow", config=config).num_rows)
    except FileNotFoundError:  # nothing written for it yet
        return 0


@respx.mock
def test_only_the_missing_urls_are_fetched_and_the_game_gets_all_its_rows(tmp_path: Path) -> None:
    extractor = _extractor(tmp_path)
    _store_partial(extractor, ["v1/game/{pk}/boxscore", "v1/game/{pk}/winProbability"])
    assert _rows(extractor.cache_config, "game_linescore") == 0
    routes = _mock()
    report = game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    called = {t for t, r in routes.items() if r.call_count}
    assert called == {
        "v1.1/game/{pk}/feed/live",
        "v1/game/{pk}/linescore",
        "v1/game/{pk}/playByPlay",
    }
    assert report.completed == 1 and report.stored == 0 and report.failed == {}
    assert _rows(extractor.cache_config, "game_linescore") > 0
    assert _rows(extractor.cache_config, "game_feed_plays") > 0


@respx.mock
def test_a_second_run_asks_for_nothing(tmp_path: Path) -> None:
    extractor = _extractor(tmp_path)
    _store_partial(extractor, ["v1/game/{pk}/boxscore"])
    routes = _mock()
    game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    release_all()
    before = {t: r.call_count for t, r in routes.items()}
    again = game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    assert {t: r.call_count for t, r in routes.items()} == before and again.completed == 0


@respx.mock
def test_an_answer_of_404_for_a_tolerated_url_is_stored_so_it_is_not_asked_again(
    tmp_path: Path,
) -> None:
    extractor = _extractor(tmp_path)
    have = [t for t in ANSWERS if t != "v1/game/{pk}/winProbability"]
    _store_partial(extractor, have)
    routes = _mock({"v1/game/{pk}/winProbability": 404})
    report = game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    assert report.completed == 1 and report.failed == {}
    assert routes["v1/game/{pk}/winProbability"].call_count == 1
    release_all()
    before = {t: r.call_count for t, r in routes.items()}
    game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    asked = [t for t, r in routes.items() if r.call_count != before[t]]
    assert not asked, f"the 404 is on record, yet these were asked again: {asked}"


@respx.mock
def test_a_server_error_while_completing_fails_the_game_and_keeps_what_was_stored(
    tmp_path: Path,
) -> None:
    extractor = _extractor(tmp_path)
    _store_partial(extractor, ["v1/game/{pk}/boxscore"])
    _mock({"v1.1/game/{pk}/feed/live": 500})
    report = game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    assert report.completed == 0 and PK in report.failed
    assert _rows(extractor.cache_config, "game_boxscore_pitching_notes") > 0


@respx.mock
def test_a_game_that_is_not_in_the_requested_list_is_left_alone(tmp_path: Path) -> None:
    extractor = _extractor(tmp_path)
    _store_partial(extractor, ["v1/game/{pk}/boxscore"])
    routes = _mock()
    report = game_segments.ingest_game_segments(extractor, SEASON, ())
    assert not any(r.call_count for r in routes.values()) and report.completed == 0
    assert json.dumps(sorted(report.failed)) is not None


@respx.mock
def test_a_stored_game_that_the_provider_cannot_serve_is_not_completed_and_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A known-unavailable game that is stored with a few URLs (from old raw files) is left as it is."""
    extractor = _extractor(tmp_path)
    _store_partial(extractor, ["v1/game/{pk}/boxscore"])
    monkeypatch.setattr(
        game_segments, "known_unavailable_games", lambda: {PK: {"status": 500, "season": SEASON}}
    )
    routes = _mock({"v1.1/game/{pk}/feed/live": 500})
    report = game_segments.ingest_game_segments(extractor, SEASON, (PK,))
    assert not any(r.call_count for r in routes.values())
    assert report.failed == {} and report.unavailable == [PK] and report.completed == 0
