"""DuckDB views and ``read`` over segment files: visible at once, and ``_open``/``_legacy`` never read.

Written first (task 4.1, B-367); task 4.3 (B-369) made the listing follow the rule below and these pass.

The listing rule fixed here (design section 2): a season-split dataset is read from
``season=*/*.parquet`` (one folder level), an unsplit one from ``*.parquet``; the files may be
``part-*``, ``compact-*`` or ``seg-*``; folders starting with an underscore (``_open``, ``_legacy``)
and files ending in ``.part`` are never read.
"""

import json
import shutil
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.access import read
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.hostlock import release_all
from baseballpy.core.responselog import Response
from baseballpy.core.segments import DatasetRows, SegmentWriter
from baseballpy.database import BaseballDatabase
from baseballpy.sources import catalog
from baseballpy.sources.mlb_api.endpoints import BY_NAME
from baseballpy.sources.mlb_api.generic import MlbRecordNormalizer

FIXTURES = Path(__file__).parent / "fixtures" / "mlb"
SEASON = 2024
DATASET = "game_linescore"
VIEW = "mlb_game_linescore"


@pytest.fixture(autouse=True)
def _free_locks() -> Generator[None, None, None]:
    yield
    release_all()


def _normalize(unit_id: str, responses: object) -> dict[str, DatasetRows]:
    payload = json.loads((FIXTURES / "game_linescore.json").read_text(encoding="utf-8"))
    table = MlbRecordNormalizer().normalize(
        BY_NAME[DATASET], payload, extra={"game_pk": int(unit_id)}
    )
    return {DATASET: DatasetRows(table, "0" * 64)}


def _commit(config: LakeConfig, games: list[str]) -> int:
    writer = SegmentWriter(config, "mlb_api", SEASON, _normalize)
    for game in games:
        writer.add_unit(game, [Response(f"https://x/{game}", b"{}", "2026-11-08T00:00:00+00:00")])
    segment = writer.commit()
    release_all()
    assert segment is not None
    return segment


def _dataset_dir(config: LakeConfig) -> Path:
    return config.processed_dir("mlb_api", DATASET, SEASON)


def _count_view(con: Any) -> int:
    return int(con.execute(f"SELECT count(*) FROM {VIEW}").fetchone()[0])  # noqa: S608 - a constant view name


def _count_read(config: LakeConfig) -> int:
    return int(read(f"mlb_api.{DATASET}", backend="pyarrow", config=config).num_rows)


def test_views_and_read_see_a_segment_as_soon_as_it_commits(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    catalog.register_all()
    config = LakeConfig(home=tmp_path)
    _commit(config, ["745000", "745001"])
    per_game = _count_read(config) // 2
    assert per_game > 0

    database = BaseballDatabase(db_path=tmp_path / "views.duckdb", cache_config=config)
    con = database.connect()
    assert "differs from the registered schema" not in caplog.text, "a segment is not an odd file"
    assert _count_view(con) == 2 * per_game

    _commit(config, ["745002"])  # a second segment, no `db sync`, the same open connection
    assert _count_view(con) == 3 * per_game
    assert _count_read(config) == 3 * per_game
    assert sorted(p.name for p in _dataset_dir(config).glob("seg-*.parquet")) == [
        "seg-0001.parquet",
        "seg-0002.parquet",
    ]
    con.close()


def test_open_and_legacy_folders_are_never_read(tmp_path: Path) -> None:
    catalog.register_all()
    config = LakeConfig(home=tmp_path)
    _commit(config, ["745000"])
    per_game = _count_read(config)
    folder = _dataset_dir(config)
    segment = next(folder.glob("seg-*.parquet"))

    # copies of a committed file in the places that must stay invisible
    for hidden in ("_open", "_legacy"):
        (folder / hidden).mkdir(exist_ok=True)
        shutil.copy(segment, folder / hidden / "seg-0009.parquet")
    shutil.copy(segment, folder / "seg-0007.parquet.part")
    table = pq.read_table(segment)
    pq.write_table(pa.concat_tables([table, table]), folder / "_legacy" / "compact-0001.parquet")

    con = BaseballDatabase(db_path=":memory:", cache_config=config).connect()
    assert _count_view(con) == per_game, "the view reads only the committed files"
    assert _count_read(config) == per_game, "so does read()"
    spec = get_dataset("mlb_api", DATASET)
    assert spec.partition == "season"
    con.close()


def test_old_parts_and_segments_in_one_view_merge_by_column_name_without_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from baseballpy.core.stores import ProcessedStore

    catalog.register_all()
    config = LakeConfig(home=tmp_path)
    spec = get_dataset("mlb_api", DATASET)
    payload = json.loads((FIXTURES / "game_linescore.json").read_text(encoding="utf-8"))
    old = MlbRecordNormalizer().normalize(BY_NAME[DATASET], payload, extra={"game_pk": 745000})
    ProcessedStore(config).put(spec, old, chunk_id="game_linescore_745000", season=SEASON)
    _commit(config, ["745001"])

    con = BaseballDatabase(db_path=":memory:", cache_config=config).connect()
    assert "differs from the registered schema" not in caplog.text
    assert _count_view(con) == old.num_rows * 2
    nulls = con.execute(f"SELECT count(*) FROM {VIEW} WHERE _raw_sha256 IS NULL").fetchone()  # noqa: S608
    assert nulls is not None and nulls[0] == old.num_rows, "the old rows have no lineage"
    con.close()


def test_a_commit_leaves_no_empty_open_folder_in_a_dataset(tmp_path: Path) -> None:
    config = LakeConfig(home=tmp_path)
    _commit(config, ["745000"])
    assert not (_dataset_dir(config) / "_open").exists()
