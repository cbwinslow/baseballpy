"""Retrosheet box-score game accounts: typed kinds, lossless remainder, strict layouts."""

from datetime import date
from pathlib import Path

import pyarrow as pa
import pytest
import respx
from conftest import RetroRepo

from baseballpy.core.config import LakeConfig
from baseballpy.sources.retrosheet.api import BOX_DATASETS, RetrosheetSource
from baseballpy.sources.retrosheet.box_parser import (
    BoxParseError,
    decode_box,
    parse_box_text,
)

SAMPLE = Path(__file__).parent / "fixtures" / "retrosheet" / "box_sample.EBA"


def _sample() -> str:
    return decode_box(SAMPLE.read_bytes())


def test_every_line_of_real_games_is_accounted_for() -> None:
    text = _sample()
    tables = parse_box_text(text, "box_sample.EBA")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    info = sum(1 for ln in lines if ln.startswith("info,"))
    games = tables.games.num_rows
    assert games == 3
    typed = games + games + info + tables.starters.num_rows + tables.batting.num_rows
    assert typed + tables.records.num_rows == len(lines), "id+version+info+start+bline+records"
    assert set(tables.games.column("source_file").to_pylist()) == {"box_sample.EBA"}


def test_games_are_typed_and_sentinels_become_null() -> None:
    games = parse_box_text(_sample()).games
    row = {n: games.column(n)[0].as_py() for n in games.column_names}
    assert isinstance(row["date"], date) and row["version"] == 3
    assert isinstance(row["usedh"], bool) and isinstance(row["attendance"], int)
    assert games.schema.field("date").type == pa.date32()
    assert games.schema.field("usedh").type == pa.bool_()
    text = "id,AAA195001010\nversion,3\ninfo,temp,unknown\ninfo,attendance,12000\ninfo,newkey,zz\n"
    one = parse_box_text(text).games
    assert one.column("temp").null_count == 1 and one.column("attendance")[0].as_py() == 12000
    assert one.column("_extras")[0].as_py() == '{"newkey": "zz"}'


def test_starters_and_batting_lines_are_typed_counts() -> None:
    tables = parse_box_text(_sample())
    assert (
        tables.starters.num_rows >= 18 * 3
    )  # 9 batters a side (more with a DH or substitutes listed)
    assert tables.starters.schema.field("batting_order").type == pa.int8()
    assert set(tables.starters.column("side").to_pylist()) == {0, 1}
    batting = tables.batting
    assert batting.schema.field("ab").type == pa.int16() and "interference" in batting.column_names
    assert batting.column("player_id").null_count == 0
    assert sum(batting.column("ab").to_pylist()) > 0


def test_other_records_are_kept_losslessly_with_their_raw_line() -> None:
    records = parse_box_text(_sample()).records
    kinds = set(records.column("kind").to_pylist())
    assert {"stat,pline", "stat,dline", "stat,tline", "line", "com"} <= kinds
    assert any(k.startswith("event,") for k in kinds)
    raw = records.column("raw").to_pylist()
    assert all(line in _sample() for line in raw)
    pline = next(i for i, k in enumerate(records.column("kind").to_pylist()) if k == "stat,pline")
    assert (
        records.column("fields")[pline].as_py()[0] and records.column("line_no")[pline].as_py() > 0
    )


def test_unknown_record_kind_is_preserved_not_dropped() -> None:
    text = "id,AAA195001010\nversion,3\nbrandnew,1,2,3\n"
    records = parse_box_text(text).records
    assert records.column("kind").to_pylist() == ["brandnew"]
    assert records.column("fields")[0].as_py() == ["1", "2", "3"]


@pytest.mark.parametrize(
    "text, message",
    [
        ("stat,bline,x\n", "before any id record"),
        ("id,A\nstat,bline,x,0,1,1,4\n", "bline record has"),
        ('id,A\nstart,x,"N",0,1\n', "start record has"),
        ("id,A\ninfo,site\n", "info record has"),
        ("id\n", "id record has"),
        ("id,A\ninfo,usedh,maybe\n", "boolean info value"),
    ],
)
def test_unexpected_layouts_raise_instead_of_guessing(text: str, message: str) -> None:
    with pytest.raises(BoxParseError, match=message):
        parse_box_text(text)


def test_latin1_fallback_and_blank_lines() -> None:
    raw = 'id,AAA195001010\n\nversion,3\nstart,x1,"Mu\xf1oz",0,1,2\n'.encode("latin-1")
    tables = parse_box_text(decode_box(raw))
    assert tables.starters.column("player_name")[0].as_py() == "Muñoz"


@respx.mock
def test_source_ingests_box_files_into_four_datasets_and_resumes(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add("seasons/2023/2023.EBA", SAMPLE.read_bytes())
    retro_repo.mount()
    lake = LakeConfig(home=tmp_path, today=date(2026, 6, 1))
    source = RetrosheetSource(lake)
    first = source.box_accounts(2023)
    assert set(first) == set(BOX_DATASETS) and first["box_games"].num_rows == 3
    routes = respx.calls.call_count
    again = source.box_accounts(2023)
    assert again["box_games"].num_rows == 3 and respx.calls.call_count == routes
    raw = lake.raw_dir("retrosheet", "box_files", 2023)
    assert (raw / "2023.EBA").exists()
    for name in BOX_DATASETS:
        assert list(lake.processed_dir("retrosheet", name).rglob("*.parquet")), name


@respx.mock
def test_season_without_box_files_stores_empty_tables(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    retro_repo.add("seasons/2023/2023schedule.csv", "Date,Num\n")
    retro_repo.mount()
    source = RetrosheetSource(LakeConfig(home=tmp_path, today=date(2026, 6, 1)))
    tables = source.box_accounts(2023)
    assert all(t.num_rows == 0 for t in tables.values())
    assert tables["box_batting_lines"].schema.names[0] == "game_id"
