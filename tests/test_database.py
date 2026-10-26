"""Unit tests for consolidated multi-season DuckDB catalog and cross-source joins."""

from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.atomic import atomic_write_parquet
from baseballpy.core.config import CacheConfig
from baseballpy.database import BaseballDatabase, connect_db, sync_database


@pytest.fixture
def mock_cache_env(tmp_path: Path) -> CacheConfig:
    """Populate a temporary mock cache directory with multi-season Parquet tables."""
    cache = CacheConfig(base_dir=tmp_path)

    # 1. Multi-season Statcast: season=2023 and season=2024
    s23_dir = cache.statcast_dir / "season=2023"
    s24_dir = cache.statcast_dir / "season=2024"
    s23_dir.mkdir(parents=True, exist_ok=True)
    s24_dir.mkdir(parents=True, exist_ok=True)

    pitches_2023 = pa.table(
        {
            "pitch_type": ["FF", "SL"],
            "release_speed": [97.5, 85.2],
            "pitcher": [660271, 545361],
            "game_year": [2023, 2023],
        }
    )
    pitches_2024 = pa.table(
        {
            "pitch_type": ["FF", "CH"],
            "release_speed": [99.1, 88.0],
            "pitcher": [660271, 605151],
            "game_year": [2024, 2024],
        }
    )
    atomic_write_parquet(pitches_2023, s23_dir / "chunk1.parquet")
    atomic_write_parquet(pitches_2024, s24_dir / "chunk1.parquet")

    # 2. Chadwick Register
    chadwick_dir = cache.chadwick_dir / "processed"
    chadwick_dir.mkdir(parents=True, exist_ok=True)
    register_table = pa.table(
        {
            "key_person": ["ohtans01", "troutm01", "degroj01"],
            "key_mlbam": [660271, 545361, 605151],
            "key_retro": ["ohtas001", "troum001", "degro001"],
            "key_bbref": ["ohtansh01", "troutmi01", "degroja01"],
            "name_last": ["Ohtani", "Trout", "deGrom"],
            "name_first": ["Shohei", "Mike", "Jacob"],
        }
    )
    atomic_write_parquet(register_table, chadwick_dir / "register.parquet")

    # 3. Lahman People Table
    lahman_dir = cache.lahman_dir / "processed"
    lahman_dir.mkdir(parents=True, exist_ok=True)
    people_table = pa.table(
        {
            "playerID": ["ohtansh01", "troutmi01", "degroja01"],
            "bbrefID": ["ohtansh01", "troutmi01", "degroja01"],
            "nameFirst": ["Shohei", "Mike", "Jacob"],
            "nameLast": ["Ohtani", "Trout", "deGrom"],
            "weight": [210, 235, 180],
            "height": [76, 74, 76],
        }
    )
    atomic_write_parquet(people_table, lahman_dir / "people.parquet")

    # 4. Retrosheet Events
    retro_events_dir = cache.retrosheet_dir / "processed" / "events" / "season=2023"
    retro_events_dir.mkdir(parents=True, exist_ok=True)
    events_table = pa.table(
        {
            "game_id": ["ANA202304010", "ANA202304010"],
            "event_cd": [3, 23],
            "resp_pit_id": ["ohtas001", "troum001"],
        }
    )
    atomic_write_parquet(events_table, retro_events_dir / "events.parquet")

    return cache


def test_database_views_and_multi_season_query(mock_cache_env: CacheConfig) -> None:
    """Verify DuckDB database auto-discovers views and queries multi-season data."""
    db = BaseballDatabase(db_path=":memory:", cache_config=mock_cache_env)
    con = db.connect()

    # Query multi-season statcast
    df = con.sql(
        "SELECT season, pitch_type, release_speed, pitcher FROM statcast_pitches ORDER BY release_speed DESC"
    ).pl()
    assert len(df) == 4
    # Check that season column is populated from Hive directory
    assert 2023 in df["season"].to_list()
    assert 2024 in df["season"].to_list()

    # Verify partition pruning works
    s24_df = con.sql("SELECT * FROM statcast_pitches WHERE season = 2024").pl()
    assert len(s24_df) == 2
    assert (s24_df["season"] == 2024).all()


def test_cross_source_sql_join(mock_cache_env: CacheConfig) -> None:
    """Verify cross-source SQL joins joining Statcast, Chadwick, and Lahman."""
    con = connect_db(db_path=":memory:", cache_config=mock_cache_env)

    # Join Statcast pitches -> Chadwick Register -> Lahman People
    query = """
    SELECT
        p.season,
        p.pitch_type,
        p.release_speed,
        reg.name_last,
        lahman.weight,
        lahman.height
    FROM statcast_pitches p
    JOIN chadwick_register reg ON p.pitcher = reg.key_mlbam
    JOIN lahman_people lahman ON reg.key_bbref = lahman.bbrefID
    WHERE p.pitcher = 660271
    ORDER BY p.release_speed DESC
    """
    joined = con.sql(query).pl()
    assert len(joined) == 2
    assert (joined["name_last"] == "Ohtani").all()
    assert (joined["weight"] == 210).all()
    assert 99.1 in joined["release_speed"].to_list()


def test_sync_database_helper(mock_cache_env: CacheConfig, tmp_path: Path) -> None:
    """Verify sync_database helper registers views in physical file."""
    db_file = tmp_path / "test_baseball.duckdb"
    count = sync_database(db_path=db_file, cache_config=mock_cache_env)
    assert count >= 4  # statcast, retrosheet_events, lahman_people, chadwick_register

    # Reconnect and verify tables exist
    con = connect_db(db_path=db_file, cache_config=mock_cache_env)
    tables = con.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    assert "statcast_pitches" in table_names
    assert "chadwick_register" in table_names
    assert "lahman_people" in table_names
    assert "retrosheet_events" in table_names
