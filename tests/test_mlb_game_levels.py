"""The per-game MLB download covers the major leagues unless told otherwise."""

from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.ingest.types import Selection, make_job
from baseballpy.sources.mlb_api import api as api_mod
from baseballpy.sources.mlb_api.adapter import MlbApiAdapter, parse_game_sports


class _Calendar:
    def not_started_reason(self, season: int) -> None:
        return None

    def latest_started_season(self) -> int:
        return 2026


class _Source:
    def __init__(self) -> None:
        self.calls: list[tuple[int, dict[str, Any]]] = []

    def ingest_season(self, season: int, **kwargs: Any) -> list[Any]:
        self.calls.append((season, kwargs))
        return []


def _games_job(adapter: MlbApiAdapter, *options: tuple[str, str]) -> Any:
    selection = Selection(seasons=(2024,), datasets=("games",), options=options)
    return [j for j in adapter.plan(selection) if j.param("games")][0]


def test_parse_game_sports() -> None:
    assert parse_game_sports("1") == (1,)
    assert parse_game_sports(" 1, 11 ,12,1") == (1, 11, 12)
    assert parse_game_sports("ALL") is None
    for bad in ("", "major", "1,x"):
        with pytest.raises(ValueError, match="bad --option sports"):
            parse_game_sports(bad)


def test_the_plan_defaults_to_the_major_leagues_and_takes_the_option() -> None:
    adapter = MlbApiAdapter(_Source(), calendar=_Calendar())
    assert _games_job(adapter).param("sports") == "1"
    assert _games_job(adapter, ("sports", "all")).param("sports") == "all"
    assert _games_job(adapter, ("sports", "1, 11")).param("sports") == "1,11"
    with pytest.raises(ValueError, match="bad --option sports"):
        _games_job(adapter, ("sports", "minors"))


def test_the_job_hands_the_levels_to_the_source() -> None:
    source = _Source()
    adapter = MlbApiAdapter(source, calendar=_Calendar())
    adapter.run(make_job("mlb_api", "season", games=True, season=2024))
    adapter.run(make_job("mlb_api", "season", games=True, season=2024, sports="all"))
    adapter.run(make_job("mlb_api", "season", games=True, season=2024, sports="1,11"))
    assert [kw["game_sport_ids"] for _, kw in source.calls] == [(1,), None, (1, 11)]


def test_final_game_pks_keeps_only_the_wanted_levels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule = pa.table(
        {
            "game_pk": [1, 1, 2, 3, 4, 5],
            "sport_id": [1, 1, 1, 11, 12, 1],
            "status_abstract_game_state": ["Final", "Final", "Final", "Final", "Final", "Live"],
        }
    )
    monkeypatch.setattr(api_mod, "read_endpoint", lambda *a, **k: schedule)
    source = api_mod.MlbApiSource(LakeConfig(home=tmp_path))
    assert source.final_game_pks(2024, (1,)) == (1, 2)
    assert source.final_game_pks(2024, (1, 11)) == (1, 2, 3)
    assert source.final_game_pks(2024) == (1, 2, 3, 4)


def test_a_games_run_fetches_only_the_games_not_the_season_datasets_again() -> None:
    """The season datasets have their own job; repeating them in the games job re-sent hundreds of
    requests per season and failed the job on the ones the provider refuses (ADR 91)."""
    source = _Source()
    adapter = MlbApiAdapter(source, calendar=_Calendar())
    job = _games_job(adapter)
    assert job.param("games_only") is True
    adapter.run(job)
    adapter.run(make_job("mlb_api", "season", games=True, season=2024))  # an older job id
    assert source.calls[0][1]["include_season"] is False
    assert source.calls[1][1]["include_season"] is True
