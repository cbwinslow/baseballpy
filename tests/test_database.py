"""Unit tests for the registry-driven DuckDB catalog over the processed/ tier."""

import shutil
from pathlib import Path

import duckdb
import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.database import (
    BaseballDatabase,
    DatabaseReadOnlyError,
    connect_db,
    sync_database,
)
from baseballpy.sources import catalog


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    """Populate a temporary v2 lake with multi-season Parquet datasets."""
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)

    pitches = get_dataset("statcast", "pitches")
    store.put(
        pitches,
        pa.table(
            {
                "pitch_type": ["FF", "SL"],
                "release_speed": [97.5, 85.2],
                "pitcher": [660271, 545361],
                "game_year": [2023, 2023],
            }
        ),
        chunk_id="a",
        season=2023,
    )
    store.put(
        pitches,
        pa.table(
            {
                "pitch_type": ["FF", "CH"],
                "release_speed": [99.1, 88.0],
                "pitcher": [660271, 605151],
                "game_year": [2024, 2024],
            }
        ),
        chunk_id="a",
        season=2024,
    )
    store.put(
        get_dataset("chadwick", "register"),
        pa.table(
            {
                "key_person": ["ohtans01", "troutm01", "degroj01"],
                "key_mlbam": [660271, 545361, 605151],
                "key_retro": ["ohtas001", "troum001", "degro001"],
                "key_bbref": ["ohtansh01", "troutmi01", "degroja01"],
                "name_last": ["Ohtani", "Trout", "deGrom"],
                "name_first": ["Shohei", "Mike", "Jacob"],
            }
        ),
    )
    store.put(
        get_dataset("lahman", "People"),
        pa.table(
            {
                "playerID": ["ohtansh01", "troutmi01", "degroja01"],
                "bbrefID": ["ohtansh01", "troutmi01", "degroja01"],
                "weight": [210, 235, 180],
                "height": [76, 74, 76],
            }
        ),
    )
    store.put(
        get_dataset("retrosheet", "events"),
        pa.table({"GAME_ID": ["ANA202304010", "ANA202304010"], "EVENT_CD": [3, 23]}),
        chunk_id="events",
        season=2023,
    )
    return cfg


def test_database_views_and_multi_season_query(lake: LakeConfig) -> None:
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    df = con.sql(
        "SELECT season, pitch_type, release_speed, pitcher FROM statcast_pitches "
        "ORDER BY release_speed DESC"
    ).pl()
    assert len(df) == 4
    assert set(df["season"].to_list()) == {2023, 2024}
    s24 = con.sql("SELECT * FROM statcast_pitches WHERE season = 2024").pl()
    assert len(s24) == 2


def test_cross_source_sql_join(lake: LakeConfig) -> None:
    con = connect_db(db_path=":memory:", cache_config=lake)
    joined = con.sql(
        """
        SELECT p.season, p.release_speed, reg.name_last, lahman.weight
        FROM statcast_pitches p
        JOIN chadwick_register reg ON p.pitcher = reg.key_mlbam
        JOIN lahman_people lahman ON reg.key_bbref = lahman.bbrefID
        WHERE p.pitcher = 660271
        ORDER BY p.release_speed DESC
        """
    ).pl()
    assert len(joined) == 2
    assert (joined["name_last"] == "Ohtani").all()
    assert 99.1 in joined["release_speed"].to_list()


def test_sync_database_helper(lake: LakeConfig, tmp_path: Path) -> None:
    db_file = tmp_path / "databases" / "x.duckdb"
    count = sync_database(db_path=db_file, cache_config=lake)
    assert count >= 4 + 2  # four datasets + v_player_crosswalk + v_season_catalog
    con = duckdb.connect(str(db_file), read_only=True)
    names = {
        r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }
    con.close()
    assert {"statcast_pitches", "lahman_people", "chadwick_register", "retrosheet_events"} <= names


def test_default_database_path_is_under_lake_home(lake: LakeConfig) -> None:
    db = BaseballDatabase(cache_config=lake)
    assert db.db_path == lake.home / "databases" / "baseball.duckdb"
    assert not db.db_path.parent.exists()  # constructing never creates directories
    db.sync_views()
    assert db.db_path.exists()


def test_leaderboards_never_leak_into_pitches(lake: LakeConfig) -> None:
    store = ProcessedStore(lake)
    from baseballpy.sources.statcast.leaderboards import leaderboard_spec

    board = pa.table({"player_id": [1, 2], "year": [2024, 2024], "xba": [0.3, 0.2]})
    store.put(
        leaderboard_spec("expected_statistics", board.schema), board, chunk_id="x", season=2024
    )
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    assert con.execute("SELECT count(*) FROM statcast_pitches").fetchone() == (4,)
    assert con.execute(
        "SELECT count(*) FROM statcast_leaderboard_expected_statistics"
    ).fetchone() == (2,)


def test_events_and_postseason_are_separate_views(lake: LakeConfig) -> None:
    store = ProcessedStore(lake)
    store.put(
        get_dataset("retrosheet", "events_postseason"),
        pa.table({"GAME_ID": ["BOS202310280"], "EVENT_CD": [2]}),
        chunk_id="events",
        season=2023,
    )
    regular = lake.processed_dir("retrosheet", "events") / "season=2023"
    postseason = lake.processed_dir("retrosheet", "events_postseason") / "season=2023"
    assert regular.is_dir() and postseason.is_dir() and regular != postseason
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    assert con.execute("SELECT count(*) FROM retrosheet_events").fetchone() == (2,)
    assert con.execute("SELECT count(*) FROM retrosheet_events_postseason").fetchone() == (1,)


def test_physical_season_column_does_not_duplicate_hive_season(lake: LakeConfig) -> None:
    store = ProcessedStore(lake)
    schedule = get_dataset("mlb_api", "schedule")
    store.put(
        schedule, pa.table({"game_pk": [1, 2], "season": [2024, 2024]}), chunk_id="s", season=2024
    )
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    cols = [r[0] for r in con.execute("DESCRIBE mlb_schedule").fetchall()]
    assert cols.count("season") == 1
    assert con.execute("SELECT season FROM mlb_schedule LIMIT 1").fetchone() == (2024,)


def test_every_registered_dataset_with_data_gets_a_view(tmp_path: Path) -> None:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    for spec in DATASETS.values():
        store.put(
            spec,
            spec.schema.empty_table(),
            chunk_id="data",
            season=2024 if spec.partition == "season" else None,
        )
    db = BaseballDatabase(db_path=":memory:", cache_config=cfg)
    con = db.connect()
    views = {
        r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()
    }
    assert {spec.view for spec in DATASETS.values()} <= views
    assert {"v_player_crosswalk", "v_season_catalog"} <= views


def test_unregistered_dataset_directories_are_still_queryable(lake: LakeConfig) -> None:
    from baseballpy.sources.lahman.api import lahman_spec

    table = pa.table({"playerID": ["a"], "awardID": ["MVP"]})
    ProcessedStore(lake).put(lahman_spec("AwardsPlayers", table.schema), table)
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    assert con.execute("SELECT count(*) FROM lahman_awardsplayers").fetchone() == (1,)


def test_season_catalog_and_crosswalk_views(lake: LakeConfig) -> None:
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    rows = con.execute(
        "SELECT dataset, season, row_count FROM v_season_catalog "
        "WHERE source = 'statcast' ORDER BY season"
    ).fetchall()
    assert rows == [("pitches", 2023, 2), ("pitches", 2024, 2)]
    assert con.execute("SELECT count(*) FROM v_player_crosswalk").fetchone() == (3,)


def test_read_only_requires_views_then_works(lake: LakeConfig, tmp_path: Path) -> None:
    db_file = tmp_path / "ro.duckdb"
    duckdb.connect(str(db_file)).close()  # an empty database file, no views yet
    with pytest.raises(DatabaseReadOnlyError, match="baseballpy db sync"):
        BaseballDatabase(db_path=db_file, cache_config=lake, read_only=True).connect()

    sync_database(db_path=db_file, cache_config=lake)
    con = BaseballDatabase(db_path=db_file, cache_config=lake, read_only=True).connect()
    assert con.execute("SELECT count(*) FROM statcast_pitches").fetchone() == (4,)
    con.close()


def test_read_only_sync_is_refused(lake: LakeConfig, tmp_path: Path) -> None:
    db = BaseballDatabase(db_path=tmp_path / "x.duckdb", cache_config=lake, read_only=True)
    with pytest.raises(DatabaseReadOnlyError):
        db.sync_views()


def test_view_paths_with_quotes_are_escaped(tmp_path: Path) -> None:
    home = tmp_path / "o'brien"
    catalog.register_all()
    cfg = LakeConfig(home=home)
    ProcessedStore(cfg).put(get_dataset("chadwick", "register"), pa.table({"key_person": ["a"]}))
    con = BaseballDatabase(db_path=":memory:", cache_config=cfg).connect()
    assert con.execute("SELECT count(*) FROM chadwick_register").fetchone() == (1,)


def test_deleting_the_cache_loses_no_dataset_and_every_view_still_resolves(
    lake: LakeConfig,
) -> None:
    cache = lake.http_cache_root
    cache.mkdir(parents=True)
    (cache / "response.bin").write_bytes(b"cached")
    con = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    before = con.execute("SELECT count(*) FROM statcast_pitches").fetchone()
    shutil.rmtree(cache)
    after_db = BaseballDatabase(db_path=":memory:", cache_config=lake).connect()
    assert not cache.exists()
    assert after_db.execute("SELECT count(*) FROM statcast_pitches").fetchone() == before == (4,)
    assert after_db.execute("SELECT count(*) FROM chadwick_register").fetchone() == (3,)
    assert after_db.execute("SELECT count(*) FROM lahman_people").fetchone() == (3,)
