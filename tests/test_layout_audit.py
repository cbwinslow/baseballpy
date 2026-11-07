"""Layout audit: finds what would make the lake slow or damaged, changes nothing."""

import json
import shutil
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.layout_audit import LayoutKind, audit_layout
from baseballpy.sources import catalog


def _pitches(speeds: list[float], year: int) -> pa.Table:
    schema = get_dataset("statcast", "pitches").schema
    n = len(speeds)
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["release_speed"] = pa.array(speeds, schema.field("release_speed").type)
    columns["game_year"] = pa.array([year] * n, schema.field("game_year").type)
    return pa.table(columns, schema=schema)


@pytest.fixture
def spec() -> DatasetSpec:
    catalog.register_all()
    return get_dataset("statcast", "pitches")


@pytest.fixture
def lake(tmp_path: Path, spec: DatasetSpec) -> LakeConfig:
    return LakeConfig(home=tmp_path)


def _kinds(lake: LakeConfig) -> set[LayoutKind]:
    return {f.kind for f in audit_layout(lake, ("statcast",))}


def test_a_clean_lake_has_no_findings(lake: LakeConfig, spec: DatasetSpec) -> None:
    store = ProcessedStore(lake)
    for chunk in "abc":
        store.put(spec, _pitches([90.0], 2023), chunk_id=chunk, season=2023)
    assert audit_layout(lake, ("statcast",)) == []


def test_many_small_files_and_empty_files_are_advised_and_compaction_clears_them(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    store = ProcessedStore(lake)
    for index in range(12):
        store.put(spec, _pitches([90.0 + index], 2023), chunk_id=f"c{index:02d}", season=2023)
    store.put(spec, spec.schema.empty_table(), chunk_id="none", season=2023)
    kinds = _kinds(lake)
    assert {LayoutKind.TINY_FILES, LayoutKind.EMPTY_FILES} <= kinds
    assert not any(f.fails for f in audit_layout(lake, ("statcast",)))
    compact_dataset(spec, lake)
    assert audit_layout(lake, ("statcast",)) == []


def test_a_part_with_other_columns_fails_the_check(lake: LakeConfig, spec: DatasetSpec) -> None:
    store = ProcessedStore(lake)
    path = store.put(spec, _pitches([90.0], 2023), chunk_id="a", season=2023)
    pq.write_table(pa.table({"only": [1]}), path)
    found = [f for f in audit_layout(lake, ("statcast",)) if f.kind is LayoutKind.MIXED_SCHEMA]
    assert found and found[0].fails and "part-a.parquet" in found[0].evidence


def test_a_compacted_file_nobody_points_at_fails_the_check(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    store = ProcessedStore(lake)
    for chunk in "abc":
        store.put(spec, _pitches([90.0], 2023), chunk_id=chunk, season=2023)
    compact_dataset(spec, lake)
    folder = lake.processed_dir(spec.source, spec.name, 2023)
    shutil.copy(folder / "compact-0001.parquet", folder / "compact-0007.parquet")
    found = [f for f in audit_layout(lake, ("statcast",)) if f.kind is LayoutKind.ORPHAN_COMPACT]
    assert len(found) == 1 and "compact-0007" in found[0].evidence and found[0].fails


def test_tiny_row_groups_are_advised(lake: LakeConfig, spec: DatasetSpec) -> None:
    store = ProcessedStore(lake)
    path = store.put(spec, _pitches([90.0] * 40, 2023), chunk_id="a", season=2023)
    pq.write_table(pq.read_table(path), path, row_group_size=10)
    assert LayoutKind.SMALL_ROW_GROUPS in _kinds(lake)


def test_plain_raw_text_files_are_advised(tmp_path: Path) -> None:
    plain = LakeConfig(home=tmp_path, raw_compress_sources=())
    RawStore(plain).put("statcast", "pitches", "1.csv", b"a,b\n" * 50, season=2023)
    packed = LakeConfig(home=tmp_path)
    found = audit_layout(packed, ("statcast",))
    assert [f.kind for f in found] == [LayoutKind.RAW_PLAIN]
    RawStore(packed).put("statcast", "pitches", "1.csv", b"a,b\n" * 50, season=2023)
    assert audit_layout(packed, ("statcast",)) == []


def test_the_layout_command_prints_json_and_sets_the_exit_code(
    lake: LakeConfig, spec: DatasetSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    store = ProcessedStore(lake)
    path = store.put(spec, _pitches([90.0], 2023), chunk_id="a", season=2023)
    ok = CliRunner().invoke(main, ["catalog", "layout", "--source", "statcast"])
    assert ok.exit_code == 0 and "clean" in ok.output
    pq.write_table(pa.table({"only": [1]}), path)
    bad = CliRunner().invoke(main, ["catalog", "layout", "--source", "statcast", "--json"])
    assert bad.exit_code == 1
    assert json.loads(bad.output)[0]["kind"] == "MIXED_SCHEMA"
