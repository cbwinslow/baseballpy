"""Cache decisions go through the store: a compacted chunk is stored, a lost one is not (B-409).

A source that tests for ``part-*.parquet`` by name downloads a compacted season again on every run and
cannot read its own cache; the same user would get different behaviour once they had compacted.
"""

import json
from datetime import date
from pathlib import Path

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import respx
from test_statcast_pitches import _by_window

from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog
from baseballpy.sources.statcast.extractor import (
    MLB_SEASONS_URL,
    SAVANT_BASE_URL,
    StatcastExtractor,
)


def _mount_season(tmp_path: Path) -> tuple[LakeConfig, StatcastExtractor, respx.Route]:
    lake = LakeConfig(home=tmp_path, today=date(2026, 1, 1))
    extractor = StatcastExtractor(cache_config=lake, chunk_days=5)
    respx.get(MLB_SEASONS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [{"springStartDate": "2024-06-01", "postSeasonEndDate": "2024-06-12"}]
            },
        )
    )
    route = respx.get(SAVANT_BASE_URL).mock(side_effect=_by_window)
    return lake, extractor, route


@respx.mock
def test_a_compacted_statcast_season_is_served_from_the_lake(tmp_path: Path) -> None:
    catalog.register_all()
    lake, extractor, route = _mount_season(tmp_path)
    first = extractor.ingest_season(2024)
    assert (first.chunks, first.rows, route.call_count) == (3, 15, 3)
    report = compact_dataset(get_dataset("statcast", "pitches"), lake)
    assert report.chunks == 3  # the three part files are now one compacted file
    again = extractor.ingest_season(2024)
    assert again.cached_chunks == 3 and again.rows == first.rows
    assert route.call_count == 3, "a compacted season must not be downloaded again"


@respx.mock
def test_a_lost_compacted_file_makes_the_windows_download_again(tmp_path: Path) -> None:
    catalog.register_all()
    lake, extractor, route = _mount_season(tmp_path)
    first = extractor.ingest_season(2024)
    compact_dataset(get_dataset("statcast", "pitches"), lake)
    folder = lake.processed_dir("statcast", "pitches", 2024)
    for compacted in folder.glob("compact-*.parquet"):
        compacted.unlink()
    again = extractor.ingest_season(2024)
    assert again.cached_chunks == 0 and route.call_count == 6
    assert again.rows == first.rows
    assert len(list(folder.glob("part-*.parquet"))) == 3


def test_a_chunk_its_compacted_file_lacks_is_not_cached(tmp_path: Path) -> None:
    catalog.register_all()
    spec = get_dataset("statcast", "pitches")
    lake = LakeConfig(home=tmp_path)
    store = ProcessedStore(lake)
    schema = spec.schema
    for chunk, speed in (("a", 90.0), ("b", 91.0)):
        columns = {f.name: pa.nulls(1, f.type) for f in schema}
        columns["release_speed"] = pa.array([speed], schema.field("release_speed").type)
        columns["game_year"] = pa.array([2023], schema.field("game_year").type)
        store.put(spec, pa.table(columns, schema=schema), chunk_id=chunk, season=2023)
    compact_dataset(spec, lake)
    assert store.is_cached(spec, "a", 2023) and store.is_cached(spec, "b", 2023)
    # the file keeps its name but its footer no longer lists chunk "b" (the 2019 damage)
    folder = lake.processed_dir("statcast", "pitches", 2023)
    (compacted,) = folder.glob("compact-*.parquet")
    table = pq.read_table(compacted)
    metadata = dict(table.schema.metadata or {})
    chunks = json.loads(metadata[b"baseballpy.chunks"])
    chunks.pop("season=2023/part-b.parquet", None)
    chunks.pop("season=2023/b", None)
    metadata[b"baseballpy.chunks"] = json.dumps(chunks).encode()
    pq.write_table(table.replace_schema_metadata(metadata), compacted)
    assert store.is_cached(spec, "a", 2023)
    assert not store.is_cached(spec, "b", 2023)
