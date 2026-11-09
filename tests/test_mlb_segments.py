"""The MLB per-game download on segments (ADR 95): each URL once, the same rows as before.

Written first (task 4.1, B-367); ``baseballpy.sources.mlb_api.game_segments`` (task 4.2, B-368) made
them pass.

The interface these tests fix:

* ``game_url_groups()``: the URLs of one game and the datasets cut from each, taken from the endpoint
  registry (``scope="game"``, same path = same URL); no list of datasets lives anywhere else.
* ``ingest_game_segments(extractor, season, game_pks, *, segment_games=250, segment_seconds=600.0)``:
  for every game not yet stored, fetch each URL once, decode it once (``game_segments.decode_body``,
  the only place a body is decoded), cut every dataset of the URL from the decoded value, journal the
  responses, and commit a segment every ``segment_games`` games or ``segment_seconds``; the last
  open segment is committed at the end. It returns a report with ``stored`` (games stored by this
  call), ``already`` (games skipped because they were stored before), ``failed`` (``{game_pk: why}``)
  and ``segments`` (committed by this call).
* A game is stored only if every URL answered 200 with a body that decodes, or answered 404 for a
  dataset whose endpoint has ``tolerate_missing`` (a cancelled game has no win probability: the 404
  is kept as a raw row with status 404 and its datasets get no rows). Any other 404, an empty body
  or a body that does not decode makes the game failed, and it is fetched again on the next run.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.access import read
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import LINEAGE_COLUMN
from baseballpy.core.hostlock import release_all
from baseballpy.sources.mlb_api import generic
from baseballpy.sources.mlb_api.endpoints import MLB_BASE_URL, SUPPORTED, Context
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor
from baseballpy.sources.mlb_api.mlb_schema import MLB_SCHEMAS

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
SEASON = 2024
#: URL path of a game -> the fixture that is a real answer for it (one fixture serves every dataset of its URL)
ANSWERS = {
    "v1.1/game/{pk}/feed/live": "game_feed_plays",
    "v1/game/{pk}/boxscore": "game_boxscore_pitching_notes",
    "v1/game/{pk}/linescore": "game_linescore",
    "v1/game/{pk}/winProbability": "game_win_probability",
    "v1/game/{pk}/playByPlay": "game_play_by_play",
}
GAME_DATASETS = sorted(e.name for e in SUPPORTED if e.scope == "game" and e.name in MLB_SCHEMAS)
PKS = (745000, 745001, 745002)


@pytest.fixture(autouse=True)
def _free_locks() -> Any:
    yield
    release_all()


def _api() -> Any:
    import baseballpy.sources.mlb_api.game_segments as module  # type: ignore[import-not-found]

    return module


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _extractor(tmp_path: Path) -> MlbEndpointExtractor:
    return MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path, today=date(2026, 6, 1)))


def _mock_games(
    pks: tuple[int, ...], overrides: dict[tuple[int, str], httpx.Response] | None = None
) -> dict[tuple[int, str], respx.Route]:
    """Every URL of every game answers with its fixture, unless ``overrides`` says otherwise."""
    routes: dict[tuple[int, str], respx.Route] = {}
    for pk in pks:
        for template, fixture in ANSWERS.items():
            response = (overrides or {}).get((pk, template)) or httpx.Response(
                200, json=_fixture(fixture)
            )
            routes[(pk, template)] = respx.get(f"{MLB_BASE_URL}/{template.format(pk=pk)}").mock(
                return_value=response
            )
    return routes


def _calls(routes: dict[tuple[int, str], respx.Route]) -> dict[tuple[int, str], int]:
    return {key: route.call_count for key, route in routes.items()}


@respx.mock
def test_each_game_url_is_fetched_and_parsed_once_for_all_its_datasets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _api()
    groups = module.game_url_groups()
    assert sorted(g.path for g in groups) == sorted(t.replace("{pk}", "{game_pk}") for t in ANSWERS)
    assert sorted(name for g in groups for name in g.datasets) == GAME_DATASETS
    assert len(GAME_DATASETS) == 13 and len(groups) == 5

    decoded: list[int] = []
    real_decode = module.decode_body

    def counting_decode(body: bytes) -> Any:
        decoded.append(len(body))
        return real_decode(body)

    monkeypatch.setattr(module, "decode_body", counting_decode)
    routes = _mock_games(PKS)
    extractor = _extractor(tmp_path)
    report = module.ingest_game_segments(extractor, SEASON, PKS)

    assert report.stored == 3 and report.failed == {} and report.segments == 1
    assert set(_calls(routes).values()) == {1}, "every URL of every game is requested once"
    assert len(decoded) == 15, "five bodies per game decoded once each, not once per dataset"

    config = extractor.cache_config
    raw_dir = config.raw_root / "mlb_api"
    assert sorted(p.name for p in raw_dir.iterdir()) == [f"season={SEASON}"], (
        "no per-dataset raw folder"
    )
    assert not list(raw_dir.rglob("*.gz")) and not list(raw_dir.rglob("_manifest.json"))
    for name in GAME_DATASETS:
        files = list(config.processed_dir("mlb_api", name, SEASON).glob("seg-*.parquet"))
        assert len(files) == 1, name


@respx.mock
def test_segment_rows_equal_the_old_per_game_rows(tmp_path: Path) -> None:
    module = _api()
    old_home, new_home = tmp_path / "old", tmp_path / "new"
    _mock_games(PKS)
    old = _extractor(old_home)
    for name in GAME_DATASETS:
        old.ingest(name, Context(season=SEASON, game_pks=PKS))
    new = _extractor(new_home)
    module.ingest_game_segments(new, SEASON, PKS)

    for name in GAME_DATASETS:
        before = generic.read_endpoint(name, SEASON, old.cache_config)
        after = read(
            f"mlb_api.{name}", SEASON, backend="pyarrow", config=new.cache_config
        ).drop_columns([LINEAGE_COLUMN])
        assert after.num_rows == before.num_rows, name
        columns = [c for c in before.column_names if c != "season"]
        key = [(c, "ascending") for c in columns]
        assert after.select(columns).sort_by(key).to_pylist() == (
            before.select(columns).sort_by(key).to_pylist()
        ), name


@respx.mock
def test_an_empty_or_failed_response_never_marks_a_game_complete(tmp_path: Path) -> None:
    module = _api()
    good, empty_feed, no_box, no_odds = 745000, 745001, 745002, 745003
    routes = _mock_games(
        (good, empty_feed, no_box, no_odds),
        {
            (empty_feed, "v1.1/game/{pk}/feed/live"): httpx.Response(200, content=b""),
            (no_box, "v1/game/{pk}/boxscore"): httpx.Response(404),
            (no_odds, "v1/game/{pk}/winProbability"): httpx.Response(404),
        },
    )
    extractor = _extractor(tmp_path)
    pks = (good, empty_feed, no_box, no_odds)
    report = module.ingest_game_segments(extractor, SEASON, pks)

    assert report.stored == 2, "the good game and the cancelled-game style 404 that is tolerated"
    assert set(report.failed) == {empty_feed, no_box}
    assert "empty" in report.failed[empty_feed] and "404" in report.failed[no_box]
    rows = read(
        "mlb_api.game_win_probability", SEASON, backend="pyarrow", config=extractor.cache_config
    )
    assert sorted(set(rows.column("game_pk").to_pylist())) == [good], "a tolerated 404 adds no rows"

    # the next run fetches only the failed games again, and finishes them once the provider answers
    before = _calls(routes)
    respx.get(f"{MLB_BASE_URL}/v1.1/game/{empty_feed}/feed/live").mock(
        return_value=httpx.Response(200, json=_fixture("game_feed_plays"))
    )
    respx.get(f"{MLB_BASE_URL}/v1/game/{no_box}/boxscore").mock(
        return_value=httpx.Response(200, json=_fixture("game_boxscore_pitching_notes"))
    )
    again = module.ingest_game_segments(extractor, SEASON, pks)
    assert again.already == 2 and again.stored == 2 and again.failed == {}
    assert (
        routes[(good, "v1/game/{pk}/boxscore")].call_count
        == before[(good, "v1/game/{pk}/boxscore")]
    )
    assert (
        routes[(no_odds, "v1/game/{pk}/linescore")].call_count
        == before[(no_odds, "v1/game/{pk}/linescore")]
    ), "stored games are not requested again"


@respx.mock
def test_old_part_files_and_segments_are_read_together(tmp_path: Path) -> None:
    module = _api()
    old_game, new_game = 745000, 745001
    _mock_games((old_game, new_game))
    extractor = _extractor(tmp_path)
    for name in GAME_DATASETS:
        extractor.ingest(name, Context(season=SEASON, game_pks=(old_game,)))
    module.ingest_game_segments(extractor, SEASON, (new_game,))

    table = read("mlb_api.game_linescore", SEASON, backend="pyarrow", config=extractor.cache_config)
    by_game = dict(
        zip(
            table.column("game_pk").to_pylist(),
            table.column(LINEAGE_COLUMN).to_pylist(),
            strict=True,
        )
    )
    assert set(by_game) == {old_game, new_game}
    assert by_game[old_game] is None, "rows of the old part files have no lineage"
    assert isinstance(by_game[new_game], str) and len(by_game[new_game]) == 64


def test_a_segment_run_becomes_one_report_per_dataset_and_a_capped_list_of_failures() -> None:
    from baseballpy.sources.mlb_api.game_segments import GameSegmentReport, game_segment_reports

    report = GameSegmentReport(
        stored=3,
        already=2,
        failed={pk: "HTTP 404" for pk in range(100, 150)},
        segments=1,
        rows={"game_linescore": 30},
    )
    reports = game_segment_reports(report, games=55)
    by_name = {r.name: r for r in reports}
    assert sorted(set(by_name) - {"game_segments"}) == GAME_DATASETS
    assert by_name["game_linescore"].rows == 30 and by_name["game_linescore"].cached == 2
    errors = by_name["game_segments"].errors
    assert (
        len(errors) == 21 and errors[-1] == "... and 30 more" and errors[0] == "game 100: HTTP 404"
    )
