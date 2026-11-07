"""FanGraphs ingest adapter: one job types the files the user put in the inbox (no network)."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

if TYPE_CHECKING:
    from baseballpy.sources.fangraphs.ingest import IngestOutcome

#: ``loader(datasets, refresh)`` makes the datasets current and says what it did per dataset.
Loader = Callable[[Sequence[str] | None, bool], "IngestOutcome"]


def _default_loader(datasets: Sequence[str] | None, refresh: bool) -> "IngestOutcome":
    from baseballpy.sources.fangraphs.ingest import ingest

    return ingest(datasets, refresh=refresh)


def _dataset_names() -> list[str]:
    from baseballpy.sources.fangraphs.ingest import dataset_names

    return dataset_names()


class FangraphsAdapter:
    """IngestAdapter for the FanGraphs files in the inbox: one job, no request to any host.

    Seasons in the selection are ignored (each file holds every season). A subset of datasets is
    carried in the ``datasets`` job parameter.
    """

    source = "fangraphs"
    task = "inbox"

    def __init__(self, loader: Loader | None = None) -> None:
        self._loader = loader or _default_loader

    def all_seasons(self) -> Sequence[int]:
        """The files are not split by season."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """One job; its ``datasets`` parameter is set only when a subset is selected."""
        names = _dataset_names()
        if not selection.datasets:
            return [make_job(self.source, self.task)]
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for fangraphs: {unknown}; known: {names}")
        chosen = [d for d in names if d in selection.datasets]
        return [make_job(self.source, self.task, datasets=",".join(chosen))]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute the inbox ingest job."""
        if job.task != self.task:
            raise ValueError(f"unknown task {job.task!r} for fangraphs")
        chosen = job.param("datasets")
        outcome = self._loader(str(chosen).split(",") if chosen else None, refresh)
        detail = ", ".join(f"{name}={count}" for name, count in outcome.rows.items())
        if outcome.missing:
            detail += f"; no file for {', '.join(outcome.missing)}"
        return JobResult(
            job=job,
            status=JobStatus.COMPLETED,
            rows=sum(outcome.rows.values()),
            detail=detail,
            cache_hit=bool(outcome.rows) and len(outcome.unchanged) == len(outcome.rows),
        )


__all__ = ["FangraphsAdapter"]
