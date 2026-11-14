"""Tests for resolving dataset group names in ingest dry-run estimates."""

from collections.abc import Mapping
from pathlib import Path

import pyarrow as pa
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, DatasetSpec, get_dataset
from baseballpy.ingest.adapters import (
    ADAPTERS,
    GroupedAdapter,
    IngestAdapter,
)
from baseballpy.ingest.estimate import TypicalSize, estimate
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection
from baseballpy.sources import catalog
from baseballpy.sources.adapters import register_all_adapters
from baseballpy.sources.mlb_api.adapter import MlbApiAdapter
from baseballpy.sources.mlb_api.endpoints import SUPPORTED


@pytest.fixture(autouse=True)
def _register_datasets() -> None:
    catalog.register_all()


class _FakeGroupedAdapter:
    source = "fake_source"

    def all_seasons(self) -> list[int]:
        return [2024]

    def plan(self, selection: Selection) -> list[Job]:
        return []

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        return JobResult(job=job, status=JobStatus.COMPLETED)

    def dataset_groups(self) -> Mapping[str, tuple[str, ...]]:
        return {"bundle": ("ds1", "ds2")}


def test_fake_grouped_adapter_resolves_group_and_leaves_unknown_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec1 = DatasetSpec(
        source="fake_source",
        name="ds1",
        view="v_fake_ds1",
        schema=pa.schema([("id", pa.int64())]),
        partition="season",
        keys=("id",),
        description="Dataset 1",
        endpoint_doc="",
    )
    spec2 = DatasetSpec(
        source="fake_source",
        name="ds2",
        view="v_fake_ds2",
        schema=pa.schema([("id", pa.int64())]),
        partition="season",
        keys=("id",),
        description="Dataset 2",
        endpoint_doc="",
    )
    monkeypatch.setitem(DATASETS, spec1.key, spec1)
    monkeypatch.setitem(DATASETS, spec2.key, spec2)
    monkeypatch.setitem(ADAPTERS, "fake_source", _FakeGroupedAdapter)

    selection = Selection(
        sources=("fake_source",),
        datasets=("bundle", "not_a_real_dataset"),
        seasons=(2024,),
    )
    sizes = {
        "fake_source.ds1": TypicalSize(bytes_per_folder=50, folders_measured=1),
        "fake_source.ds2": TypicalSize(bytes_per_folder=50, folders_measured=1),
    }
    est = estimate([selection], LakeConfig(home=tmp_path), sizes)

    assert est.datasets == 2
    assert est.folders_total == 2
    assert est.folders_missing == 2
    assert est.bytes_typical == 100
    assert "bundle" not in est.unresolved
    assert est.unresolved == ("not_a_real_dataset",)


def test_real_mlb_adapter_dataset_groups(tmp_path: Path) -> None:
    register_all_adapters()  # idempotent: the estimate finds the adapters through the registry
    adapter = MlbApiAdapter()
    assert isinstance(adapter, GroupedAdapter)
    groups = adapter.dataset_groups()

    assert "games" in groups
    games = groups["games"]
    assert len(games) > 0

    for name in games:
        spec = get_dataset("mlb_api", name)
        assert spec is not None
        assert spec.name == name

    assert any("boxscore" in name for name in games)
    assert not any(name.startswith("ref_") for name in games)
    assert not any("standing" in name for name in games)
    assert not any("team" in name and not name.startswith("game_") for name in games)

    all_grouped = {name for names in groups.values() for name in names}
    for ep in SUPPORTED:
        assert ep.unsupported is None
        assert ep.name in all_grouped, f"endpoint {ep.name} missing from dataset_groups"

    selection = Selection(sources=("mlb_api",), datasets=("games",), seasons=(2024,))
    est = estimate([selection], LakeConfig(home=tmp_path))
    assert est.datasets == len(games)
    assert est.unresolved == ()


def test_adapter_raising_on_construction_does_not_crash_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _broken_factory() -> IngestAdapter:
        raise RuntimeError("boom on construction")

    monkeypatch.setitem(ADAPTERS, "broken_source", _broken_factory)
    selection = Selection(sources=("broken_source",), datasets=("some_group",), seasons=(2024,))
    est = estimate([selection], LakeConfig(home=tmp_path))
    assert est.datasets == 0
    assert est.unresolved == ("some_group",)
