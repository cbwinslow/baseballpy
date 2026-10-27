"""Tests for Retrosheet extraction, chadwickpy parsing, and atomic two-tier caching."""

from pathlib import Path

import httpx
import pyarrow as pa
import respx
from conftest import RetroRepo

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.sources.retrosheet.api import RetrosheetSource
from baseballpy.sources.retrosheet.downloader import GITHUB_RETROSHEET_BASE
from baseballpy.sources.retrosheet.parser import (
    RetrosheetBoxScoreParser,
    RetrosheetDailySplitsParser,
    RetrosheetEventParser,
    RetrosheetGameLogParser,
    RetrosheetReferenceParser,
    RetrosheetRosterParser,
    RetrosheetSubstitutionsParser,
)


def _spec(name: str) -> DatasetSpec:
    return get_dataset("retrosheet", name)


def test_parse_events_via_chadwick(tmp_path: Path) -> None:
    fake_eva = (
        b"id,BOS202404010\n"
        b"info,date,2024/04/01\n"
        b"info,hometeam,BOS\n"
        b"info,visteam,BAL\n"
        b"start,play01,Batter One,0,1,4\n"
        b"start,pitch01,Pitcher One,1,1,1\n"
        b"play,1,0,play01,00,,S\n"
        b"data,er,pitch01,0\n"
    )
    eva_path = tmp_path / "2024BOS.EVA"
    eva_path.write_bytes(fake_eva)

    parser = RetrosheetEventParser()
    table = parser.parse_files([eva_path], year=2024)

    assert isinstance(table, pa.Table)
    assert len(table) == 1
    assert table["GAME_ID"].to_pylist() == ["BOS202404010"]
    assert table["INN_CT"].to_pylist() == [1]
    assert table["EVENT_CD"].to_pylist() == [20]  # Single -> 20
    assert pa.types.is_int16(table.schema.field("EVENT_CD").type)


def test_parse_boxscores(tmp_path: Path) -> None:
    fake_eva = (
        b"id,BOS202404010\n"
        b"info,date,2024/04/01\n"
        b"info,hometeam,BOS\n"
        b"info,visteam,BAL\n"
        b"start,play01,Batter One,0,1,4\n"
        b"start,pitch01,Pitcher One,1,1,1\n"
        b"play,1,0,play01,00,,S\n"
        b"data,er,pitch01,0\n"
    )
    eva_path = tmp_path / "2024BOS.EVA"
    eva_path.write_bytes(fake_eva)

    parser = RetrosheetBoxScoreParser()
    batting, pitching = parser.parse_files([eva_path], year=2024)

    assert isinstance(batting, pa.Table)
    assert isinstance(pitching, pa.Table)
    assert len(batting) > 0
    assert len(pitching) > 0

    # Batter One had 1 hit in 1 at-bat
    batter_row = batting.filter(pa.compute.equal(batting["player_id"], "play01"))
    assert len(batter_row) == 1
    assert batter_row["h"].to_pylist() == [1]
    assert batter_row["ab"].to_pylist() == [1]

    # Pitcher One allowed 1 hit
    pitcher_row = pitching.filter(pa.compute.equal(pitching["pitcher_id"], "pitch01"))
    assert len(pitcher_row) == 1
    assert pitcher_row["h"].to_pylist() == [1]
    assert pitcher_row["starter_fl"].to_pylist() == [True]


def test_parse_daily_splits(tmp_path: Path) -> None:
    fake_eva = (
        b"id,BOS202404010\n"
        b"info,date,2024/04/01\n"
        b"info,hometeam,BOS\n"
        b"info,visteam,BAL\n"
        b"start,play01,Batter One,0,1,4\n"
        b"start,pitch01,Pitcher One,1,1,1\n"
        b"play,1,0,play01,00,,S\n"
        b"data,er,pitch01,0\n"
    )
    eva_path = tmp_path / "2024BOS.EVA"
    eva_path.write_bytes(fake_eva)

    parser = RetrosheetDailySplitsParser()
    table = parser.parse_files([eva_path], year=2024)

    assert isinstance(table, pa.Table)
    assert len(table) == 2  # 1 batter appearance, 1 pitcher appearance
    assert "GAME_ID" in table.column_names
    assert "B_H" in table.column_names
    assert "P_H" in table.column_names


def test_parse_substitutions(tmp_path: Path) -> None:
    fake_eva = (
        b"id,BOS202404010\n"
        b"info,date,2024/04/01\n"
        b"info,hometeam,BOS\n"
        b"info,visteam,BAL\n"
        b"start,play01,Batter One,0,1,4\n"
        b"start,pitch01,Pitcher One,1,1,1\n"
        b"play,1,0,play01,00,,S\n"
        b"sub,sub01,Sub Batter,0,1,4\n"
        b"play,1,0,sub01,00,,K\n"
        b"data,er,pitch01,0\n"
    )
    eva_path = tmp_path / "2024BOS.EVA"
    eva_path.write_bytes(fake_eva)

    parser = RetrosheetSubstitutionsParser()
    table = parser.parse_files([eva_path], year=2024)

    assert isinstance(table, pa.Table)
    assert len(table) >= 1
    assert "SUB_ID" in table.column_names


def test_parse_reference_tables(tmp_path: Path) -> None:
    parks_csv = tmp_path / "ballparks.csv"
    parks_csv.write_text(
        "PARKID,NAME,AKA,CITY,STATE,START,END,LEAGUE,NOTES\n"
        "BOS07,Fenway Park,,Boston,MA,04/20/1912,,AL,\n",
        encoding="utf-8",
    )

    parser = RetrosheetReferenceParser()
    table = parser.parse_file("ballparks", parks_csv)

    assert isinstance(table, pa.Table)
    assert len(table) == 1
    assert table["park_id"].to_pylist() == ["BOS07"]
    assert table["name"].to_pylist() == ["Fenway Park"]
    assert table["city"].to_pylist() == ["Boston"]


def test_parse_gamelogs(tmp_path: Path) -> None:
    gl_path = tmp_path / "gl2024.txt"
    line = '20240328,0,Thu,LAN,NL,1,SDN,NL,1,5,2,54,D,,,,SEO01,15952,185,"000101003","000000020",37,11,1,0,0,5,0,0,0,1,0,3,1,0,0,0,8,6,2,2,0,0,27,11,1,0,0,0,31,4,0,0,0,2,0,0,1,0,0,7,2,0,0,0,9,5,5,5,1,0,27,9,2,0,0,0,hp_id,hp_name,1b_id,1b_name,2b_id,2b_name,3b_id,3b_name,lf_id,lf_name,rf_id,rf_name,v_mgr_id,v_mgr_name,h_mgr_id,h_mgr_name,w_pit_id,w_pit_name,l_pit_id,l_pit_name,s_pit_id,s_pit_name,gwrbi_id,gwrbi_name,v_sp_id,v_sp_name,h_sp_id,h_sp_name,v_b1_id,v_b1_name,8,v_b2_id,v_b2_name,6,v_b3_id,v_b3_name,7,v_b4_id,v_b4_name,3,v_b5_id,v_b5_name,9,v_b6_id,v_b6_name,4,v_b7_id,v_b7_name,5,v_b8_id,v_b8_name,2,v_b9_id,v_b9_name,1,h_b1_id,h_b1_name,8,h_b2_id,h_b2_name,6,h_b3_id,h_b3_name,7,h_b4_id,h_b4_name,3,h_b5_id,h_b5_name,9,h_b6_id,h_b6_name,4,h_b7_id,h_b7_name,5,h_b8_id,h_b8_name,2,h_b9_id,h_b9_name,1,additional_info,acquisition_info'
    gl_path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    parser = RetrosheetGameLogParser()
    table = parser.parse_file(gl_path)

    assert isinstance(table, pa.Table)
    assert len(table) == 2
    assert table.schema.field("attendance").type == pa.int32()
    assert table["attendance"].to_pylist() == [15952, 15952]
    assert table["visiting_team"].to_pylist() == ["LAN", "LAN"]


def test_parse_rosters(tmp_path: Path) -> None:
    ros_path = tmp_path / "BOS2024.ROS"
    ros_path.write_text(
        "deve001,Devers,Rafael,L,R,BOS,3B\ndurj001,Duran,Jarren,L,R,BOS,OF\n", encoding="utf-8"
    )

    parser = RetrosheetRosterParser()
    table = parser.parse_files([ros_path], year=2024)

    assert isinstance(table, pa.Table)
    assert len(table) == 2
    assert table["last_name"].to_pylist() == ["Devers", "Duran"]
    assert table["bats"].to_pylist() == ["L", "L"]
    assert table["year"].to_pylist() == [2024, 2024]


@respx.mock
def test_retrosheet_source_orchestrator(tmp_path: Path, retro_repo: RetroRepo) -> None:
    cache_config = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cache_config)

    fake_eva = (
        b"id,BOS202404010\n"
        b"info,date,2024/04/01\n"
        b"info,hometeam,BOS\n"
        b"info,visteam,BAL\n"
        b"start,play01,Batter One,0,1,4\n"
        b"start,pitch01,Pitcher One,1,1,1\n"
        b"play,1,0,play01,00,,S\n"
        b"data,er,pitch01,0\n"
    )
    retro_repo.add("seasons/2024/TEAM2024", b"BOS,A\n")
    retro_repo.add("seasons/2024/2024BOS.EVA", fake_eva)
    retro_repo.add("seasons/2024/BOS2024.ROS", b"play01,One,Batter,R,R,BOS,OF\n")
    retro_repo.add(
        "reference/teams.csv",
        b"TEAM,LEAGUE,CITY,NICKNAME,FIRST,LAST\nBOS,AL,Boston,Red Sox,1901,2024\n",
    )
    retro_repo.mount()

    # 1. First run parses and caches
    events_table = source.events(2024)
    assert len(events_table) == 1
    assert events_table["GAME_ID"].to_pylist() == ["BOS202404010"]

    # Check two-tier directory structure
    raw_season = cache_config.raw_dir("retrosheet", "event_files", 2024)
    processed_season = cache_config.processed_dir("retrosheet", "events", 2024)
    assert (raw_season / "2024BOS.EVA").exists()
    assert (processed_season / "part-events.parquet").exists()

    # Check manifest recorded completion
    assert source.store.is_cached(_spec("events"), "events", 2024)

    # 2. Second run reads from processed parquet cache without network calls
    respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/2024/TEAM2024").mock(
        return_value=httpx.Response(500)
    )
    respx.get(f"{GITHUB_RETROSHEET_BASE}/seasons/2024/2024BOS.EVA").mock(
        return_value=httpx.Response(500)
    )
    cached_table = source.events(2024, refresh=False)
    assert len(cached_table) == 1

    # 3. Boxscores extraction and caching
    batting, pitching = source.boxscores(2024)
    assert len(batting) > 0
    assert len(pitching) > 0
    assert source.store.is_cached(_spec("boxscores_batting"), "batting", 2024)
    assert source.store.is_cached(_spec("boxscores_pitching"), "pitching", 2024)

    # 4. Reference tables
    teams_table = source.reference("teams")
    assert len(teams_table) == 1
    assert teams_table["team_id"].to_pylist() == ["BOS"]


@respx.mock
def test_retrosheet_downloader_2025_casing(tmp_path: Path, retro_repo: RetroRepo) -> None:
    """Verify download_gamelog resolves the uppercase GL2025.TXT listed by the tree."""
    cache_config = LakeConfig(home=tmp_path)
    source = RetrosheetSource(cache_config=cache_config)
    retro_repo.add(
        "seasons/2025/GL2025.TXT",
        b"20250327,0,Thu,BAL,AL,1,BOS,AL,1,5,3,54,D,0,0,0,BOS07,37000,180\n",
    )
    retro_repo.mount()

    gl_path = source.downloader.download_gamelog(2025)
    assert gl_path.exists()
    assert gl_path.parent == cache_config.raw_dir("retrosheet", "gamelogs", 2025)
    assert b"20250327" in gl_path.read_bytes()


def test_boxscores_include_substitutes_and_relievers_not_just_starters(tmp_path: Path) -> None:
    """Regression: chadwickpy hands back the *latest* player of each chain; walking only `next`
    emitted exactly the starters (2 pitchers per game, ~20 batters) for every season."""
    game = (
        b"id,BOS202404010\n"
        b"info,date,2024/04/01\n"
        b"info,hometeam,BOS\n"
        b"info,visteam,BAL\n"
        b"start,vis01,Vis One,0,1,4\n"
        b"start,vpit1,Vis Pitcher,0,0,1\n"
        b"start,hom01,Home One,1,1,4\n"
        b"start,hpit1,Home Pitcher,1,0,1\n"
        b"play,1,0,vis01,00,,S\n"
        b"sub,vpit2,Vis Reliever,0,0,1\n"
        b"sub,vis02,Vis Sub,0,1,4\n"
        b"play,1,0,vis02,00,,K\n"
        b"sub,hpit2,Home Reliever,1,0,1\n"
        b"play,1,1,hom01,00,,K\n"
        b"data,er,hpit1,0\n"
    )
    path = tmp_path / "2024BOS.EVA"
    path.write_bytes(game)
    batting, pitching = RetrosheetBoxScoreParser().parse_files([path], year=2024)
    assert set(batting["player_id"].to_pylist()) >= {"vis01", "vis02", "hom01"}
    pitchers = pitching.to_pydict()
    assert set(pitchers["pitcher_id"]) == {"vpit1", "vpit2", "hpit1", "hpit2"}
    starters = {
        p for p, fl in zip(pitchers["pitcher_id"], pitchers["starter_fl"], strict=True) if fl
    }
    assert starters == {"vpit1", "hpit1"}
    by_pitcher = dict(zip(pitchers["pitcher_id"], pitchers["seq"], strict=True))
    assert by_pitcher["vpit1"] == 1 and by_pitcher["vpit2"] == 2
