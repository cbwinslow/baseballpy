"""Compaction: many chunk files become a few big ones, nothing is lost, ingests still resume."""

import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

import baseballpy as bp
from baseballpy.cli import main
from baseballpy.core import compact as compact_module
from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.stores import ProcessedStore, manifest_key
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog


def _pitches(speeds: list[float], year: int) -> pa.Table:
    """A full-schema Statcast table (every other column empty) with the given speeds."""
    schema = get_dataset("statcast", "pitches").schema
    n = len(speeds)
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["release_speed"] = pa.array(speeds, schema.field("release_speed").type)
    columns["pitcher"] = pa.array([660271] * n, schema.field("pitcher").type)
    columns["game_year"] = pa.array([year] * n, schema.field("game_year").type)
    return pa.table(columns, schema=schema)


@pytest.fixture
def spec() -> DatasetSpec:
    catalog.register_all()
    return get_dataset("statcast", "pitches")


@pytest.fixture
def lake(tmp_path: Path, spec: DatasetSpec) -> LakeConfig:
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    for chunk, speeds in (("a", [90.0, 91.0]), ("b", [92.0]), ("c", [93.0, 94.0, 95.0])):
        store.put(spec, _pitches(speeds, 2023), chunk_id=chunk, season=2023)
    store.put(spec, _pitches([80.0], 2024), chunk_id="a", season=2024)  # one chunk: left alone
    return cfg


def _files(cfg: LakeConfig, spec: DatasetSpec, season: int) -> list[str]:
    return sorted(
        p.name for p in cfg.processed_dir(spec.source, spec.name, season).glob("*.parquet")
    )


def test_chunks_become_one_file_and_every_row_and_chunk_survives(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    before = bp.read("statcast.pitches", seasons=2023, config=lake).sort("release_speed")
    report = compact_dataset(spec, lake)
    assert (report.groups, report.chunks, report.files_before, report.files_after) == (1, 3, 3, 1)
    assert _files(lake, spec, 2023) == ["compact-0001.parquet"]
    assert len(_files(lake, spec, 2024)) == 1 and _files(lake, spec, 2024)[0].startswith("part-")
    after = bp.read("statcast.pitches", seasons=2023, config=lake).sort("release_speed")
    assert after.equals(before)
    store = ProcessedStore(lake)
    assert store.read_part(spec, "b", 2023)["release_speed"].to_pylist() == [92.0]
    assert store.read_part(spec, "c", 2023)["release_speed"].to_pylist() == [93.0, 94.0, 95.0]
    assert all(store.is_cached(spec, c, 2023) for c in "abc")


def test_a_rerun_changes_nothing_and_a_new_chunk_is_merged_in(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    compact_dataset(spec, lake)
    again = compact_dataset(spec, lake)
    assert again.groups == 0 and _files(lake, spec, 2023) == ["compact-0001.parquet"]
    ProcessedStore(lake).put(spec, _pitches([96.0], 2023), chunk_id="d", season=2023)
    merged = compact_dataset(spec, lake)
    assert merged.groups == 1 and merged.chunks == 4
    assert len(_files(lake, spec, 2023)) == 1
    assert bp.read("statcast.pitches", seasons=2023, config=lake).height == 7


def test_a_chunk_downloaded_again_replaces_its_rows_and_never_duplicates(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    compact_dataset(spec, lake)
    store = ProcessedStore(lake)
    store.put(spec, _pitches([100.0, 101.0], 2023), chunk_id="b", season=2023)
    speeds = sorted(bp.read("statcast.pitches", seasons=2023, config=lake)["release_speed"])
    assert speeds == [90.0, 91.0, 93.0, 94.0, 95.0, 100.0, 101.0]
    assert store.read_part(spec, "a", 2023)["release_speed"].to_pylist() == [90.0, 91.0]
    assert store.read_part(spec, "b", 2023)["release_speed"].to_pylist() == [100.0, 101.0]
    compact_dataset(spec, lake)
    assert bp.read("statcast.pitches", seasons=2023, config=lake).height == 7


def test_dry_run_changes_nothing(lake: LakeConfig, spec: DatasetSpec) -> None:
    before = _files(lake, spec, 2023)
    report = compact_dataset(spec, lake, dry_run=True)
    assert report.groups == 1 and report.files_after == 1
    assert _files(lake, spec, 2023) == before


def test_a_bad_copy_is_refused_and_the_small_files_stay(
    lake: LakeConfig, spec: DatasetSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = compact_module.write_compacted

    def corrupt(path, schema, tables, **kw):  # type: ignore[no-untyped-def]
        key, table = tables[0]
        return original(
            path,
            schema,
            [
                (
                    key,
                    table.set_column(
                        table.schema.get_field_index("release_speed"),
                        "release_speed",
                        pa.array([0.0] * table.num_rows),
                    ),
                )
            ]
            + tables[1:],
            **kw,
        )

    monkeypatch.setattr(compact_module, "write_compacted", corrupt)
    before = _files(lake, spec, 2023)
    with pytest.raises(ValueError, match="differs after compaction"):
        compact_dataset(spec, lake)
    assert _files(lake, spec, 2023) == before


def test_leftovers_of_an_interrupted_run_are_cleaned_without_duplicates(
    lake: LakeConfig, spec: DatasetSpec, tmp_path: Path
) -> None:
    store = ProcessedStore(lake)
    saved = tmp_path / "saved.parquet"
    shutil.copy(store.part_path(spec, "a", 2023), saved)
    compact_dataset(spec, lake)
    orphan = lake.processed_dir(spec.source, spec.name, 2023) / "compact-0009.parquet"
    shutil.copy(lake.processed_dir(spec.source, spec.name, 2023) / "compact-0001.parquet", orphan)
    shutil.copy(
        saved, store.part_path(spec, "a", 2023)
    )  # a part that is also inside the compact file
    compact_dataset(spec, lake)
    assert not orphan.exists()
    assert bp.read("statcast.pitches", seasons=2023, config=lake).height == 6
    assert len(_files(lake, spec, 2023)) == 1


def test_duckdb_views_and_the_footer_map_see_the_compacted_file(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    compact_dataset(spec, lake)
    BaseballDatabase(cache_config=lake).sync_views()
    counts = bp.sql(
        "SELECT season, count(*) AS n FROM statcast_pitches GROUP BY season ORDER BY season",
        config=lake,
    )
    assert counts["n"].to_list() == [6, 1]
    file = lake.processed_dir(spec.source, spec.name, 2023) / "compact-0001.parquet"
    spans = pq.ParquetFile(file).schema_arrow.metadata[b"baseballpy.chunks"]
    assert manifest_key("b", 2023).encode() in spans


def test_the_compact_command_reports_and_merges(
    lake: LakeConfig, spec: DatasetSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    result = CliRunner().invoke(main, ["compact", "--source", "statcast", "--dataset", "pitches"])
    assert result.exit_code == 0, result.output
    assert "merged 3 chunks" in result.output
    assert _files(lake, spec, 2023) == ["compact-0001.parquet"]


def test_chunks_with_different_category_values_are_compacted_and_read_back_right(
    tmp_path: Path, spec: DatasetSpec
) -> None:
    """Category columns carry a dictionary per chunk; compaction must not call that a difference."""
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    kind = spec.schema.field("pitch_type").type
    for chunk, values in (("a", ["FF", "SL"]), ("b", ["CH", "FF"]), ("c", ["KC"])):
        table = _pitches([90.0] * len(values), 2023)
        column = pa.array(values).dictionary_encode().cast(kind)
        store.put(
            spec,
            table.set_column(table.schema.get_field_index("pitch_type"), "pitch_type", column),
            chunk_id=chunk,
            season=2023,
        )
    assert compact_dataset(spec, cfg).groups == 1
    kinds = sorted(bp.read("statcast.pitches", seasons=2023, config=cfg)["pitch_type"].to_list())
    assert kinds == ["CH", "FF", "FF", "KC", "SL"]
    assert store.read_part(spec, "b", 2023)["pitch_type"].to_pylist() == ["CH", "FF"]


def test_empty_chunk_files_are_removed_and_the_chunk_still_counts_as_downloaded(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    store = ProcessedStore(lake)
    store.put(
        spec, spec.schema.empty_table(), chunk_id="none", season=2023, metadata={"empty": True}
    )
    assert store.part_path(spec, "none", 2023).exists()
    dry = compact_dataset(spec, lake, dry_run=True)
    assert dry.empty_files == 1 and store.part_path(spec, "none", 2023).exists()
    assert compact_dataset(spec, lake).empty_files == 1
    assert not store.part_path(spec, "none", 2023).exists()
    assert store.is_cached(spec, "none", 2023) and store.has_part(spec, "none", 2023)
    assert store.read_part(spec, "none", 2023).num_rows == 0
    assert bp.read("statcast.pitches", seasons=2023, config=lake).height == 6


def test_coverage_and_the_duplicate_check_still_see_a_compacted_season(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    from baseballpy.coverage import check_statcast_pitches

    cache = lake.http_cache_root / "mlb-seasons"
    cache.mkdir(parents=True)
    (cache / "2023.json").write_text(
        '{"springStartDate": "2023-03-01", "postSeasonEndDate": "2023-03-15"}', encoding="utf-8"
    )
    before = check_statcast_pitches(2023, lake)
    compact_dataset(spec, lake)
    after = check_statcast_pitches(2023, lake)
    assert before.held_count == after.held_count == 3
    assert after.expected_count == before.expected_count == 4 and after.missing_count == 1
    assert len(list(lake.processed_dir("statcast", "pitches", 2023).glob("*.parquet"))) == 1
