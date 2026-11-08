"""A schema that gained typed columns: old files are read, migrated and lose nothing (ADR 87)."""

import json
from dataclasses import replace
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import baseballpy as bp
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.evolve import migrate_dataset, promote_extras
from baseballpy.core.schema_tools import EXTRAS
from baseballpy.core.stores import ProcessedStore, spec_fingerprint
from baseballpy.sources import catalog

SLUG = "player_name_slug"
KEY = "player.nameSlug"


@pytest.fixture
def spec() -> DatasetSpec:
    catalog.register_all()
    return get_dataset("mlb_api", "award_recipients")


def _full(spec: DatasetSpec, n: int, *, slug: bool, season: int) -> pa.Table:
    """``n`` rows in the registered schema; the slug is a typed value or sits in ``_extras``."""
    schema = spec.schema
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["season"] = pa.array([season] * n).cast(schema.field("season").type)
    names = [f"person-{season}-{i}" for i in range(n)]
    if slug:
        columns[SLUG] = pa.array(names, pa.string())
    else:
        columns[EXTRAS] = pa.array([json.dumps({KEY: s, "other": 1}) for s in names], pa.string())
    return pa.table(columns, schema=schema)


def _old(table: pa.Table) -> pa.Table:
    """What a file written before the schema gained the slug column looks like."""
    return table.drop_columns([SLUG])


def test_promote_moves_the_value_out_of_extras(spec: DatasetSpec) -> None:
    old = _old(_full(spec, 3, slug=False, season=2008))
    counts: dict[str, int] = {}
    new = promote_extras(old, spec.schema, source="mlb_api", dataset=spec.name, counts=counts)
    assert new.schema.equals(spec.schema, check_metadata=False)
    assert new[SLUG].to_pylist() == ["person-2008-0", "person-2008-1", "person-2008-2"]
    assert [json.loads(x) for x in new[EXTRAS].to_pylist()] == [{"other": 1}] * 3  # key moved
    assert counts == {SLUG: 3}


def test_promote_without_a_value_leaves_the_column_empty_and_extras_alone(
    spec: DatasetSpec,
) -> None:
    table = _full(spec, 2, slug=False, season=2008)
    table = table.set_column(
        table.schema.get_field_index(EXTRAS), EXTRAS, pa.array([None, '{"x":1}'], pa.string())
    )
    new = promote_extras(_old(table), spec.schema, source="mlb_api", dataset=spec.name)
    assert new[SLUG].to_pylist() == [None, None]
    assert new[EXTRAS].to_pylist() == [None, '{"x":1}']


def test_promote_emptied_extras_become_null(spec: DatasetSpec) -> None:
    table = _full(spec, 1, slug=False, season=2008)
    table = table.set_column(
        table.schema.get_field_index(EXTRAS), EXTRAS, pa.array([json.dumps({KEY: "a"})])
    )
    new = promote_extras(_old(table), spec.schema, source="mlb_api", dataset=spec.name)
    assert new[SLUG].to_pylist() == ["a"] and new[EXTRAS].to_pylist() == [None]


@pytest.fixture
def lake(tmp_path: Path, spec: DatasetSpec) -> LakeConfig:
    """Season 2008 written before the slug column existed (old file, old fingerprint), 2025 after."""
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    store.put(spec, _full(spec, 3, slug=False, season=2008), chunk_id="a", season=2008)
    store.put(spec, _full(spec, 2, slug=True, season=2025), chunk_id="b", season=2025)
    old_path = store.part_path(spec, "a", 2008)
    pq.write_table(_old(pq.read_table(old_path)), old_path)
    older = replace(spec, schema=pq.read_schema(old_path))
    manifest = cfg.dataset_manifest(spec.source, spec.name, "processed")
    for key, entry in manifest.chunks().items():
        if key.startswith("season=2008"):
            manifest.put_entry(key, {**entry, "schema_sha256": spec_fingerprint(older)})
    return cfg


def test_read_survives_old_and_new_files(spec: DatasetSpec, lake: LakeConfig) -> None:
    frame = bp.read("mlb_api.award_recipients", config=lake).sort("season", SLUG)
    assert frame.height == 5
    assert frame[SLUG].to_list() == [None, None, None, "person-2025-0", "person-2025-1"]
    assert bp.read("mlb_api.award_recipients", config=lake, lazy=True).collect().height == 5


def test_migration_fills_old_rows_and_certifies_the_chunk(
    spec: DatasetSpec, lake: LakeConfig
) -> None:
    dry = migrate_dataset(spec, lake, dry_run=True)
    assert (dry.files_checked, dry.files_rewritten) == (2, 1)
    assert (
        pq.read_schema(ProcessedStore(lake).part_path(spec, "a", 2008)).names != spec.schema.names
    )

    report = migrate_dataset(spec, lake)
    assert (report.files_rewritten, report.rows, report.promoted, report.failed) == (
        1,
        3,
        {SLUG: 3},
        [],
    )
    frame = bp.read("mlb_api.award_recipients", config=lake).sort("season", SLUG)
    assert frame[SLUG].to_list() == [
        "person-2008-0",
        "person-2008-1",
        "person-2008-2",
        "person-2025-0",
        "person-2025-1",
    ]
    manifest = lake.dataset_manifest(spec.source, spec.name, "processed")
    entry = next(e for k, e in manifest.chunks().items() if k.startswith("season=2008"))
    assert entry["schema_sha256"] == spec_fingerprint(spec)
    assert migrate_dataset(spec, lake).files_rewritten == 0  # nothing left to do
    assert isinstance(frame, pl.DataFrame)


def test_a_file_with_an_unknown_column_is_left_alone_and_reported(
    spec: DatasetSpec, lake: LakeConfig
) -> None:
    path = ProcessedStore(lake).part_path(spec, "a", 2008)
    table = pq.read_table(path).append_column("surprise", pa.array([1, 2, 3]))
    pq.write_table(table, path)
    report = migrate_dataset(spec, lake)
    assert report.files_rewritten == 0 and len(report.failed) == 1
    assert "surprise" in pq.read_schema(path).names  # not touched, nothing dropped


def test_a_chunk_that_was_stale_for_another_reason_is_not_certified(
    spec: DatasetSpec, lake: LakeConfig
) -> None:
    manifest = lake.dataset_manifest(spec.source, spec.name, "processed")
    key = next(k for k in manifest.chunks() if k.startswith("season=2008"))
    manifest.put_entry(key, {**manifest.chunks()[key], "schema_sha256": "some-other-parser"})
    assert migrate_dataset(spec, lake).files_rewritten == 1  # the columns are fixed ...
    assert manifest.chunks()[key]["schema_sha256"] == "some-other-parser"  # ... but still stale


def test_a_compacted_file_keeps_its_chunk_map_after_migration(
    tmp_path: Path, spec: DatasetSpec
) -> None:
    from baseballpy.core.compacted import INTO, chunk_map, read_chunk, write_compacted

    cfg = LakeConfig(home=tmp_path)
    root = cfg.processed_dir(spec.source, spec.name)
    folder = cfg.processed_dir(spec.source, spec.name, 2008)
    folder.mkdir(parents=True)
    first = _old(_full(spec, 2, slug=False, season=2008))
    second = _old(_full(spec, 3, slug=False, season=2008))
    path = folder / "compact-0001.parquet"
    write_compacted(path, first.schema, [("season=2008/a", first), ("season=2008/b", second)])
    manifest = cfg.dataset_manifest(spec.source, spec.name, "processed")
    manifest.put_entries(
        {
            key: {
                "status": "COMPLETED",
                "records_count": rows,
                INTO: path.relative_to(root).as_posix(),
            }
            for key, rows in (("season=2008/a", 2), ("season=2008/b", 3))
        }
    )
    report = migrate_dataset(spec, cfg)
    assert (report.files_rewritten, report.rows, report.failed) == (1, 5, [])
    assert chunk_map(path) == {"season=2008/a": (0, 2), "season=2008/b": (2, 3)}
    entry = manifest.chunks()["season=2008/b"]
    assert read_chunk(root, entry, "season=2008/b")[SLUG].to_pylist() == [
        f"person-2008-{i}" for i in range(3)
    ]
    assert pq.read_schema(path).equals(spec.schema, check_metadata=False)


def test_sync_warns_when_a_view_would_hide_columns(
    spec: DatasetSpec, lake: LakeConfig, caplog: pytest.LogCaptureFixture
) -> None:
    from baseballpy.database import BaseballDatabase

    db = BaseballDatabase(db_path=lake.database_path, cache_config=lake)
    with caplog.at_level("WARNING"):
        db.sync_views()
    assert any("baseballpy compact" in r.message for r in caplog.records)
    migrate_dataset(spec, lake)
    caplog.clear()
    with caplog.at_level("WARNING"):
        db.sync_views()
    assert not any("mlb_award_recipients" in r.message for r in caplog.records)


def test_compact_rewrites_old_files_first(spec: DatasetSpec, lake: LakeConfig) -> None:
    from baseballpy.core.compact import compact_dataset

    assert compact_dataset(spec, lake, dry_run=True).migrated_files == 1
    report = compact_dataset(spec, lake)
    assert (report.migrated_files, report.migrate_failed) == (1, 0)
    slugs = bp.read("mlb_api.award_recipients", config=lake)[SLUG]
    assert slugs.null_count() == 0
