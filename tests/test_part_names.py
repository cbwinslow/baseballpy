"""Processed part file names: short, no repeated dataset or season, and readable by every tool."""

from pathlib import Path

import pandas as pd
import polars as pl
import pyarrow as pa
import pyarrow.dataset as pads
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore, part_filename
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog


@pytest.mark.parametrize(
    ("dataset", "chunk", "season", "expected"),
    [
        ("award_recipients", "award_recipients_2024_AAACMVP", 2024, "part-AAACMVP.parquet"),
        ("players_season", "players_season_2024_sport1", 2024, "part-sport1.parquet"),
        ("standings_by_league", "standings_by_league_2024", 2024, "part-data.parquet"),
        ("ref_awards", "ref_awards", None, "part-data.parquet"),
        ("events", "events", 2022, "part-data.parquet"),
        ("rosters", "rosters_2023", 2023, "part-data.parquet"),
        ("pitches", "2024-04-01_2024-04-05", 2024, "part-2024-04-01_2024-04-05.parquet"),
        ("box_batting", "745000", 2024, "part-745000.parquet"),
        ("register", "data", None, "part-data.parquet"),
        ("gamelogs", "gl2023", 2023, "part-gl2023.parquet"),
    ],
)
def test_part_filename_drops_what_the_folders_already_say(
    dataset: str, chunk: str, season: int | None, expected: str
) -> None:
    assert part_filename(dataset, chunk, season) == expected


def test_two_chunks_that_would_share_a_file_are_refused(tmp_path: Path) -> None:
    catalog.register_all()
    store = ProcessedStore(LakeConfig(home=tmp_path))
    spec = get_dataset("retrosheet", "rosters")
    table = pa.table({"x": [1]})
    store.put(spec, table, chunk_id="rosters_2023", season=2023)
    store.put(spec, table, chunk_id="rosters_2023", season=2023)  # same chunk again is a rerun
    with pytest.raises(ValueError, match="would share the file"):
        store.put(spec, table, chunk_id="data", season=2023)


def test_every_reader_sees_the_same_rows_in_the_renamed_tree(tmp_path: Path) -> None:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec = get_dataset("mlb_api", "award_recipients")
    for season in (2023, 2024):
        for award in ("ALMVP", "NLMVP"):
            store.put(
                spec,
                pa.table({"award": [award, award], "year": [season, season]}),
                chunk_id=f"award_recipients_{season}_{award}",
                season=season,
            )
    folder = tmp_path / "processed" / "mlb_api" / "award_recipients"
    names = sorted(p.name for p in folder.rglob("*.parquet"))
    assert names == [
        "part-ALMVP.parquet",
        "part-ALMVP.parquet",
        "part-NLMVP.parquet",
        "part-NLMVP.parquet",
    ]
    assert sorted(p.parent.name for p in folder.rglob("*.parquet")) == [
        "season=2023",
        "season=2023",
        "season=2024",
        "season=2024",
    ]

    con = BaseballDatabase(db_path=":memory:", cache_config=cfg).connect()
    assert con.execute(f"SELECT count(*) FROM {spec.view}")  # noqa: S608 - registry view name.fetchone() == (8,)
    glob = str(folder / "**" / "*.parquet")
    assert pl.scan_parquet(glob, hive_partitioning=True).collect().height == 8
    assert len(pd.read_parquet(folder)) == 8
    assert pads.dataset(folder, partitioning="hive").count_rows() == 8


def test_a_manifest_with_the_old_name_is_renamed_on_first_use(tmp_path: Path) -> None:
    cfg = LakeConfig(home=tmp_path)
    folder = cfg.processed_dir("lahman", "batting")
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text('{"chunks": {}}', encoding="utf-8")
    cfg.dataset_manifest("lahman", "batting")
    assert (folder / "_manifest.json").exists() and not (folder / "manifest.json").exists()
