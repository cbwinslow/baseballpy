"""Tests for the dataset registry and the raw/processed stores (lake layout v2)."""

import re
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, SOURCES, DatasetSpec, get_dataset, register
from baseballpy.core.sql import quote_ident
from baseballpy.core.stores import ProcessedStore, RawStore, reprocess
from baseballpy.sources import catalog

DOCS = Path(__file__).parent.parent / "docs"


def _slug(heading: str) -> str:
    """GitHub-style anchor for a Markdown heading."""
    text = heading.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def _anchors(doc: Path) -> set[str]:
    return {
        _slug(line.lstrip("#"))
        for line in doc.read_text(encoding="utf-8").splitlines()
        if line.startswith("#")
    }


def test_registry_is_populated_and_complete() -> None:
    catalog.register_all()
    assert len(DATASETS) >= 36
    assert {d.source for d in DATASETS.values()} == set(SOURCES)
    views = [d.view for d in DATASETS.values()]
    assert len(views) == len(set(views))
    for spec in DATASETS.values():
        assert spec.key == f"{spec.source}.{spec.name}"
        assert len(spec.schema) > 0, spec.key
        assert spec.keys, spec.key
        assert set(spec.keys) <= set(spec.schema.names), (spec.key, spec.keys)
        assert quote_ident(spec.view)
        assert spec.description, spec.key


def test_every_endpoint_doc_anchor_exists() -> None:
    catalog.register_all()
    missing: list[str] = []
    for spec in DATASETS.values():
        doc_path, _, anchor = spec.endpoint_doc.partition("#")
        doc = DOCS / doc_path
        assert doc.exists(), (spec.key, spec.endpoint_doc)
        if anchor not in _anchors(doc):
            missing.append(f"{spec.key} -> {spec.endpoint_doc}")
    assert missing == []


def test_regular_and_postseason_events_are_distinct_datasets() -> None:
    catalog.register_all()
    assert get_dataset("retrosheet", "events").view == "retrosheet_events"
    assert get_dataset("retrosheet", "events_postseason").view == "retrosheet_events_postseason"


def test_register_rejects_conflicts_and_unknown_sources() -> None:
    catalog.register_all()
    existing = get_dataset("lahman", "People")
    assert register(existing) is existing  # identical re-registration is a no-op
    clash = DatasetSpec(
        "lahman", "Other", existing.view, pa.schema([("a", pa.int32())]), "none", ("a",), "x", "x"
    )
    with pytest.raises(ValueError, match="already used"):
        register(clash)
    with pytest.raises(ValueError, match="unknown source"):
        register(
            DatasetSpec("nope", "x", "v_x", pa.schema([("a", pa.int32())]), "none", ("a",), "", "")
        )
    with pytest.raises(KeyError, match="known:"):
        get_dataset("lahman", "Nope")


def test_raw_store_records_sha_and_detects_tampering(tmp_path: Path) -> None:
    cfg = LakeConfig(home=tmp_path)
    raw = RawStore(cfg)
    path = raw.put("statcast", "pitches", "a.csv", b"x,y\n1,2\n", season=2024, source_ref="abc")
    assert path == tmp_path / "raw" / "statcast" / "pitches" / "season=2024" / "a.csv"
    entry = cfg.dataset_manifest("statcast", "pitches", "raw", 2024).get_chunk("a.csv")
    assert entry is not None
    assert entry["bytes"] == 8 and entry["source_ref"] == "abc" and len(entry["sha256"]) == 64
    assert raw.verify("statcast", "pitches", "a.csv", 2024)
    assert raw.get("statcast", "pitches", "a.csv", 2024) == b"x,y\n1,2\n"
    path.write_bytes(b"tampered")
    assert not raw.verify("statcast", "pitches", "a.csv", 2024)
    assert list(tmp_path.rglob("*.part")) == []


@pytest.mark.parametrize("bad", ["../x", "a/b", "a\\b", ""])
def test_raw_store_rejects_path_traversal(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ValueError, match="invalid chunk id"):
        RawStore(LakeConfig(home=tmp_path)).put("lahman", "People", bad, b"x")


def test_processed_store_layout_partitions_and_manifest(tmp_path: Path) -> None:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec = get_dataset("retrosheet", "events")
    table = pa.table({"GAME_ID": ["A", "B"]})
    path = store.put(spec, table, chunk_id="events", season=2023, source_ref="sha1")
    assert (
        path
        == tmp_path / "processed" / "retrosheet" / "events" / "season=2023" / "part-events.parquet"
    )
    assert pq.ParquetFile(path).metadata.num_rows == 2
    assert store.is_cached(spec, "events", 2023)
    assert not store.is_cached(spec, "events", 2024)
    assert store.row_count(spec) == 2
    entry = cfg.dataset_manifest("retrosheet", "events").get_chunk("season=2023/events")
    assert entry is not None and entry["records_count"] == 2 and entry["source_ref"] == "sha1"
    # rerun overwrites deterministically instead of duplicating
    store.put(spec, pa.table({"GAME_ID": ["C"]}), chunk_id="events", season=2023)
    assert store.row_count(spec) == 1
    assert store.read(spec, 2023)["GAME_ID"].to_pylist() == ["C"]


def test_processed_store_enforces_partition_contract(tmp_path: Path) -> None:
    catalog.register_all()
    store = ProcessedStore(LakeConfig(home=tmp_path))
    table = pa.table({"a": [1]})
    with pytest.raises(ValueError, match="season-partitioned"):
        store.put(get_dataset("statcast", "pitches"), table, chunk_id="x")
    with pytest.raises(ValueError, match="not season-partitioned"):
        store.put(get_dataset("lahman", "People"), table, season=2024)


def test_reprocess_rebuilds_processed_from_raw_without_network(tmp_path: Path) -> None:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    spec = get_dataset("retrosheet", "gamelogs")
    RawStore(cfg).put("retrosheet", "gamelogs", "gl2023.txt", b"a\nb\n", season=2023)

    def parse(raw_dir: Path) -> pa.Table:
        lines = (raw_dir / "gl2023.txt").read_text().split()
        return pa.table({"date": lines})

    out = reprocess(spec, 2023, parse, config=cfg, chunk_id="gl2023")
    assert out.exists()
    assert ProcessedStore(cfg).read(spec, 2023)["date"].to_pylist() == ["a", "b"]
    with pytest.raises(FileNotFoundError, match="no raw data"):
        reprocess(spec, 1999, parse, config=cfg)


def test_put_stream_writes_row_groups_atomically_and_skips_empty_streams(tmp_path: Path) -> None:
    catalog.register_all()
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    spec = get_dataset("retrosheet", "reference_relatives")
    batch = pa.table(
        {
            "person_id_1": ["a", "b"],
            "relation": ["Brother", "Father"],
            "person_id_2": ["c", "d"],
            "_extras": pa.array([None, None], pa.string()),
        }
    )
    assert store.put_stream(spec, iter([batch, batch.slice(0, 1)])) == 3
    part = store.part_path(spec, "data")
    meta = pq.ParquetFile(part).metadata
    assert meta.num_rows == 3 and meta.num_row_groups == 2
    entry = cfg.dataset_manifest("retrosheet", "reference_relatives").get_chunk("data")
    assert entry is not None and entry["records_count"] == 3
    assert list(tmp_path.rglob("*.part")) == []

    empty = get_dataset("retrosheet", "reference_teams")
    assert store.put_stream(empty, iter([])) == 0
    assert not store.part_path(empty, "data").exists()
    assert list(tmp_path.rglob("*.part")) == []


def test_an_empty_rebuild_removes_the_old_part_so_old_rows_are_not_served(tmp_path: Path) -> None:
    catalog.register_all()
    store = ProcessedStore(LakeConfig(home=tmp_path))
    spec = get_dataset("retrosheet", "reference_relatives")
    batch = pa.table(
        {
            "person_id_1": ["a"],
            "relation": ["Brother"],
            "person_id_2": ["c"],
            "_extras": pa.array([None], pa.string()),
        }
    )
    assert store.put_stream(spec, iter([batch])) == 1
    assert store.read_part(spec).num_rows == 1
    assert store.put_stream(spec, iter([])) == 0  # upstream no longer has any rows
    assert not store.part_path(spec, "data").exists()
    assert store.is_cached(spec) and store.read_part(spec).num_rows == 0


def test_put_stream_failure_leaves_no_part_or_final_file(tmp_path: Path) -> None:
    catalog.register_all()
    store = ProcessedStore(LakeConfig(home=tmp_path))
    spec = get_dataset("retrosheet", "reference_relatives")

    def boom() -> "pa.Table":
        raise RuntimeError("parser crashed")

    def gen():  # type: ignore[no-untyped-def]
        yield pa.table(
            {
                "person_id_1": ["a"],
                "relation": ["x"],
                "person_id_2": ["b"],
                "_extras": pa.array([None], pa.string()),
            }
        )
        yield boom()

    with pytest.raises(RuntimeError, match="parser crashed"):
        store.put_stream(spec, gen())
    assert not store.part_path(spec, "data").exists()
    assert list(tmp_path.rglob("*.part")) == []


def test_register_all_is_cheap_after_the_first_pass_and_recovers_a_cleared_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    from baseballpy.core import datasets
    from baseballpy.sources import catalog

    first = catalog.register_all()
    start = time.perf_counter()
    for _ in range(50):
        assert catalog.register_all() is first
    assert (time.perf_counter() - start) / 50 < 0.001  # was about 5 ms per call
    monkeypatch.setattr(datasets, "DATASETS", {})  # a replaced, empty registry is refilled
    assert len(catalog.register_all()) == len(first)


def test_a_schema_change_makes_a_stored_chunk_stale_without_refresh(tmp_path: Path) -> None:
    from baseballpy.core.stores import schema_fingerprint, schema_matches

    config = LakeConfig(home=tmp_path)
    store = ProcessedStore(config)
    old = _spec_with(pa.schema([("a", pa.int32())]))
    store.put(old, pa.table({"a": pa.array([1], pa.int32())}))
    assert store.is_cached(old)
    entry = config.dataset_manifest(old.source, old.name, "processed").get_chunk("data")
    assert entry is not None and entry["schema_sha256"] == schema_fingerprint(old.schema)

    new = _spec_with(pa.schema([("a", pa.int32()), ("b", pa.string())]))
    assert not store.is_cached(new)  # a column was added: the chunk must be rebuilt
    assert not schema_matches(new, entry) and schema_matches(old, entry)
    # a chunk written before schemas were fingerprinted is trusted
    assert schema_matches(new, {k: v for k, v in entry.items() if k != "schema_sha256"})


def _spec_with(schema: pa.Schema) -> DatasetSpec:
    return DatasetSpec(
        source="testsrc",
        name="things",
        view="testsrc_things",
        schema=schema,
        partition="none",
        keys=("a",),
        description="x",
        endpoint_doc="x",
    )


def test_a_parser_revision_replaces_chunks_written_by_an_older_parser(tmp_path: Path) -> None:
    import dataclasses

    from baseballpy.core.stores import schema_matches

    config = LakeConfig(home=tmp_path)
    store = ProcessedStore(config)
    v0 = _spec_with(pa.schema([("a", pa.int32())]))
    store.put(v0, pa.table({"a": pa.array([1], pa.int32())}))
    entry = config.dataset_manifest(v0.source, v0.name, "processed").get_chunk("data") or {}

    v1 = dataclasses.replace(v0, revision=1)  # same columns, the parser now produces other values
    assert store.is_cached(v0) and not store.is_cached(v1)
    assert not schema_matches(v1, entry)
    # a chunk with no digest at all (written before digests existed) is rebuilt too
    assert not schema_matches(v1, {k: v for k, v in entry.items() if k != "schema_sha256"})
    store.put(v1, pa.table({"a": pa.array([1], pa.int32())}))
    assert store.is_cached(v1)
