"""The lineage column ``_raw_sha256``: old files stay valid and readable, segment files are recognised."""

import json
from collections.abc import Generator
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import LINEAGE_COLUMN, DatasetSpec, with_lineage
from baseballpy.core.hostlock import release_all
from baseballpy.core.responselog import Response
from baseballpy.core.segments import DatasetRows, SegmentWriter
from baseballpy.core.stores import (
    schema_fingerprint,
    schema_matches,
    segment_fingerprint,
    segment_matches,
    spec_fingerprint,
)
from baseballpy.frames import scan_dataset

SCHEMA = pa.schema([("game_id", pa.string()), ("seq", pa.int32())])


def _spec(schema: pa.Schema = SCHEMA, revision: int = 0) -> DatasetSpec:
    return DatasetSpec(
        source="mlb_api",
        name="plays_test",
        view="mlb_plays_test",
        schema=schema,
        partition="none",
        keys=("game_id", "seq"),
        description="test",
        endpoint_doc="",
        revision=revision,
    )


@pytest.fixture(autouse=True)
def _free_locks() -> Generator[None, None, None]:
    yield
    release_all()


def test_the_lineage_column_changes_no_digest_a_chunk_was_stored_with() -> None:
    spec = _spec()
    assert spec_fingerprint(spec) == schema_fingerprint(SCHEMA), "the same digest as before"
    assert schema_matches(spec, {"schema_sha256": schema_fingerprint(SCHEMA)})
    assert spec.schema.names == ["game_id", "seq"], "the registered schema is not touched"
    assert segment_fingerprint(spec) != spec_fingerprint(spec)
    assert with_lineage(with_lineage(SCHEMA)) == with_lineage(SCHEMA), (
        "adding it twice adds nothing"
    )
    assert with_lineage(SCHEMA).names == ["game_id", "seq", LINEAGE_COLUMN]


def test_a_segment_file_carries_the_segment_fingerprint_and_a_schema_change_is_seen(
    tmp_path: Path,
) -> None:
    config = LakeConfig(home=tmp_path)

    def normalize(unit_id: str, responses: object) -> dict[str, DatasetRows]:
        table = pa.table({"game_id": [unit_id], "seq": pa.array([1], pa.int32())})
        return {"plays_test": DatasetRows(table, "sha")}

    writer = SegmentWriter(config, "mlb_api", None, normalize)
    writer.add_unit("g1", [Response("https://x/1", b"{}", "2026-11-08T00:00:00+00:00")])
    writer.commit()
    line = (config.raw_root / "mlb_api" / "segments.json").read_text(encoding="utf-8")
    stored = json.loads(line)["datasets"]["plays_test"]["schema_sha256"]
    assert segment_matches(_spec(), stored)
    changed = _spec(SCHEMA.append(pa.field("outs", pa.int8())))
    assert not segment_matches(changed, stored), "a new column makes the segment stale"
    assert not segment_matches(_spec(), None)


def _write(folder: Path, name: str, table: pa.Table) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, folder / name)


def test_old_parts_and_segment_files_are_read_together_and_old_rows_have_no_lineage(
    tmp_path: Path,
) -> None:
    old = pa.table({"game_id": ["old"], "seq": pa.array([1], pa.int32())})
    new = pa.table({"game_id": ["new"], "seq": pa.array([2], pa.int32()), LINEAGE_COLUMN: ["abc"]})
    _write(tmp_path, "part-1.parquet", old)
    _write(tmp_path, "seg-0001.parquet", new)
    frame = scan_dataset(_spec(), tmp_path).collect().sort("game_id")
    assert frame.columns == ["game_id", "seq", LINEAGE_COLUMN]
    assert dict(zip(frame["game_id"], frame[LINEAGE_COLUMN], strict=True)) == {
        "old": None,
        "new": "abc",
    }


def test_a_dataset_without_segment_files_comes_back_exactly_as_registered(tmp_path: Path) -> None:
    _write(
        tmp_path, "part-1.parquet", pa.table({"game_id": ["a"], "seq": pa.array([1], pa.int32())})
    )
    assert scan_dataset(_spec(), tmp_path).collect().columns == ["game_id", "seq"]


def test_a_column_the_schema_does_not_have_is_still_an_error(tmp_path: Path) -> None:
    table = pa.table(
        {
            "game_id": ["a"],
            "seq": pa.array([1], pa.int32()),
            "surprise": [1],
            LINEAGE_COLUMN: ["abc"],
        }
    )
    _write(tmp_path, "seg-0001.parquet", table)
    with pytest.raises(pl.exceptions.PolarsError):
        scan_dataset(_spec(), tmp_path).collect()


def test_migration_and_compaction_never_rewrite_a_segment_file(tmp_path: Path) -> None:
    """A segment file is named by a commit line (its sha256): rewriting it would break the check."""
    from baseballpy.core.compact import compact_dataset
    from baseballpy.core.datasets import get_dataset
    from baseballpy.core.evolve import migrate_dataset
    from baseballpy.sources import catalog

    catalog.register_all()
    config = LakeConfig(home=tmp_path)
    spec = get_dataset("mlb_api", "game_linescore")
    folder = config.processed_dir("mlb_api", "game_linescore", 2024)
    folder.mkdir(parents=True)
    table = spec.schema.empty_table()
    seg = folder / "seg-0001.parquet"
    pq.write_table(
        with_lineage(spec.schema).empty_table(), seg
    )  # the extra column is what a migration would call "different"
    before = seg.read_bytes()

    report = migrate_dataset(spec, config)
    compact_dataset(spec, config, migrate=True)
    assert seg.read_bytes() == before
    assert report.files_rewritten == 0 and table.num_rows == 0
