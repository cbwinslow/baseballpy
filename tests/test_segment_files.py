"""The open files of a processed segment: bounded row groups, lineage column, no file for no rows."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.responselog import Response
from baseballpy.core.segments import (
    LINEAGE_COLUMN,
    DatasetRows,
    ProcessedSegmentFiles,
    SegmentWriter,
    segment_file_name,
)


def _unit(game: str, plays: int = 3) -> dict[str, DatasetRows]:
    return {
        "plays": DatasetRows(
            pa.table({"game_id": [game] * plays, "seq": list(range(plays))}), f"sha-{game}"
        ),
        "box": DatasetRows(pa.table({"game_id": [game], "runs": [4]}), f"box-{game}"),
        "empty": DatasetRows(pa.table({"game_id": pa.array([], pa.string())}), f"sha-{game}"),
    }


def _files(tmp_path: Path, row_group_units: int = 50) -> ProcessedSegmentFiles:
    return ProcessedSegmentFiles(LakeConfig(home=tmp_path), "mlb_api", 2024, 1, row_group_units)


def test_names_and_paths(tmp_path: Path) -> None:
    files = _files(tmp_path)
    assert segment_file_name(7) == "seg-0007.parquet"
    folder = tmp_path / "processed" / "mlb_api" / "plays" / "season=2024"
    assert files.final_path("plays") == folder / "seg-0001.parquet"
    assert files.part_path("plays") == folder / "_open" / "seg-0001.parquet.part"
    assert not (tmp_path / "processed").exists(), "asking for a path creates nothing"


def test_rows_are_written_in_row_groups_of_the_given_number_of_units(tmp_path: Path) -> None:
    files = _files(tmp_path, row_group_units=50)
    for n in range(120):
        files.add(_unit(str(n)))
    assert files.close() == {"plays": 360, "box": 120}, "a dataset with no rows has no entry"
    plays = pq.ParquetFile(files.part_path("plays"))
    assert [plays.metadata.row_group(i).num_rows for i in range(plays.metadata.num_row_groups)] == [
        150,
        150,
        60,
    ]
    assert not files.part_path("empty").exists()


def test_every_row_carries_the_sha256_of_its_response(tmp_path: Path) -> None:
    files = _files(tmp_path)
    files.add(_unit("a"))
    files.add(_unit("b", plays=2))
    files.close()
    table = pq.read_table(files.part_path("plays"))
    assert table.column_names == ["game_id", "seq", LINEAGE_COLUMN]
    assert table.to_pydict()[LINEAGE_COLUMN] == ["sha-a"] * 3 + ["sha-b"] * 2
    assert pq.read_table(files.part_path("box")).to_pydict()[LINEAGE_COLUMN] == ["box-a", "box-b"]


def test_open_files_are_invisible_to_readers_of_seg_files(tmp_path: Path) -> None:
    files = _files(tmp_path)
    files.add(_unit("a"))
    files.close()
    folder = files.final_path("plays").parent
    assert not list(folder.glob("seg-*.parquet")) and not list(folder.glob("*.parquet"))
    assert files.part_path("plays").exists()


def test_a_table_that_already_has_the_lineage_column_is_refused(tmp_path: Path) -> None:
    files = _files(tmp_path)
    table = pa.table({"game_id": ["a"], LINEAGE_COLUMN: ["x"]})
    with pytest.raises(ValueError, match=LINEAGE_COLUMN):
        files.add({"plays": DatasetRows(table, "sha")})


def test_units_with_different_schemas_are_refused(tmp_path: Path) -> None:
    files = _files(tmp_path)
    files.add({"plays": DatasetRows(pa.table({"game_id": ["a"], "seq": [1]}), "s1")})
    with pytest.raises(pa.ArrowInvalid):
        files.add({"plays": DatasetRows(pa.table({"game_id": ["b"], "seq": ["one"]}), "s2")})
        files.close()


def test_abort_deletes_the_open_files(tmp_path: Path) -> None:
    files = _files(tmp_path, row_group_units=1)
    files.add(_unit("a"))
    assert files.part_path("plays").exists()
    files.abort()
    assert not files.part_path("plays").exists() and not files.part_path("box").exists()


def test_a_writer_parses_before_it_journals_and_numbers_the_segment(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    seen: list[str] = []

    def normalize(unit_id: str, responses: object) -> dict[str, DatasetRows]:
        seen.append(unit_id)
        if unit_id == "bad":
            raise ValueError("cannot parse")
        return _unit(unit_id)

    writer = SegmentWriter(config, "mlb_api", 2024, normalize)
    response = [Response("https://x/1", b"{}", "2026-11-08T00:00:00+00:00")]
    writer.add_unit("ok", response)
    with pytest.raises(ValueError, match="cannot parse"):
        writer.add_unit("bad", response)
    assert writer.stored() == frozenset({"ok"}), "a unit that cannot be parsed is not journalled"
    assert writer.committed_units() == frozenset()
    assert seen == ["ok", "bad"]
