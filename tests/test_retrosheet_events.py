"""Event datasets keep every field chadwickpy emits and have a unique key (retrosheet-source-review 5.6)."""

import json
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.datasets import get_dataset
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet import _chadwick_adapter as cw
from baseballpy.sources.retrosheet.parser import RetrosheetEventParser
from baseballpy.sources.retrosheet.schema import RETROSHEET_EVENT_SCHEMA

#: a game with several plays, a stolen base, a double play and a substitution
GAME = (
    b"id,BOS202404010\n"
    b"info,date,2024/04/01\n"
    b"info,hometeam,BOS\n"
    b"info,visteam,BAL\n"
    b"start,vis01,Visitor One,0,1,8\n"
    b"start,vis02,Visitor Two,0,2,9\n"
    b"start,hom01,Home One,1,1,8\n"
    b"start,visp1,Visitor Pitcher,0,0,1\n"
    b"start,homp1,Home Pitcher,1,0,1\n"
    b"play,1,0,vis01,00,,S8\n"
    b"play,1,0,vis02,00,,K\n"
    b"play,1,0,vis01,00,,SB2\n"
    b"play,1,0,vis02,00,,64(1)3/GDP\n"
    b"play,1,1,hom01,00,,W\n"
    b"play,1,1,hom01,00,,NP\n"
)


def _parse(tmp_path: Path, data: bytes = GAME) -> pa.Table:
    path = tmp_path / "2024BOS.EVA"
    path.write_bytes(data)
    return RetrosheetEventParser().parse_files([path], year=2024)


def test_event_fields_match_chadwickpy_and_keys_are_unique(tmp_path: Path) -> None:
    table = _parse(tmp_path)
    assert table.num_rows > 3
    assert list(cw.EVENT_COLUMNS) == RETROSHEET_EVENT_SCHEMA.names[:-1]  # then _extras
    assert table.schema.names[-1] == "_extras"
    assert table["EVENT_ID"].null_count == 0
    for dataset in ("events", "events_postseason", "events_deduced"):
        catalog.register_all()
        spec = get_dataset("retrosheet", dataset)
        assert spec.keys == ("GAME_ID", "EVENT_ID")
        keys = list(zip(table["GAME_ID"].to_pylist(), table["EVENT_ID"].to_pylist(), strict=True))
        assert len(set(keys)) == len(keys)
        assert all(spec.schema.field(c).nullable or table[c].null_count == 0 for c in spec.keys)


def test_fields_that_were_dropped_before_are_now_stored(tmp_path: Path) -> None:
    table = _parse(tmp_path)
    for name in ("EVENT_ID", "BAT_TEAM_ID", "START_BASES_CD", "END_BASES_CD", "RUN1_FATE_ID"):
        assert name in table.schema.names
    assert table["EVENT_ID"].to_pylist() == list(range(1, table.num_rows + 1))
    assert pa.types.is_boolean(table.schema.field("PA_NEW_FL").type)
    assert pa.types.is_integer(table.schema.field("START_BASES_CD").type)
    assert table["BAT_TEAM_ID"].to_pylist()[0] == "BAL"


def test_a_field_the_schema_does_not_know_goes_to_extras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = cw.event_rows

    def with_new_field(data: bytes, league: object = None) -> object:
        for row in real(data, league=league):  # type: ignore[arg-type]
            yield {**row, "FUTURE_FIELD": "x"}

    monkeypatch.setattr(cw, "event_rows", with_new_field)
    table = _parse(tmp_path)
    assert json.loads(table["_extras"].to_pylist()[0]) == {"FUTURE_FIELD": "x"}


def test_substitution_and_daily_split_keys_survive_double_switches(tmp_path: Path) -> None:
    from baseballpy.sources.retrosheet.parser import (
        RetrosheetDailySplitsParser,
        RetrosheetSubstitutionsParser,
    )

    game = (
        GAME.split(b"play,")[0]
        + b"play,1,0,vis01,00,,S8\n"
        + b"sub,visp2,Reliever,0,0,1\n"
        + b"sub,vis03,Pinch,0,2,11\n"
        + b"sub,vis03,Pinch,0,2,6\n"
        + b"play,1,0,vis03,00,,K\n"
    )
    path = tmp_path / "2024BOS.EVA"
    path.write_bytes(game)
    catalog.register_all()
    subs = RetrosheetSubstitutionsParser().parse_files([path], year=2024)
    daily = RetrosheetDailySplitsParser().parse_files([path], year=2024)
    for name, table in (("substitutions", subs), ("daily_splits", daily)):
        keys = get_dataset("retrosheet", name).keys
        rows = list(zip(*[table[k].to_pylist() for k in keys], strict=True))
        assert rows and len(set(rows)) == len(rows), name
    # two substitutions in front of the same play share (GAME_ID, EVENT_ID); SUB_ID tells them apart
    event_keys = set(zip(subs["GAME_ID"].to_pylist(), subs["EVENT_ID"].to_pylist(), strict=True))
    # a player who changes position in the same stoppage keeps his SUB_ID; SUB_FLD_CD tells the rows apart
    assert len(subs) == 3 and len(event_keys) == 1


def test_boxscores_batting_key_is_unique_and_orders_a_slots_occupants(tmp_path: Path) -> None:
    from baseballpy.sources.retrosheet.parser import RetrosheetBoxScoreParser

    game = (
        GAME.split(b"play,")[0]
        + b"play,1,0,vis01,00,,S8\n"
        + b"sub,vis03,Pinch,0,2,11\n"
        + b"play,1,0,vis03,00,,K\n"
    )
    path = tmp_path / "2024BOS.EVA"
    path.write_bytes(game)
    catalog.register_all()
    batting, _ = RetrosheetBoxScoreParser().parse_files([path], year=2024)
    keys = get_dataset("retrosheet", "boxscores_batting").keys
    assert keys == ("game_id", "team_id", "slot", "seq")
    rows = list(zip(*[batting[k].to_pylist() for k in keys], strict=True))
    assert len(set(rows)) == len(rows)
    by_player = dict(zip(batting["player_id"].to_pylist(), batting["seq"].to_pylist(), strict=True))
    assert (
        by_player["vis02"] == 1 and by_player["vis03"] == 2
    )  # the pinch hitter follows the starter
