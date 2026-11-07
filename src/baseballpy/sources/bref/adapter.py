"""Baseball-Reference ingest adapter: one job downloads the two WAR files and types them."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

if TYPE_CHECKING:
    from baseballpy.sources.bref.ingest import IngestOutcome

#: ``loader(datasets, refresh)`` makes the datasets current and says what it did per dataset.
Loader = Callable[[Sequence[str] | None, bool], "IngestOutcome"]


def _default_loader(datasets: Sequence[str] | None, refresh: bool) -> "IngestOutcome":
    from baseballpy.sources.bref.ingest import ingest

    return ingest(datasets, refresh=refresh)


def _dataset_names() -> list[str]:
    from baseballpy.sources.bref.ingest import dataset_names

    return dataset_names()


class BrefAdapter:
    """IngestAdapter for Baseball-Reference WAR: one job, at most two requests.

    The files hold every season at once, so seasons in the selection are ignored. A subset of
    datasets is carried in the ``datasets`` job parameter.
    """

    source = "bref"
    task = "war"

    def __init__(self, loader: Loader | None = None) -> None:
        self._loader = loader or _default_loader

    def all_seasons(self) -> Sequence[int]:
        """Baseball-Reference WAR files are not split by season upstream."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """One job; its ``datasets`` parameter is set only when a subset is selected."""
        names = _dataset_names()
        if not selection.datasets:
            return [make_job(self.source, self.task)]
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for bref: {unknown}; known: {names}")
        chosen = [d for d in names if d in selection.datasets]
        if chosen == names:
            return [make_job(self.source, self.task)]
        return [make_job(self.source, self.task, datasets=",".join(chosen))]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute the WAR ingest job."""
        if job.task != self.task:
            raise ValueError(f"unknown task {job.task!r} for bref")
        chosen = job.param("datasets")
        outcome = self._loader(str(chosen).split(",") if chosen else None, refresh)
        return JobResult(
            job=job,
            status=JobStatus.COMPLETED,
            rows=sum(outcome.rows.values()),
            detail=", ".join(f"{name}={count}" for name, count in outcome.rows.items()),
        )


__all__ = ["BrefAdapter"]
