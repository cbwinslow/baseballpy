"""Retrosheet ingest adapter."""

from collections.abc import Sequence
from typing import Any

from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import Job, JobResult, Selection, make_job
from baseballpy.sources.retrosheet.api import SEASON_DATASETS

KNOWN_DATASETS = {"reference"} | set(SEASON_DATASETS)


class RetrosheetAdapter:
    """IngestAdapter wrapping RetrosheetSource."""

    source = "retrosheet"

    def __init__(self, source: Any = None) -> None:
        self._source = source

    def _get_source(self) -> Any:
        if self._source is None:
            from baseballpy.sources.retrosheet.api import RetrosheetSource

            self._source = RetrosheetSource()
        return self._source

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for Retrosheet."""
        seasons: list[int] = self._get_source().downloader.seasons()
        return seasons

    def plan(self, selection: Selection) -> list[Job]:
        """Generate planned jobs matching the given selection."""
        if selection.datasets:
            unknown = [d for d in selection.datasets if d not in KNOWN_DATASETS]
            if unknown:
                raise ValueError(
                    f"unknown dataset(s) for retrosheet: {unknown}; known: {sorted(KNOWN_DATASETS)}"
                )
            has_reference = "reference" in selection.datasets
            season_datasets = tuple(d for d in selection.datasets if d != "reference")
        else:
            has_reference = True
            season_datasets = ()

        jobs: list[Job] = []
        if has_reference:
            jobs.append(make_job("retrosheet", "reference"))

        if selection.seasons:
            for season in selection.seasons:
                if selection.datasets:
                    if season_datasets:
                        jobs.append(
                            make_job(
                                "retrosheet",
                                "season",
                                datasets=",".join(season_datasets),
                                season=season,
                            )
                        )
                else:
                    jobs.append(make_job("retrosheet", "season", season=season))
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single Retrosheet ingest job."""
        source = self._get_source()

        if job.task == "reference":
            report_dict = source.ingest_reference(refresh=refresh)
            return counts_to_result(job, report_dict.values())

        if job.task == "season":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            datasets_param = job.param("datasets")
            datasets = tuple(str(datasets_param).split(",")) if datasets_param else None
            report = source.ingest_season(season, datasets=datasets, refresh=refresh)
            return counts_to_result(job, report.datasets.values())

        raise ValueError(f"unknown task {job.task!r} for retrosheet")


__all__ = ["RetrosheetAdapter"]
