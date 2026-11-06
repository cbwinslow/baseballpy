"""``baseballpy.read`` and ``baseballpy.sql``: the two doors from the lake to a DataFrame."""

from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import baseballpy as bp
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.database import BaseballDatabase, _view_sql
from baseballpy.sources import catalog


def _pitches(speeds: list[float], year: int) -> pa.Table:
    return pa.table(
        {
            "pitch_type": ["FF"] * len(speeds),
            "release_speed": speeds,
            "pitcher": [660271] * len(speeds),
            "game_year": [year] * len(speeds),
        }
    )


@pytest.fixture
def lake(tmp_path: Path) -> LakeConfig:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    pitches = get_dataset("statcast", "pitches")
    store.put(pitches, _pitches([97.5, 85.2], 2023), chunk_id="a", season=2023)
    store.put(pitches, _pitches([99.1], 2023), chunk_id="b", season=2023)
    store.put(pitches, _pitches([88.0, 90.0, 91.0], 2024), chunk_id="a", season=2024)
    store.put(
        get_dataset("chadwick", "register"),
        pa.table({"key_person": ["ohtans01"], "key_mlbam": [660271], "name_last": ["Ohtani"]}),
    )
    BaseballDatabase(cache_config=cfg).sync_views()
    return cfg


def test_read_all_seasons_has_every_row_and_a_season_column(lake: LakeConfig) -> None:
    df = bp.read("statcast.pitches", config=lake)
    assert isinstance(df, pl.DataFrame)
    assert df.height == 6
    assert sorted(df["season"].unique().to_list()) == [2023, 2024]


def test_read_seasons_and_columns_open_only_what_is_asked(lake: LakeConfig) -> None:
    df = bp.read("statcast.pitches", seasons=2024, columns=["release_speed", "season"], config=lake)
    assert df.columns == ["release_speed", "season"]
    assert df.height == 3 and df["season"].unique().to_list() == [2024]
    both = bp.read("statcast.pitches", seasons=range(2023, 2025), config=lake)
    assert both.height == 6


def test_read_backends_and_lazy(lake: LakeConfig) -> None:
    arrow = bp.read("statcast.pitches", seasons=2023, backend="pyarrow", config=lake)
    assert isinstance(arrow, pa.Table) and arrow.num_rows == 3
    lazy = bp.read("statcast.pitches", lazy=True, config=lake)
    assert isinstance(lazy, pl.LazyFrame)
    assert lazy.filter(pl.col("release_speed") > 95).collect().height == 2
    with pytest.raises(ValueError, match="lazy"):
        bp.read("statcast.pitches", lazy=True, backend="pyarrow", config=lake)


def test_read_resolves_view_and_bare_names_and_rejects_bad_input(lake: LakeConfig) -> None:
    assert bp.read("statcast_pitches", seasons=2024, config=lake).height == 3
    with pytest.raises(ValueError, match="unknown dataset"):
        bp.read("nope", config=lake)
    with pytest.raises(ValueError, match="not split by season"):
        bp.read("chadwick.register", seasons=2024, config=lake)
    with pytest.raises(FileNotFoundError, match="ingest"):
        bp.read("statcast.pitches", config=LakeConfig(home=lake.home / "empty"))


def test_sql_gives_the_same_rows_as_read_and_can_join(lake: LakeConfig) -> None:
    via_sql = bp.sql(
        "SELECT season, count(*) AS n, sum(release_speed) AS total "
        "FROM statcast_pitches GROUP BY season ORDER BY season",
        config=lake,
    )
    via_read = (
        bp.read("statcast.pitches", config=lake)
        .group_by("season")
        .agg(pl.len().alias("n"), pl.col("release_speed").sum().alias("total"))
        .sort("season")
    )
    assert via_sql["n"].to_list() == via_read["n"].to_list() == [3, 3]
    assert via_sql["total"].to_list() == pytest.approx(via_read["total"].to_list())
    joined = bp.sql(
        "SELECT r.name_last, count(*) AS n FROM statcast_pitches p "
        "JOIN chadwick_register r ON p.pitcher = r.key_mlbam GROUP BY r.name_last",
        backend="pyarrow",
        config=lake,
    )
    assert joined.to_pylist() == [{"name_last": "Ohtani", "n": 6}]


def test_sql_refuses_to_change_data_and_needs_a_database(lake: LakeConfig) -> None:
    with pytest.raises(Exception, match="(?i)read-only|read only"):
        bp.sql("DROP VIEW statcast_pitches", config=lake)
    with pytest.raises(FileNotFoundError, match="db sync"):
        bp.sql("SELECT 1", config=LakeConfig(home=lake.home / "empty"))


def test_registered_views_skip_the_schema_merge_and_parts_share_one_schema(
    lake: LakeConfig,
) -> None:
    strict = _view_sql(Path("x/**/*.parquet"), True, True)
    assert "union_by_name" not in strict and "hive_partitioning" in strict
    assert "union_by_name = true" in _view_sql(Path("x/**/*.parquet"), False, False)
    parts = sorted(lake.processed_dir("statcast", "pitches").rglob("*.parquet"))
    assert len(parts) == 3
    assert len({pq.read_schema(p).to_string() for p in parts}) == 1
