"""Tests verifying Retrosheet parsers quarantine uncastable values under real dataset names."""

import json
from pathlib import Path
from typing import Any, cast

import pyarrow as pa

from baseballpy.cli_quarantine import scan_quarantine
from baseballpy.core.config import QuarantineConfig
from baseballpy.sources.retrosheet.parser import (
    RetrosheetGameLogParser,
    RetrosheetRosterParser,
    _arr,
)


def test_arr_helper_quarantines_under_specified_dataset() -> None:
    """_arr directly routes uncastable Arrow conversion failures to the specified dataset."""
    field = pa.field("test_col", pa.int32())
    arr = _arr(["not_a_number"], field, dataset="gamelogs")
    assert arr.to_pylist() == [None]

    files = scan_quarantine()
    assert len(files) == 1
    assert files[0].dataset == "gamelogs"
    assert files[0].source == "retrosheet"


def test_gamelog_uncastable_integer_quarantined_under_gamelogs(tmp_path: Path) -> None:
    """When a game log column value fails PyArrow integer casting, quarantine records 'gamelogs'."""
    gl_path = tmp_path / "gl2024.txt"
    # game_num (field index 1) is pa.int8() [-128..127]; "99999" passes to_int but overflows int8
    # and safe_array in _arr catches the ArrowInvalid failure. On old code, _arr wrote "parse".
    line = "20240401,99999,Mon,BAL,AL,1,BOS,AL,1,5,3,54,D,0,0,0,BOS07,37000,180\n"
    gl_path.write_text(line, encoding="utf-8")

    parser = RetrosheetGameLogParser()
    table = parser.parse_file(gl_path)

    assert isinstance(table, pa.Table)
    assert len(table) == 1
    assert table["game_num"].to_pylist() == [None]

    files = scan_quarantine()
    assert len(files) == 1
    assert files[0].dataset == "gamelogs"
    assert files[0].source == "retrosheet"

    # Verify dead-letter JSONL content and filename prefix
    qdir = QuarantineConfig().quarantine_dir
    jsonl_files = list(qdir.rglob("*.jsonl"))
    assert len(jsonl_files) == 1
    assert jsonl_files[0].name.startswith("gamelogs-")

    record = json.loads(jsonl_files[0].read_text(encoding="utf-8").strip())
    assert record["dataset"] == "gamelogs"
    assert record["source"] == "retrosheet"
    assert record["payload"]["column"] == "game_num"
    assert record["payload"]["value"] == 99999


def test_gamelog_coercion_error_quarantined_under_gamelogs(tmp_path: Path) -> None:
    """When a game log integer field holds non-numeric text like 'abc', quarantine records 'gamelogs'."""
    gl_path = tmp_path / "gl2024.txt"
    # visiting_score (field index 9) is pa.int16(); "abc" fails to_int coercion in _safe_int
    line = "20240401,0,Mon,BAL,AL,1,BOS,AL,1,abc,3,54,D,0,0,0,BOS07,37000,180\n"
    gl_path.write_text(line, encoding="utf-8")

    parser = RetrosheetGameLogParser()
    table = parser.parse_file(gl_path)

    assert isinstance(table, pa.Table)
    assert len(table) == 1
    assert table["visiting_score"].to_pylist() == [None]

    files = scan_quarantine()
    assert len(files) == 1
    assert files[0].dataset == "gamelogs"
    assert files[0].source == "retrosheet"


def test_roster_uncastable_year_quarantined_under_rosters(tmp_path: Path) -> None:
    """When a roster has an uncastable year, _arr captures it under dataset 'rosters'."""
    ros_path = tmp_path / "BOS2024.ROS"
    ros_path.write_text("deve001,Devers,Rafael,L,R,BOS,3B\n", encoding="utf-8")

    parser = RetrosheetRosterParser()
    # year in RETROSHEET_ROSTER_SCHEMA is pa.int16(); passing non-numeric text triggers safe_array
    table = parser.parse_files([ros_path], year=cast(Any, "not_a_year"))
    assert isinstance(table, pa.Table)
    assert len(table) == 1
    assert table["year"].to_pylist() == [None]

    files = scan_quarantine()
    assert len(files) == 1
    assert files[0].dataset == "rosters"
    assert files[0].source == "retrosheet"


def test_boxscore_and_split_datasets_quarantined_under_real_names() -> None:
    """Verify each Retrosheet parser routes column errors under its real dataset name."""
    batting_col = pa.field("ab", pa.int16())
    pitching_col = pa.field("outs_recorded", pa.int16())
    daily_col = pa.field("B_AB", pa.int16())
    sub_col = pa.field("SUB_FLD_CD", pa.int16())

    assert _arr(["bad"], batting_col, dataset="boxscores_batting").to_pylist() == [None]
    assert _arr(["bad"], pitching_col, dataset="boxscores_pitching").to_pylist() == [None]
    assert _arr(["bad"], daily_col, dataset="daily_splits").to_pylist() == [None]
    assert _arr(["bad"], sub_col, dataset="substitutions").to_pylist() == [None]

    files = scan_quarantine()
    datasets = {f.dataset for f in files}
    assert datasets == {"boxscores_batting", "boxscores_pitching", "daily_splits", "substitutions"}
    assert "parse" not in datasets
