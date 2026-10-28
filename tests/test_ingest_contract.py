"""Source contract (ADR 39): every source that owns datasets plugs in through an IngestAdapter."""

import pytest

from baseballpy.core.datasets import DATASETS
from baseballpy.ingest import ADAPTERS, IngestAdapter, Job, Selection, get_adapters
from baseballpy.sources.adapters import register_all_adapters
from baseballpy.sources.catalog import register_all


def _sources_with_datasets() -> set[str]:
    register_all()
    return {spec.source for spec in DATASETS.values()}


def test_every_source_with_datasets_has_a_registered_adapter() -> None:
    register_all_adapters()
    missing = _sources_with_datasets() - set(ADAPTERS)
    assert not missing, f"sources without an IngestAdapter: {sorted(missing)}"


def test_every_adapter_satisfies_the_protocol_and_plans_its_own_jobs() -> None:
    register_all_adapters()
    adapters = get_adapters()
    assert adapters, "no adapters registered"
    for source, adapter in adapters.items():
        assert isinstance(adapter, IngestAdapter), source
        assert adapter.source == source
        jobs = adapter.plan(Selection())
        assert all(isinstance(job, Job) and job.source == source for job in jobs), source


def test_registering_adapters_twice_is_idempotent() -> None:
    register_all_adapters()
    before = dict(ADAPTERS)
    register_all_adapters()
    assert before == ADAPTERS


@pytest.mark.parametrize("source", sorted(_sources_with_datasets()))
def test_planning_with_seasons_never_needs_the_network(source: str) -> None:
    """``plan`` is pure: it must not construct an orchestrator or touch the network."""
    register_all_adapters()
    adapter = get_adapters((source,))[source]
    jobs = adapter.plan(Selection(seasons=(2023,)))
    assert all(job.source == source for job in jobs)
