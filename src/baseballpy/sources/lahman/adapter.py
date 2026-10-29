"""SABR Lahman Baseball Database ingest adapter."""

from collections.abc import Sequence
from typing import Any

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job


class LahmanAdapter:
    """IngestAdapter wrapping LahmanSource."""

    source = "lahman"

    def __init__(self, source: Any = None) -> None:
        self._source = source

    def _get_source(self) -> Any:
        if self._source is None:
            from baseballpy.sources.lahman.api import LahmanSource

            self._source = LahmanSource()
        return self._source

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for Lahman (empty: Lahman is season-less)."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """Generate planned jobs matching the given selection."""
        if self._source is not None:
            available_tables = self._source.list_tables()
        else:
            from baseballpy.sources.lahman.schema import LahmanTable

            available_tables = [t.value for t in LahmanTable]

        by_lower = {name.lower(): name for name in available_tables}
        if selection.datasets:
            unknown = [d for d in selection.datasets if d.lower() not in by_lower]
            if unknown:
                raise ValueError(
                    f"unknown table(s) for lahman: {unknown}; known: {sorted(by_lower.values())}"
                )
            wanted = [by_lower[d.lower()] for d in selection.datasets]  # names ignore letter case
        else:
            wanted = list(available_tables)

        return [make_job("lahman", "table", name=name) for name in wanted]

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single Lahman ingest job."""
        if job.task != "table":
            raise ValueError(f"unknown task {job.task!r} for lahman")

        name_val = job.param("name")
        if name_val is None:
            raise ValueError(f"job {job.job_id} missing 'name' parameter")

        loaded = self._get_source().load_table(str(name_val), refresh=refresh)
        return JobResult(
            job=job,
            status=JobStatus.COMPLETED,
            rows=loaded.table.num_rows,
            cache_hit=loaded.from_cache,
        )


__all__ = ["LahmanAdapter"]
