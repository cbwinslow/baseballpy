"""Retrosheet ingest adapter."""

from collections.abc import Sequence
from typing import Any

from baseballpy.core.datasets import datasets_for
from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import Job, JobResult, Selection, make_job
from baseballpy.sources.retrosheet.api import REFERENCE_UNIT, UNITS, unit_of, units_for


def known_datasets() -> list[str]:
    """Every name ``--datasets`` accepts: registry dataset names, ingest units and ``reference``."""
    names = {d.name for d in datasets_for("retrosheet")}
    return sorted(names | set(UNITS) | {REFERENCE_UNIT})


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
        """Generate planned jobs matching the given selection.

        ``--datasets`` takes any registered dataset name (``box_games``, ``boxscores_batting``,
        ``reference_teams``, ...) or an ingest unit (``box_accounts``, ``reference``); a name is
        resolved to the unit that writes it, so ``-d reference_teams`` ingests every reference table.
        """
        if selection.datasets:
            if unknown := [d for d in selection.datasets if unit_of(d) is None]:
                raise ValueError(
                    f"unknown dataset(s) for retrosheet: {unknown}; known: {known_datasets()}"
                )
            units = units_for(selection.datasets)
            has_reference = REFERENCE_UNIT in units
            season_units = tuple(u for u in units if u != REFERENCE_UNIT)
            if season_units and not selection.seasons:
                raise ValueError(
                    f"retrosheet dataset(s) {list(season_units)} are stored per season: "
                    "pass --seasons (for example --seasons 2023)"
                )
        else:
            has_reference = True
            season_units = ()

        jobs: list[Job] = []
        if has_reference:
            jobs.append(make_job("retrosheet", "reference"))

        for season in selection.seasons or ():
            if selection.datasets:
                if season_units:
                    jobs.append(
                        make_job(
                            "retrosheet",
                            "season",
                            datasets=",".join(season_units),
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


__all__ = ["RetrosheetAdapter", "known_datasets"]
