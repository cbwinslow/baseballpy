"""Chadwick Bureau Register ingest adapter."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

if TYPE_CHECKING:
    from baseballpy.sources.chadwick.ingest import IngestOutcome

#: ``loader(datasets, refresh)`` makes the datasets current and says what it did per dataset.
Loader = Callable[[Sequence[str] | None, bool], "IngestOutcome"]


def _default_loader(datasets: Sequence[str] | None, refresh: bool) -> "IngestOutcome":
    from baseballpy.sources.chadwick.ingest import ingest

    return ingest(datasets, refresh=refresh)


def _dataset_names() -> list[str]:
    from baseballpy.sources.chadwick.ingest import dataset_names

    return dataset_names()


class ChadwickAdapter:
    """IngestAdapter for the Chadwick Register: one job downloads once and types the datasets.

    Any registered Chadwick dataset can be selected. All datasets share one download, so the job is
    one unit; a subset is carried in the ``datasets`` job parameter and the job reports rows per
    dataset in its detail.
    """

    source = "chadwick"
    task = "register"

    def __init__(self, loader: Loader | None = None) -> None:
        self._loader = loader or _default_loader

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for Chadwick (empty: Chadwick is season-less)."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """One job; its ``datasets`` parameter is set only when a subset is selected."""
        names = _dataset_names()
        if not selection.datasets:
            return [make_job(self.source, self.task)]
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for chadwick: {unknown}; known: {names}")
        chosen = [d for d in names if d in selection.datasets]
        if chosen == names:
            return [make_job(self.source, self.task)]
        return [make_job(self.source, self.task, datasets=",".join(chosen))]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute the Chadwick ingest job."""
        if job.task != self.task:
            raise ValueError(f"unknown task {job.task!r} for chadwick")
        chosen = job.param("datasets")
        selected = str(chosen).split(",") if chosen else None
        outcome = self._loader(selected, refresh)
        return JobResult(
            job=job,
            status=JobStatus.COMPLETED,
            rows=sum(outcome.rows.values()),
            detail=", ".join(f"{name}={count}" for name, count in outcome.rows.items()),
            cache_hit=not outcome.tables,
        )


__all__ = ["ChadwickAdapter"]
