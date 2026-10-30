"""Tests for Retrosheet game log and roster row validation, quarantine, and extra field preservation."""

import json
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.quarantine import get_quarantine
from baseballpy.sources.retrosheet.parser import (
    RetrosheetGameLogParser,
    RetrosheetRosterParser,
)


def test_short_gamelog_rows_are_quarantined_and_extra_fields_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify short game log rows (<10 fields) are quarantined and extra fields (>161) preserved in _extras."""
    lake = LakeConfig(home=tmp_path / "lake")
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    get_quarantine.reset()

    # 161-field standard game log row
    base_row = (
        '20240328,0,Thu,LAN,NL,1,SDN,NL,1,5,2,54,D,,,,SEO01,15952,185,"000101003","000000020",'
        "37,11,1,0,0,5,0,0,0,1,0,3,1,0,0,0,8,6,2,2,0,0,27,11,1,0,0,0,31,4,0,0,0,2,0,0,1,0,0,7,2,0,0,0,9,5,5,5,1,0,27,9,2,0,0,0,"
        "hp_id,hp_name,1b_id,1b_name,2b_id,2b_name,3b_id,3b_name,lf_id,lf_name,rf_id,rf_name,"
        "v_mgr_id,v_mgr_name,h_mgr_id,h_mgr_name,w_pit_id,w_pit_name,l_pit_id,l_pit_name,s_pit_id,s_pit_name,"
        "gwrbi_id,gwrbi_name,v_sp_id,v_sp_name,h_sp_id,h_sp_name,"
        "v_b1_id,v_b1_name,8,v_b2_id,v_b2_name,6,v_b3_id,v_b3_name,7,v_b4_id,v_b4_name,3,v_b5_id,v_b5_name,9,"
        "v_b6_id,v_b6_name,4,v_b7_id,v_b7_name,5,v_b8_id,v_b8_name,2,v_b9_id,v_b9_name,1,"
        "h_b1_id,h_b1_name,8,h_b2_id,h_b2_name,6,h_b3_id,h_b3_name,7,h_b4_id,h_b4_name,3,h_b5_id,h_b5_name,9,"
        "h_b6_id,h_b6_name,4,h_b7_id,h_b7_name,5,h_b8_id,h_b8_name,2,h_b9_id,h_b9_name,1,"
        "additional_info,acquisition_info"
    )

    # 3-field short row
    short_row = "20240328,0,Thu"

    # 171-field row (161 standard + 10 extras: field_162 through field_171)
    extra_items = [f"extra_val_{i}" for i in range(162, 172)]
    row_171 = base_row + "," + ",".join(extra_items)

    gl_path = tmp_path / "gl2024.txt"
    gl_path.write_text(f"{base_row}\n{short_row}\n{row_171}\n", encoding="utf-8")

    try:
        parser = RetrosheetGameLogParser()
        table = parser.parse_file(gl_path)

        assert isinstance(table, pa.Table)
        assert len(table) == 2

        # Row 0: valid 161-field row -> _extras is None
        assert table["_extras"][0].as_py() is None

        # Row 1: 171-field row -> _extras has field_162 .. field_171
        extras_raw = table["_extras"][1].as_py()
        assert extras_raw is not None
        extras_dict = json.loads(extras_raw)
        expected_extras = {f"field_{i}": f"extra_val_{i}" for i in range(162, 172)}
        assert extras_dict == expected_extras

        # Quarantine got exactly one record for the short row
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
        assert record["dataset"] == "gamelogs"
        assert record["payload"]["type"] == "row"
        assert record["payload"]["value"] == short_row
        assert "game log row has 3 fields, expected at least 10" in record["payload"]["error"]
    finally:
        get_quarantine.reset()


def test_roster_rows_short_quarantined_and_extra_fields_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify short roster rows (<6 fields) are quarantined and extra fields (>7) preserved in _extras."""
    lake = LakeConfig(home=tmp_path / "lake")
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    get_quarantine.reset()

    # 5 fields (short, should be quarantined)
    row_5 = "short01,Short,Player,R,R"
    # 6 fields (position should be empty string "")
    row_6 = "six01,Six,Player,L,L,BOS"
    # 7 fields (position given)
    row_7 = "seven01,Seven,Player,R,R,BOS,OF"
    # 8 fields (position given + 1 extra field -> field_8)
    row_8 = "eight01,Eight,Player,S,R,BOS,1B,some_note"

    ros_path = tmp_path / "BOS2024.ROS"
    ros_path.write_text(f"{row_5}\n{row_6}\n{row_7}\n{row_8}\n", encoding="utf-8")

    try:
        parser = RetrosheetRosterParser()
        table = parser.parse_files([ros_path], year=2024)

        assert isinstance(table, pa.Table)
        assert len(table) == 3

        # 6-field row: position is "", _extras is None
        assert table["player_id"][0].as_py() == "six01"
        assert table["team"][0].as_py() == "BOS"
        assert table["position"][0].as_py() == ""
        assert table["year"][0].as_py() == 2024
        assert table["_extras"][0].as_py() is None

        # 7-field row: position is "OF", _extras is None
        assert table["player_id"][1].as_py() == "seven01"
        assert table["position"][1].as_py() == "OF"
        assert table["_extras"][1].as_py() is None

        # 8-field row: position is "1B", _extras is {"field_8": "some_note"}
        assert table["player_id"][2].as_py() == "eight01"
        assert table["position"][2].as_py() == "1B"
        extras_raw = table["_extras"][2].as_py()
        assert extras_raw is not None
        assert json.loads(extras_raw) == {"field_8": "some_note"}

        # Quarantine inspection: 5-field row is quarantined
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
        assert record["dataset"] == "rosters"
        assert record["payload"]["type"] == "row"
        assert record["payload"]["value"] == row_5
        assert "roster row has 5 fields, expected at least 6" in record["payload"]["error"]
    finally:
        get_quarantine.reset()


def test_all_star_roster_lines_are_told_apart_by_the_roster_they_came_from(tmp_path: Path) -> None:
    from baseballpy.core.datasets import get_dataset
    from baseballpy.sources import catalog
    from baseballpy.sources.retrosheet.parser import RetrosheetRosterParser

    line = b"altuj001,Altuve,Jose,R,R,HOU,2B\n"
    (tmp_path / "HOU2015.ROS").write_bytes(line)
    (tmp_path / "ALS2015.ROS").write_bytes(line)  # the all-star roster repeats the club line
    table = RetrosheetRosterParser().parse_files(
        [tmp_path / "ALS2015.ROS", tmp_path / "HOU2015.ROS"], year=2015
    )
    catalog.register_all()
    keys = get_dataset("retrosheet", "rosters").keys
    assert keys == ("year", "roster", "player_id")
    rows = list(zip(*[table[k].to_pylist() for k in keys], strict=True))
    assert sorted(rows) == [(2015, "ALS", "altuj001"), (2015, "HOU", "altuj001")]
