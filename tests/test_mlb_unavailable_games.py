"""Games the provider cannot serve (B-404): listed with evidence, never requested, never a failure, still reported."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import release_all
from baseballpy.sources.mlb_api import game_segments
from baseballpy.sources.mlb_api.endpoints import MLB_BASE_URL
from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
ANSWERS = {
    "v1.1/game/{pk}/feed/live": "game_feed_plays",
    "v1/game/{pk}/boxscore": "game_boxscore_pitching_notes",
    "v1/game/{pk}/linescore": "game_linescore",
    "v1/game/{pk}/winProbability": "game_win_probability",
    "v1/game/{pk}/playByPlay": "game_play_by_play",
}
SEASON = 2024


@pytest.fixture(autouse=True)
def _free_locks() -> Any:
    yield
    release_all()


def _extractor(tmp_path: Path) -> MlbEndpointExtractor:
    return MlbEndpointExtractor(cache_config=LakeConfig(home=tmp_path, today=date(2026, 6, 1)))


def _mock(pk: int, status: int = 200) -> list[respx.Route]:
    routes = []
    for template, fixture in ANSWERS.items():
        body = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
        response = httpx.Response(status, json=body if status == 200 else {"message": "boom"})
        routes.append(
            respx.get(f"{MLB_BASE_URL}/{template.format(pk=pk)}").mock(return_value=response)
        )
    return routes


def test_the_shipped_list_is_valid_and_every_entry_carries_its_evidence() -> None:
    entries = game_segments.known_unavailable_games()
    assert entries, "the two 2011 games found by B-404 are listed"
    for pk, entry in entries.items():
        assert isinstance(pk, int)
        assert entry["status"] in (404, 500) and entry["season"] >= 1876
        assert entry["probed"] and entry["evidence"] and entry["urls"]
        date.fromisoformat(entry["probed"])


@respx.mock
def test_a_listed_game_is_not_requested_and_is_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        game_segments, "known_unavailable_games", lambda: {9: {"status": 500, "season": SEASON}}
    )
    listed, other = _mock(9, 500), _mock(10)
    report = game_segments.ingest_game_segments(_extractor(tmp_path), SEASON, (9, 10))
    assert all(route.call_count == 0 for route in listed), "the provider is not asked again"
    assert all(route.call_count == 1 for route in other)
    assert report.stored == 1 and report.unavailable == [9] and report.failed == {}


@respx.mock
def test_a_game_that_is_not_listed_still_fails_and_is_retried_next_time(tmp_path: Path) -> None:
    _mock(11, 500)
    report = game_segments.ingest_game_segments(_extractor(tmp_path), SEASON, (11,))
    assert report.stored == 0 and report.unavailable == [] and 11 in report.failed


def test_the_job_report_counts_listed_games_as_missing_not_as_errors() -> None:
    report = game_segments.GameSegmentReport(unavailable=[9, 12], already=1)
    reports = game_segments.game_segment_reports(report, games=5)
    last = reports[-1]
    assert last.name == "game_segments" and last.missing == 2 and last.errors == ()


def test_the_probe_script_names_the_games_that_answer_again() -> None:
    import importlib.util

    path = Path(__file__).parent.parent / "scripts" / "probe_unavailable_games.py"
    spec = importlib.util.spec_from_file_location("probe_unavailable_games", path)
    assert spec and spec.loader
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    assert probe.verdict(500, 500) == "still unavailable"
    assert probe.verdict(500, 200) == "ANSWERS AGAIN: remove it from unavailable_games.json"
