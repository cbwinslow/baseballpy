"""Compaction is deterministic (B-411): the same chunks give the same files and the same rows.

AGENTS.md section 15: the same inputs must give the same outputs for every user. Two users who download
the same chunks in a different order, or compact at different times, must end with the same data.
"""

import hashlib
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog

CHUNKS = {"a": [90.0, 91.0], "b": [92.0], "c": [93.0, 94.0, 95.0], "d": [96.0]}


@pytest.fixture
def spec() -> DatasetSpec:
    catalog.register_all()
    return get_dataset("statcast", "pitches")


def _table(spec: DatasetSpec, speeds: list[float]) -> pa.Table:
    schema = spec.schema
    columns = {f.name: pa.nulls(len(speeds), f.type) for f in schema}
    columns["release_speed"] = pa.array(speeds, schema.field("release_speed").type)
    columns["game_year"] = pa.array([2023] * len(speeds), schema.field("game_year").type)
    return pa.table(columns, schema=schema)


def _lake(tmp_path: Path, name: str) -> LakeConfig:
    return LakeConfig(home=tmp_path / name)


def _put(spec: DatasetSpec, cfg: LakeConfig, chunks: list[str]) -> None:
    store = ProcessedStore(cfg)
    for chunk in chunks:
        store.put(spec, _table(spec, CHUNKS[chunk]), chunk_id=chunk, season=2023)


def _digests(spec: DatasetSpec, cfg: LakeConfig) -> dict[str, str]:
    folder = cfg.processed_dir(spec.source, spec.name, 2023)
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.glob("*.parquet"))
    }


def _speeds(spec: DatasetSpec, cfg: LakeConfig) -> list[float]:
    store = ProcessedStore(cfg)
    return sorted(store.read(spec, season=2023)["release_speed"].to_pylist())


def test_the_same_chunks_give_byte_identical_files_whatever_the_download_order(
    tmp_path: Path, spec: DatasetSpec
) -> None:
    one, two = _lake(tmp_path, "one"), _lake(tmp_path, "two")
    _put(spec, one, ["a", "b", "c", "d"])
    _put(spec, two, ["d", "c", "b", "a"])  # downloaded in another order (another thread timing)
    compact_dataset(spec, one)
    compact_dataset(spec, two)
    assert _digests(spec, one) == _digests(spec, two)
    assert list(_digests(spec, one)) == ["compact-0001.parquet"]


def test_a_rerun_rewrites_nothing(tmp_path: Path, spec: DatasetSpec) -> None:
    cfg = _lake(tmp_path, "lake")
    _put(spec, cfg, ["a", "b", "c", "d"])
    compact_dataset(spec, cfg)
    before = _digests(spec, cfg)
    report = compact_dataset(spec, cfg)
    assert report.chunks == 0 and _digests(spec, cfg) == before


def test_compacting_at_different_times_gives_the_same_rows(
    tmp_path: Path, spec: DatasetSpec
) -> None:
    """The file grouping depends on when compaction ran; the data a user queries does not."""
    once, staged = _lake(tmp_path, "once"), _lake(tmp_path, "staged")
    _put(spec, once, ["a", "b", "c", "d"])
    compact_dataset(spec, once)
    _put(spec, staged, ["a", "b"])
    compact_dataset(spec, staged)
    _put(spec, staged, ["c", "d"])
    compact_dataset(spec, staged)
    assert (
        _speeds(spec, once) == _speeds(spec, staged) == [90.0, 91.0, 92.0, 93.0, 94.0, 95.0, 96.0]
    )
