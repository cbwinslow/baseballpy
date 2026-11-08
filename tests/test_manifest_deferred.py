"""A bulk run must not pay for the size of the lake at every chunk (ADR 93)."""

from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.atomic import ManifestTracker
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog


def _saves(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    counted: list[int] = []
    real = ManifestTracker.save

    def counting(self: ManifestTracker, _only: object = None) -> None:
        counted.append(1)
        real(self, _only)  # type: ignore[arg-type]

    monkeypatch.setattr(ManifestTracker, "save", counting)
    return counted


def test_deferred_saves_are_batched_and_visible_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "_manifest.json"
    tracker = ManifestTracker(path)
    saves = _saves(monkeypatch)
    with tracker.deferred(every=10):
        for i in range(25):
            tracker.set_completed(f"c{i}", records_count=i)
            assert tracker.is_completed(f"c{i}")  # seen by this process before any save
        assert len(saves) == 2  # after the 10th and the 20th entry
        assert "c24" not in ManifestTracker(path).chunks()  # not on disk yet
    assert len(saves) == 3  # the rest is saved on exit
    assert set(ManifestTracker(path).chunks()) == {f"c{i}" for i in range(25)}


def test_an_error_inside_the_block_still_saves_what_was_recorded(tmp_path: Path) -> None:
    path = tmp_path / "_manifest.json"
    tracker = ManifestTracker(path)
    with pytest.raises(RuntimeError), tracker.deferred(every=100):
        tracker.set_completed("a", records_count=1)
        raise RuntimeError("the download stopped")
    assert "a" in ManifestTracker(path).chunks()


def test_a_change_by_another_writer_does_not_lose_held_back_entries(tmp_path: Path) -> None:
    path = tmp_path / "_manifest.json"
    mine, other = ManifestTracker(path), ManifestTracker(path)
    with mine.deferred(every=100):
        mine.set_completed("mine", records_count=1)
        other.set_completed("theirs", records_count=2)  # the file changed under us
        assert mine.is_completed("theirs") and mine.is_completed("mine")
    assert set(ManifestTracker(path).chunks()) == {"mine", "theirs"}


def test_nested_blocks_save_once_at_the_outermost_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracker = ManifestTracker(tmp_path / "_manifest.json")
    saves = _saves(monkeypatch)
    with tracker.deferred(every=100), tracker.deferred(every=100):
        tracker.set_completed("a")
    assert len(saves) == 1


@pytest.fixture
def spec():  # type: ignore[no-untyped-def]
    catalog.register_all()
    return get_dataset("mlb_api", "award_recipients")


def test_a_put_does_not_copy_the_whole_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spec,  # type: ignore[no-untyped-def]
) -> None:
    """The name-clash check used to copy every entry of the manifest at every put."""
    store = ProcessedStore(LakeConfig(home=tmp_path))
    table = pa.table({f.name: pa.nulls(1, f.type) for f in spec.schema}, schema=spec.schema)
    store.put(spec, table, chunk_id="a", season=2023)

    def forbidden(self: ManifestTracker) -> dict[str, dict[str, object]]:
        raise AssertionError("put copied every manifest entry")

    monkeypatch.setattr(ManifestTracker, "chunks", forbidden)
    store.put(spec, table, chunk_id="b", season=2023)
    store.put(spec, table, chunk_id="c", season=2024)


def test_the_clash_check_still_sees_chunks_written_by_others_and_removed_ones(
    tmp_path: Path,
    spec,  # type: ignore[no-untyped-def]
) -> None:
    config = LakeConfig(home=tmp_path)
    store = ProcessedStore(config)
    table = pa.table({f.name: pa.nulls(1, f.type) for f in spec.schema}, schema=spec.schema)
    store.put(spec, table, chunk_id="Abc", season=2023)
    with pytest.raises(ValueError, match="would share the file"):
        store.put(spec, table, chunk_id="aBC", season=2023)  # differs only by case
    store.put(spec, table, chunk_id="aBC", season=2024)  # another season folder is fine
    # a chunk recorded by another writer (another process) is seen too
    ManifestTracker(config.processed_dir(spec.source, spec.name) / "_manifest.json").set_completed(
        "season=2025/XyZ", records_count=0
    )
    with pytest.raises(ValueError, match="would share the file"):
        store.put(spec, table, chunk_id="xyz", season=2025)
