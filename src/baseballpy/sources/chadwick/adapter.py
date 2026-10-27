"""Chadwick Bureau Register ingest adapter."""

from collections.abc import Callable, Sequence, Sized

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

KNOWN_DATASETS = {"register"}


class ChadwickAdapter:
    """IngestAdapter wrapping ChadwickRegister."""

    source = "chadwick"

    def __init__(self, loader: Callable[[bool], Sized] | None = None) -> None:
        self._loader = loader

    def _load(self, refresh: bool) -> Sized:
        if self._loader is not None:
            return self._loader(refresh)
        from baseballpy.sources.chadwick.register import ChadwickRegister

        return ChadwickRegister.load(refresh=refresh)

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for Chadwick (empty: Chadwick is season-less)."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """Generate planned jobs matching the given selection."""
        if selection.datasets:
            unknown = [d for d in selection.datasets if d not in KNOWN_DATASETS]
            if unknown:
                raise ValueError(
                    f"unknown dataset(s) for chadwick: {unknown}; known: {sorted(KNOWN_DATASETS)}"
                )
        return [make_job("chadwick", "register")]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single Chadwick ingest job."""
        if job.task != "register":
            raise ValueError(f"unknown task {job.task!r} for chadwick")

        register = self._load(refresh)
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=len(register))


__all__ = ["ChadwickAdapter"]
