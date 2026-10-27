"""Adapter Protocol and registry for data ingestion sources."""

from collections.abc import Callable, Sequence
from typing import Protocol, runtime_checkable

from baseballpy.ingest.types import Job, JobResult, Selection


@runtime_checkable
class IngestAdapter(Protocol):
    """Protocol satisfied by per-source ingest adapters."""

    source: str

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for this source."""
        ...

    def plan(self, selection: Selection) -> list[Job]:
        """Generate planned jobs matching the given selection."""
        ...

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single job and return its outcome."""
        ...


ADAPTERS: dict[str, Callable[[], IngestAdapter]] = {}


def register_adapter(source: str, factory: Callable[[], IngestAdapter]) -> None:
    """Register an adapter factory for ``source``; re-registering the same factory is a no-op."""
    existing = ADAPTERS.get(source)
    if existing is not None:
        if existing == factory:
            return
        raise ValueError(
            f"adapter for source {source!r} already registered with a different factory"
        )
    ADAPTERS[source] = factory


def get_adapters(sources: Sequence[str] = ()) -> dict[str, IngestAdapter]:
    """Instantiate and return adapters for ``sources`` (or all registered if empty).

    Adapters are instantiated lazily on demand.
    """
    target_sources = list(sources) if sources else list(ADAPTERS.keys())
    for s in target_sources:
        if s not in ADAPTERS:
            known = ", ".join(sorted(ADAPTERS)) or "(none registered)"
            raise KeyError(f"unknown source {s!r}; known: {known}")
    return {s: ADAPTERS[s]() for s in target_sources}


__all__ = [
    "ADAPTERS",
    "IngestAdapter",
    "get_adapters",
    "register_adapter",
]
