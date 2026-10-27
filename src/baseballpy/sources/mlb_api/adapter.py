"""MLB Stats API ingest adapter."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import Job, JobResult, Selection, make_job

FIRST_SEASON = 1876
KNOWN_DATASETS = {"reference", "season", "games", "history"}
DEFAULT_DATASETS = ("reference", "season")


class MlbApiAdapter:
    """IngestAdapter wrapping MlbApiSource."""

    source = "mlb_api"

    def __init__(self, source: Any = None) -> None:
        self._source = source

    def _get_source(self) -> Any:
        if self._source is None:
            from baseballpy.sources.mlb_api.api import MlbApiSource

            self._source = MlbApiSource()
        return self._source

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for MLB Stats API (1876 to current year)."""
        return range(FIRST_SEASON, datetime.now().year + 1)

    def plan(self, selection: Selection) -> list[Job]:
        """Generate planned jobs matching the given selection."""
        if selection.datasets:
            unknown = [d for d in selection.datasets if d not in KNOWN_DATASETS]
            if unknown:
                raise ValueError(
                    f"unknown dataset(s) for mlb_api: {unknown}; known: {sorted(KNOWN_DATASETS)}"
                )
            wanted = set(selection.datasets)
        else:
            wanted = set(DEFAULT_DATASETS)

        jobs: list[Job] = []
        if "reference" in wanted:
            jobs.append(make_job("mlb_api", "reference"))

        if selection.seasons:
            for season in selection.seasons:
                if "season" in wanted:
                    jobs.append(make_job("mlb_api", "season", season=season))
                if "games" in wanted:
                    jobs.append(make_job("mlb_api", "season", games=True, season=season))
                if "history" in wanted:
                    jobs.append(make_job("mlb_api", "history", season=season))
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single MLB Stats API ingest job."""
        source = self._get_source()

        if job.task == "reference":
            reports = source.ingest_reference(refresh=refresh)
            counts = [None if r.requests == r.cached else r.rows for r in reports]
            return counts_to_result(job, counts)

        if job.task == "season":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            include_games = bool(job.param("games", False))
            reports = source.ingest_season(season, include_games=include_games, refresh=refresh)
            counts = [None if r.requests == r.cached else r.rows for r in reports]
            return counts_to_result(job, counts)

        if job.task == "history":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            reports = source.ingest_history(season, refresh=refresh)
            counts = [None if r.requests == r.cached else r.rows for r in reports]
            return counts_to_result(job, counts)

        raise ValueError(f"unknown task {job.task!r} for mlb_api")


__all__ = ["MlbApiAdapter"]
