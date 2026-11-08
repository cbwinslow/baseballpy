"""Tests for two-phase atomic file writes and checkpoint manifest tracking."""

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.atomic import ManifestTracker, atomic_write, atomic_write_parquet


def test_atomic_write_success(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"

    with atomic_write(target) as part_file:
        part_file.write_text("hello atomic", encoding="utf-8")
        assert part_file.exists()
        assert not target.exists()

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "hello atomic"
    # Ensure .part file is removed/renamed
    assert not target.with_suffix(".txt.part").exists()


def test_atomic_write_failure_cleanup(tmp_path: Path) -> None:
    target = tmp_path / "corrupted.txt"
    part_target = target.with_suffix(".txt.part")

    with (
        pytest.raises(RuntimeError, match="simulated failure"),
        atomic_write(target) as part_file,
    ):
        part_file.write_text("partial corrupted data", encoding="utf-8")
        raise RuntimeError("simulated failure")

    assert not target.exists()
    assert not part_target.exists()


def test_atomic_write_parquet(tmp_path: Path) -> None:
    target = tmp_path / "table.parquet"
    table = pa.table({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

    atomic_write_parquet(table, target)

    assert target.exists()
    read_tbl = pq.read_table(target)
    assert len(read_tbl) == 3
    assert read_tbl.column_names == ["col1", "col2"]


def test_manifest_tracker_lifecycle(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest = ManifestTracker(manifest_path)

    assert not manifest.is_completed("chunk_2024_01")
    manifest.set_completed("chunk_2024_01", records_count=5000, etag='"etag123"')

    assert manifest.is_completed("chunk_2024_01")
    chunk = manifest.get_chunk("chunk_2024_01")
    assert chunk is not None
    assert chunk["records_count"] == 5000
    assert chunk["etag"] == '"etag123"'

    # Reload from disk and verify persistence
    reloaded = ManifestTracker(manifest_path)
    assert reloaded.is_completed("chunk_2024_01")
    assert not reloaded.is_completed("chunk_2024_02")


def test_manifest_is_parsed_only_when_the_file_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chunk lookups must not re-parse a big manifest each time, yet must see other writers."""
    path = tmp_path / "_manifest.json"
    mine = ManifestTracker(path)
    mine.set_completed("a")
    reads: list[int] = []
    original = ManifestTracker._read_disk

    def counting(self: ManifestTracker):  # type: ignore[no-untyped-def]
        reads.append(1)
        return original(self)

    monkeypatch.setattr(ManifestTracker, "_read_disk", counting)
    for _ in range(50):
        assert mine.is_completed("a")
    assert reads == []  # unchanged file: no parse at all

    ManifestTracker(path).set_completed("b")  # another writer
    assert mine.is_completed("b")  # picked up through the changed stat
    assert len(reads) >= 1


def test_manifest_large_entry_msgspec_roundtrip(tmp_path: Path) -> None:
    """Zero-copy msgspec encoding saves and reads thousands of chunks without memory spikes."""
    path = tmp_path / "_manifest.json"
    tracker = ManifestTracker(path)
    entries = {
        f"chunk_{i}": {
            "status": "COMPLETED",
            "records_count": i * 10,
            "etag": f'"etag_{i}"',
            "completed_at": "2026-11-07T12:00:00Z",
        }
        for i in range(1000)
    }
    tracker.put_entries(entries)

    # Verify reload from disk
    reloaded = ManifestTracker(path)
    assert reloaded.is_completed("chunk_0")
    assert reloaded.is_completed("chunk_999")
    chunk = reloaded.get_chunk("chunk_500")
    assert chunk is not None
    assert chunk["records_count"] == 5000


def test_saving_a_large_manifest_does_not_build_a_big_string(tmp_path: Path) -> None:
    """A save writes bytes straight to the file: the extra memory stays near the file size."""
    import tracemalloc

    path = tmp_path / "_manifest.json"
    tracker = ManifestTracker(path)
    tracker.put_entries(
        {
            f"g{i}": {"status": "COMPLETED", "records_count": i, "schema_sha256": "x" * 64}
            for i in range(20_000)
        }
    )
    size = path.stat().st_size
    tracemalloc.start()
    try:
        tracker.set_completed("g1", records_count=1)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 3 * size


def test_a_manifest_that_is_not_utf8_is_preserved_not_lost(tmp_path: Path) -> None:
    path = tmp_path / "_manifest.json"
    path.write_bytes(b'{"chunks": {"a": "\xff\xfe"}}')
    assert ManifestTracker(path).get_chunk("a") is None
    assert list(tmp_path.glob("*.corrupt-*"))
