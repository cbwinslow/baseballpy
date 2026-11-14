"""Tests for Retrosheet data quality check and parent lookup with compacted chunks (Task B-424).

Verifies that:
1. Compacted roster chunks are found by _parent("retrosheet.rosters", year).
2. Compacted data chunks with quality issues have findings written to the manifest by _quality_check.
3. Chunks recorded with rows whose part file was deleted and not compacted raise StoredChunkMissingError.
4. Compacted Chadwick register chunks are loaded by _parent("chadwick.register", year).
"""

from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore, StoredChunkMissingError
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet.api import RetrosheetSource


def _rosters_table(player_ids: list[str], year: int) -> pa.Table:
    """Build a valid Retrosheet roster table containing the given player IDs."""
    schema = get_dataset("retrosheet", "rosters").schema
    n = len(player_ids)
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["player_id"] = pa.array(player_ids, schema.field("player_id").type)
    columns["year"] = pa.array([year] * n, schema.field("year").type)
    columns["roster"] = pa.array(["BOS"] * n, schema.field("roster").type)
    return pa.table(columns, schema=schema)


def _events_table(
    game_events: list[tuple[str, int, str | None, str | None]],
) -> pa.Table:
    """Build a valid Retrosheet events table from (GAME_ID, EVENT_ID, BAT_ID, PIT_ID) tuples."""
    schema = get_dataset("retrosheet", "events").schema
    n = len(game_events)
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["GAME_ID"] = pa.array([g[0] for g in game_events], schema.field("GAME_ID").type)
    columns["EVENT_ID"] = pa.array([g[1] for g in game_events], schema.field("EVENT_ID").type)
    columns["BAT_ID"] = pa.array([g[2] for g in game_events], schema.field("BAT_ID").type)
    columns["PIT_ID"] = pa.array([g[3] for g in game_events], schema.field("PIT_ID").type)
    return pa.table(columns, schema=schema)


def _register_table(retro_ids: list[str]) -> pa.Table:
    """Build a valid Chadwick register table containing key_retro IDs."""
    schema = get_dataset("chadwick", "register").schema
    n = len(retro_ids)
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["key_person"] = pa.array(
        [f"person_{i}" for i in range(n)], schema.field("key_person").type
    )
    columns["key_retro"] = pa.array(retro_ids, schema.field("key_retro").type)
    return pa.table(columns, schema=schema)


def test_roster_chunk_stored_then_compacted_returns_player_ids(tmp_path: Path) -> None:
    """Case (a): _parent('retrosheet.rosters', year) returns player_id values when compacted."""
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec = get_dataset("retrosheet", "rosters")

    # Store multiple chunks so compact_dataset merges them
    t1 = _rosters_table(["player01", "player02"], 2024)
    t2 = _rosters_table(["player03"], 2024)
    store.put(spec, t1, chunk_id="rosters_2024", season=2024)
    store.put(spec, t2, chunk_id="rosters_2024_extra", season=2024)

    # Compact the dataset
    compact_dataset(spec, cfg)

    # Verify part file is gone and chunk is compacted
    part = store.part_path(spec, "rosters_2024", 2024)
    assert not part.exists()
    assert store.has_part(spec, "rosters_2024", 2024)

    source = RetrosheetSource(cache_config=cfg)
    parent = source._parent("retrosheet.rosters", 2024)
    assert parent is not None
    assert set(parent.column("player_id").to_pylist()) == {"player01", "player02"}


def test_compacted_data_chunk_writes_quality_findings(tmp_path: Path) -> None:
    """Case (b): _quality_check writes findings to manifest for compacted chunks."""
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec_events = get_dataset("retrosheet", "events")
    spec_rosters = get_dataset("retrosheet", "rosters")

    # Parent rosters has player01
    store.put(
        spec_rosters,
        _rosters_table(["player01"], 2024),
        chunk_id="rosters_2024",
        season=2024,
    )
    store.put(
        spec_rosters,
        _rosters_table(["player02"], 2024),
        chunk_id="rosters_2024_b",
        season=2024,
    )
    compact_dataset(spec_rosters, cfg)

    # Events chunk has a duplicate key ("g1", 1) and an orphan BAT_ID ("orphan01")
    e1 = _events_table(
        [
            ("g1", 1, "orphan01", "player01"),
            ("g1", 1, "player01", "player01"),
        ]
    )
    e2 = _events_table([("g2", 1, "player01", "player01")])
    store.put(spec_events, e1, chunk_id="events", season=2024)
    store.put(spec_events, e2, chunk_id="events_b", season=2024)
    compact_dataset(spec_events, cfg)

    # Part file is gone
    assert not store.part_path(spec_events, "events", 2024).exists()
    assert store.has_part(spec_events, "events", 2024)

    source = RetrosheetSource(cache_config=cfg)
    source._quality_check(2024, ["events"])

    manifest = cfg.dataset_manifest("retrosheet", "events", "processed")
    entry = manifest.get_chunk("season=2024/events")
    assert entry is not None
    assert entry.get("quality") == {
        "duplicate_key_rows": 1,
        "orphan_rows:BAT_ID->retrosheet.rosters": 1,
    }


def test_chunk_recorded_with_rows_deleted_raises_missing_error(tmp_path: Path) -> None:
    """Case (c): chunk recorded with rows whose part file was deleted raises StoredChunkMissingError."""
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec_events = get_dataset("retrosheet", "events")
    spec_rosters = get_dataset("retrosheet", "rosters")

    # Put a chunk with rows
    store.put(
        spec_events,
        _events_table([("g1", 1, "p1", "p1")]),
        chunk_id="events",
        season=2024,
    )
    part = store.part_path(spec_events, "events", 2024)
    assert part.exists()
    # Delete the part file without compacting
    part.unlink()

    source = RetrosheetSource(cache_config=cfg)
    with pytest.raises(StoredChunkMissingError):
        source._quality_check(2024, ["events"])

    # Also test _parent with a missing roster chunk
    store.put(
        spec_rosters,
        _rosters_table(["p1"], 2024),
        chunk_id="rosters_2024",
        season=2024,
    )
    roster_part = store.part_path(spec_rosters, "rosters_2024", 2024)
    assert roster_part.exists()
    roster_part.unlink()

    with pytest.raises(StoredChunkMissingError):
        source._parent("retrosheet.rosters", 2024)


def test_compacted_register_parent_lookup(tmp_path: Path) -> None:
    """Chadwick register parent lookup reads compacted register chunks."""
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec_reg = get_dataset("chadwick", "register")

    store.put(spec_reg, _register_table(["retro1", "retro2"]), chunk_id="people-a")
    store.put(spec_reg, _register_table(["retro3"]), chunk_id="people-b")
    compact_dataset(spec_reg, cfg)

    source = RetrosheetSource(cache_config=cfg)
    parent = source._parent("chadwick.register", 2024)
    assert parent is not None
    assert set(parent.column("key_retro").to_pylist()) == {"retro1", "retro2", "retro3"}
