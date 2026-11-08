"""Tests for the crosswalk suite (views and top-level accessors).

They read the owner's real lake (100,000+ players, real venues and games), which the isolated test
home does not have, so they run with the live tests (`-m live`), not in the default gates.
"""

import polars as pl
import pyarrow as pa
import pytest

import baseballpy as bb

pytestmark = pytest.mark.live


def test_player_crosswalk_accessor() -> None:
    df = bb.players()
    assert isinstance(df, pl.DataFrame)
    assert len(df) > 100_000
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
    tbl = bb.players(backend="arrow")
    assert isinstance(tbl, pa.Table)
    assert len(tbl) == len(df)


def test_crosswalk_id_resolver() -> None:
    # Shohei Ohtani
    assert bb.crosswalk(660271, "mlbam", "bbref") == "ohtansh01"
    assert bb.crosswalk(660271, "mlbam", "retro") == "ohtas001"


def test_team_crosswalk_accessor() -> None:
    df = bb.team_crosswalk()
    assert isinstance(df, pl.DataFrame)
    assert len(df) >= 30
    for col in ("team_id_mlb", "team_abbr_mlb", "team_code_retro", "team_name"):
        assert col in df.columns

    # Check known franchise
    yankees = df.filter(pl.col("team_id_mlb") == 147)
    assert len(yankees) >= 1
    assert yankees["team_abbr_mlb"][0] == "NYY"
    assert yankees["team_code_retro"][0] == "NYA"


def test_venue_crosswalk_accessor() -> None:
    df = bb.venues()
    assert isinstance(df, pl.DataFrame)
    assert len(df) > 100
    for col in ("venue_id", "venue_name", "city", "state", "roof_type", "turf_type"):
        assert col in df.columns

    # Check Fenway Park (venue 3)
    fenway = df.filter(pl.col("venue_id") == 3)
    assert len(fenway) == 1
    assert "Fenway" in str(fenway["venue_name"][0])


def test_game_crosswalk_accessor() -> None:
    df = bb.games(season=2024)
    assert isinstance(df, pl.DataFrame)
    assert len(df) > 2_000
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
    ):
        assert col in df.columns

    # Check joined retro_game_id exists for regular season games
    reg = df.filter((pl.col("game_type") == "R") & pl.col("retro_game_id").is_not_null())
    assert len(reg) > 2_000
