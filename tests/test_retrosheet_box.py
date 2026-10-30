"""Retrosheet box-score game accounts: typed kinds, lossless remainder, strict layouts."""

import json
from datetime import date
from pathlib import Path

import pyarrow as pa
import pytest
import respx
from conftest import RetroRepo

from baseballpy.core.config import LakeConfig
from baseballpy.core.quarantine import get_quarantine
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


def test_repeated_info_keys_are_kept() -> None:
    text = (
        "id,BOS195004010\n"
        "version,3\n"
        "info,visteam,NYA\n"
        "info,hometeam,BOS\n"
        "info,date,1950/04/01\n"
        "info,save,a\n"
        "info,save,b\n"
    )
    tables = parse_box_text(text)
    games = tables.games
    assert games.column("save")[0].as_py() == "a"
    records = tables.records
    assert records.num_rows == 1
    assert records.column("game_id")[0].as_py() == "BOS195004010"
    assert records.column("kind")[0].as_py() == "info"
    assert records.column("fields")[0].as_py() == ["save", "b"]
    assert records.column("raw")[0].as_py() == "info,save,b"


def test_unpadded_dates_parse_and_bad_dates_are_quarantined(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = LakeConfig(home=tmp_path / "lake")
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    get_quarantine.reset()

    text = (
        "id,BOS195004010\n"
        "version,3\n"
        "info,visteam,NYA\n"
        "info,hometeam,BOS\n"
        "info,date,1950/4/1\n"
        "id,BOS195004020\n"
        "version,3\n"
        "info,visteam,NYA\n"
        "info,hometeam,BOS\n"
        "info,date,not-a-date\n"
    )
    try:
        tables = parse_box_text(text)
        games = tables.games
        assert games.num_rows == 2
        assert games.column("date")[0].as_py() == date(1950, 4, 1)
        assert games.column("date")[1].as_py() is None

        q_files = list((lake.quarantine_root / "retrosheet").rglob("*.jsonl"))
        assert len(q_files) == 1
        lines = [
            line.strip()
            for line in q_files[0].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["source"] == "retrosheet"
        assert record["dataset"] == "box_games"
        assert record["payload"]["type"] == "date"
        assert record["payload"]["value"] == "not-a-date"
    finally:
        get_quarantine.reset()


def test_non_integer_numbers_raise_box_parse_error() -> None:
    bad_version = "id,BOS195004010\nversion,x\n"
    with pytest.raises(BoxParseError):
        parse_box_text(bad_version)

    bad_start = 'id,BOS195004010\nversion,3\nstart,sprig001,"George Springer",0,x,9\n'
    with pytest.raises(BoxParseError):
        parse_box_text(bad_start)

    bad_bline = (
        "id,BOS195004010\nversion,3\nstat,bline,sprig001,0,9,1,4,1,1,0,0,0,0,0,0,0,0,0,x,0,0,0,0\n"
    )
    with pytest.raises(BoxParseError):
        parse_box_text(bad_bline)


def test_two_way_player_listed_twice_in_a_lineup_has_unique_starter_keys() -> None:
    from baseballpy.core.datasets import get_dataset
    from baseballpy.sources import catalog

    text = (
        "id,NLS202107130\nversion,3\ninfo,visteam,ALS\ninfo,hometeam,NLS\ninfo,date,2021/07/13\n"
        'start,ohtas001,"Shohei Ohtani",0,1,10\n'
        'start,ohtas001,"Shohei Ohtani",0,0,1\n'
    )
    starters = parse_box_text(text, "2021.EBE").by_name()["box_starters"]
    catalog.register_all()
    keys = get_dataset("retrosheet", "box_starters").keys
    assert keys == ("game_id", "player_id", "side", "position")
    rows = list(zip(*[starters[k].to_pylist() for k in keys], strict=True))
    assert len(rows) == 2 and len(set(rows)) == 2
