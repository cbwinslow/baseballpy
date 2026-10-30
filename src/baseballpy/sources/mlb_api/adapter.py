"""MLB Stats API ingest adapter."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

FIRST_SEASON = 1876
KNOWN_DATASETS = {"reference", "season", "games", "history", "people_stats"}
DEFAULT_DATASETS = ("reference", "season")


def _registered() -> set[str]:
    """Every registered MLB dataset name (what ``--datasets`` accepts besides the units)."""
    from baseballpy.sources.mlb_api.access import datasets

    return set(datasets())


def _partitioned() -> set[str]:
    """Names of the season-partitioned MLB datasets."""
    from baseballpy.core.datasets import datasets_for

    return {spec.name for spec in datasets_for("mlb_api") if spec.partition == "season"}


def _result(job: Job, reports: Sequence[Any]) -> JobResult:
    """Row counts of the reports as a result; refused requests fail the job but keep the data."""
    counts = [None if r.requests == r.cached else r.rows for r in reports]
    result = counts_to_result(job, counts)
    refused = [f"{r.name}: {e}" for r in reports for e in r.errors]
    if not refused:
        return result
    shown = "; ".join(refused[:3]) + (f" (+{len(refused) - 3} more)" if len(refused) > 3 else "")
    return JobResult(
        job=job,
        status=JobStatus.FAILED,
        rows=result.rows,
        detail=f"{len(refused)} request(s) refused by the provider, the rest were stored",
        error=shown,
    )


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
        named: list[str] = []
        if selection.datasets:
            # a unit (reference, season, ...) or any registered dataset name (one endpoint job)
            named = [
                d for d in selection.datasets if d not in KNOWN_DATASETS and d in _registered()
            ]
            unknown = [d for d in selection.datasets if d not in KNOWN_DATASETS and d not in named]
            if unknown:
                raise ValueError(
                    f"unknown dataset(s) for mlb_api: {unknown}; known: units "
                    f"{sorted(KNOWN_DATASETS)} or any registered dataset name (see `catalog list`)"
                )
            wanted = set(selection.datasets) & KNOWN_DATASETS
        else:
            wanted = set(DEFAULT_DATASETS)

        jobs: list[Job] = []
        for name in named:
            partitioned = name in _partitioned()
            if partitioned and not selection.seasons:
                continue
            for season in selection.seasons if partitioned else (None,):
                params: dict[str, Any] = {"name": name}
                if season is not None:
                    params["season"] = season
                jobs.append(make_job("mlb_api", "endpoint", **params))
        if "reference" in wanted:
            jobs.append(make_job("mlb_api", "reference"))

        if selection.seasons:
            for season in selection.seasons:
                if "season" in wanted:
                    jobs.append(make_job("mlb_api", "season", season=season))
                if "games" in wanted:
                    jobs.append(
                        make_job(
                            "mlb_api",
                            "season",
                            games=True,
                            season=season,
                            **selection.limit_params(),
                        )
                    )
                if "history" in wanted:
                    jobs.append(make_job("mlb_api", "history", season=season))
                if "people_stats" in wanted:
                    jobs.append(
                        make_job(
                            "mlb_api", "people_stats", season=season, **selection.limit_params()
                        )
                    )
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single MLB Stats API ingest job."""
        source = self._get_source()

        if job.task == "endpoint":
            name = str(job.param("name"))
            season_val = job.param("season")
            table = source.endpoint(
                name, season=int(season_val) if season_val is not None else None, refresh=refresh
            )
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=table.num_rows)

        if job.task == "reference":
            reports = source.ingest_reference(refresh=refresh)
            return _result(job, reports)

        if job.task == "season":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            include_games = bool(job.param("games", False))
            reports = source.ingest_season(
                season, include_games=include_games, max_games=job.limit, refresh=refresh
            )
            return _result(job, reports)

        if job.task == "people_stats":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            reports = source.ingest_people_stats(
                int(season_val), max_people=job.limit, refresh=refresh
            )
            return _result(job, reports)

        if job.task == "history":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            reports = source.ingest_history(season, refresh=refresh)
            return _result(job, reports)

        raise ValueError(f"unknown task {job.task!r} for mlb_api")


__all__ = ["MlbApiAdapter"]
