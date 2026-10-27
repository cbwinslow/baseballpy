"""Domain types for the baseballpy ingestion pipeline."""

from dataclasses import dataclass, field
from enum import StrEnum


class JobStatus(StrEnum):
    """Execution status of an ingest job."""

    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Selection:
    """Ingest scope: seasons, sources, datasets, and refresh flag."""

    seasons: tuple[int, ...] = ()
    sources: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    refresh: bool = False


@dataclass(frozen=True)
class Job:
    """Immutable, hashable description of a single unit of ingestion work."""

    source: str
    task: str
    params: tuple[tuple[str, str | int | bool], ...] = ()

    @property
    def job_id(self) -> str:
        """Deterministic identifier: ``<source>:<task>[:<k>=<v>...]``."""
        suffix = "".join(f":{k}={v}" for k, v in self.params)
        return f"{self.source}:{self.task}{suffix}"

    def param(self, name: str, default: str | int | bool | None = None) -> str | int | bool | None:
        """Look up a parameter by name, returning ``default`` if absent."""
        for k, v in self.params:
            if k == name:
                return v
        return default


def make_job(source: str, task: str, **params: str | int | bool) -> Job:
    """Create a :class:`Job` with keyword arguments sorted into ``params``."""
    sorted_params: tuple[tuple[str, str | int | bool], ...] = tuple(
        sorted(params.items(), key=lambda item: item[0])
    )
    return Job(source=source, task=task, params=sorted_params)


@dataclass
class JobResult:
    """Outcome of running a single ingest job."""

    job: Job
    status: JobStatus
    rows: int | None = None
    seconds: float = 0.0
    detail: str = ""
    error: str | None = None


@dataclass
class RunReport:
    """Aggregated results from running a collection of ingest jobs."""

    results: list[JobResult] = field(default_factory=list)

    @property
    def failed(self) -> list[JobResult]:
        """All results with status FAILED."""
        return [r for r in self.results if r.status == JobStatus.FAILED]

    @property
    def cancelled(self) -> list[JobResult]:
        """All results with status CANCELLED."""
        return [r for r in self.results if r.status == JobStatus.CANCELLED]

    @property
    def exit_code(self) -> int:
        """Process exit code: 130 if cancelled, 1 if failed, else 0."""
        if any(r.status == JobStatus.CANCELLED for r in self.results):
            return 130
        if any(r.status == JobStatus.FAILED for r in self.results):
            return 1
        return 0

    def counts(self) -> dict[str, int]:
        """Count results by status value, omitting statuses with zero occurrences."""
        tally: dict[str, int] = {}
        for r in self.results:
            key = r.status.value
            tally[key] = tally.get(key, 0) + 1
        return tally


__all__ = [
    "Job",
    "JobResult",
    "JobStatus",
    "RunReport",
    "Selection",
    "make_job",
]
