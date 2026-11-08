"""Tests for the crosswalk suite (views and top-level accessors).

Tests run in an isolated environment with synthetic fixtures, verifying all crosswalk views,
accessors, backend conversions (Polars and PyArrow), and ID crosswalking. Live integration
tests run under `-m live` against the real lake.
"""

from pathlib import Path

import polars as pl
import pyarrow as pa
import pytest

import baseballpy as bb
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog
from baseballpy.sources.chadwick.register import ChadwickRegister


@pytest.fixture
def crosswalk_lake(tmp_path: Path) -> LakeConfig:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)

    # 1. Chadwick register
    store.put(
        get_dataset("chadwick", "register"),
        pa.table(
            {
                "key_person": ["ohtans01", "judga001"],
                "key_uuid": ["uuid-ohtani", "uuid-judge"],
                "key_mlbam": [660271, 592450],
                "key_retro": ["ohtas001", "judga001"],
                "key_bbref": ["ohtansh01", "judgeaa01"],
                "key_fangraphs": [19755, 15640],
                "name_first": ["Shohei", "Aaron"],
                "name_last": ["Ohtani", "Judge"],
            }
        ),
    )

    # 2. MLB schedule hydrated
    store.put(
        get_dataset("mlb_api", "schedule_hydrated"),
        pa.table(
            {
                "game_pk": [745330, 745331],
                "official_date": ["2024-03-28", "2024-03-28"],
                "season": [2024, 2024],
                "game_number": [1, 1],
                "game_type": ["R", "R"],
                "teams_home_team_id": [147, 111],
                "teams_home_team_team_code": ["nya", "bos"],
                "teams_home_team_name": ["New York Yankees", "Boston Red Sox"],
                "teams_away_team_id": [119, 137],
                "teams_away_team_team_code": ["lan", "sfn"],
                "teams_away_team_name": ["Los Angeles Dodgers", "San Francisco Giants"],
                "venue_id": [3313, 3],
                "venue_name": ["Yankee Stadium", "Fenway Park"],
            }
        ),
        chunk_id="part-1",
        season=2024,
    )

    # 3. Retrosheet box games
    store.put(
        get_dataset("retrosheet", "box_games"),
        pa.table(
            {
                "game_id": ["NYA202403280", "BOS202403280"],
                "date": ["2024-03-28", "2024-03-28"],
                "hometeam": ["NYA", "BOS"],
            }
        ),
        chunk_id="box",
        season=2024,
    )

    # 4. MLB teams season
    store.put(
        get_dataset("mlb_api", "teams_season"),
        pa.table(
            {
                "id": [147, 111],
                "season": [2024, 2024],
                "name": ["New York Yankees", "Boston Red Sox"],
                "abbreviation": ["NYY", "BOS"],
                "team_code": ["nya", "bos"],
                "league_id": [103, 103],
                "division_id": [201, 201],
                "active": [True, True],
            }
        ),
        chunk_id="part-1",
        season=2024,
    )

    # 5. MLB venues hydrated
    store.put(
        get_dataset("mlb_api", "venues_hydrated"),
        pa.table(
            {
                "id": [3313, 3],
                "name": ["Yankee Stadium", "Fenway Park"],
                "location_city": ["Bronx", "Boston"],
                "location_state": ["NY", "MA"],
                "location_country": ["USA", "USA"],
                "location_default_coordinates_latitude": [40.8296, 42.3467],
                "location_default_coordinates_longitude": [-73.9262, -71.0972],
                "location_elevation": [54, 20],
                "field_info_capacity": [46537, 37755],
                "field_info_roof_type": ["Open", "Open"],
                "field_info_turf_type": ["Grass", "Grass"],
                "field_info_left_line": [318, 310],
                "field_info_center": [408, 390],
                "field_info_right_line": [314, 302],
                "active": [True, True],
            }
        ),
    )

    BaseballDatabase(cache_config=cfg).sync_views()
    return cfg


def test_player_crosswalk_accessor(crosswalk_lake: LakeConfig) -> None:
    df = bb.players(config=crosswalk_lake)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 2
    for col in (
        "key_mlbam",
        "key_retro",
        "key_bbref",
        "key_fangraphs",
        "key_person",
        "name_first",
        "name_last",
    ):
        assert col in df.columns

    # Test pyarrow backend
    tbl = bb.players(backend="arrow", config=crosswalk_lake)
    assert isinstance(tbl, pa.Table)
    assert len(tbl) == len(df)


def test_crosswalk_id_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test with synthetic register to verify crosswalk resolution
    dummy_table = pa.table(
        {
            "key_person": ["ohtans01"],
            "key_uuid": ["uuid-1"],
            "key_mlbam": [660271],
            "key_retro": ["ohtas001"],
            "key_bbref": ["ohtansh01"],
            "key_fangraphs": [19755],
            "name_first": ["Shohei"],
            "name_last": ["Ohtani"],
        }
    )
    reg = ChadwickRegister(dummy_table)
    monkeypatch.setattr("baseballpy.sources.chadwick.get_register", lambda **kwargs: reg)
    assert bb.crosswalk(660271, "mlbam", "bbref") == "ohtansh01"
    assert bb.crosswalk(660271, "mlbam", "retro") == "ohtas001"


def test_team_crosswalk_accessor(crosswalk_lake: LakeConfig) -> None:
    df = bb.team_crosswalk(config=crosswalk_lake)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 2
    for col in ("team_id_mlb", "team_abbr_mlb", "team_code_retro", "team_name"):
        assert col in df.columns

    yankees = df.filter(pl.col("team_id_mlb") == 147)
    assert len(yankees) == 1
    assert yankees["team_abbr_mlb"][0] == "NYY"
    assert yankees["team_code_retro"][0] == "NYA"


def test_venue_crosswalk_accessor(crosswalk_lake: LakeConfig) -> None:
    df = bb.venues(config=crosswalk_lake)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 2
    for col in ("venue_id", "venue_name", "city", "state", "roof_type", "turf_type"):
        assert col in df.columns

    fenway = df.filter(pl.col("venue_id") == 3)
    assert len(fenway) == 1
    assert "Fenway" in str(fenway["venue_name"][0])


def test_game_crosswalk_accessor(crosswalk_lake: LakeConfig) -> None:
    df = bb.games(season=2024, config=crosswalk_lake)
    assert isinstance(df, pl.DataFrame)
    assert len(df) == 2
    for col in (
        "game_pk",
        "game_date",
        "season",
        "game_number",
        "game_type",
        "home_team_id_mlb",
        "home_team_retro",
        "home_team_name",
        "away_team_id_mlb",
        "away_team_retro",
        "away_team_name",
        "venue_id",
        "venue_name",
        "retro_game_id",
    ):
        assert col in df.columns

    # Verify joined retro_game_id matches
    yankees_game = df.filter(pl.col("game_pk") == 745330)
    assert len(yankees_game) == 1
    assert yankees_game["retro_game_id"][0] == "NYA202403280"


@pytest.mark.live
def test_crosswalk_live_lake() -> None:
    assert bb.crosswalk(660271, "mlbam", "bbref") == "ohtansh01"
    assert len(bb.players()) > 100_000
    assert len(bb.team_crosswalk()) >= 30
    assert len(bb.venues()) > 100
    assert len(bb.games(season=2024)) > 2_000
