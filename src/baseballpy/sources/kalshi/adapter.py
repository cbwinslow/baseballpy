"""Kalshi ingest adapter: one catalog job that fans out over the in-scope series on threads."""

from collections.abc import Callable, Sequence

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job
from baseballpy.sources.kalshi.ingest import IngestOutcome

Loader = Callable[[Sequence[str] | None], IngestOutcome]


def _default_loader(datasets: Sequence[str] | None) -> IngestOutcome:
    from baseballpy.sources.kalshi.ingest import ingest

    return ingest(datasets)


def _dataset_names() -> list[str]:
    from baseballpy.sources.kalshi.ingest import dataset_names

    return dataset_names()


class KalshiAdapter:
    """IngestAdapter for Kalshi: season-less, so seasons in the selection are ignored.

    One ``catalog`` job covers series, events and markets (a subset is carried in the ``datasets``
    job parameter); its threads and request limits come from the shared HTTP client.
    """

    source = "kalshi"
    task = "catalog"

    def __init__(self, loader: Loader | None = None) -> None:
        self._loader = loader or _default_loader

    def all_seasons(self) -> Sequence[int]:
        """Kalshi has no seasons."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """One job; its ``datasets`` parameter is set only when a subset is selected."""
        names = _dataset_names()
        if not selection.datasets:
            return [make_job(self.source, self.task)]
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for kalshi: {unknown}; known: {names}")
        chosen = [d for d in names if d in selection.datasets]
        if chosen == names:
            return [make_job(self.source, self.task)]
        return [make_job(self.source, self.task, datasets=",".join(chosen))]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute the catalog job (the catalog is always fetched again, so ``refresh`` is moot)."""
        if job.task != self.task:
            raise ValueError(f"unknown task {job.task!r} for kalshi")
        chosen = job.param("datasets")
        outcome = self._loader(str(chosen).split(",") if chosen else None)
        return JobResult(
            job=job,
            status=JobStatus.COMPLETED,
            rows=sum(outcome.rows.values()),
            detail=f"{outcome.series} series; "
            + ", ".join(f"{name}={count}" for name, count in outcome.rows.items()),
        )


__all__ = ["KalshiAdapter"]
