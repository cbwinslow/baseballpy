"""Statcast (Baseball Savant) ingest adapter."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job

FIRST_SEASON = 2008
FIRST_MINORS_SEASON = 2021
KNOWN_DATASETS = {"pitches", "pitches_minors", "leaderboards", "game_feed", "documents"}
DEFAULT_DATASETS = ("pitches", "pitches_minors", "leaderboards", "documents")


class StatcastAdapter:
    """IngestAdapter wrapping Statcast extractor, leaderboards, and game feed."""

    source = "statcast"

    def __init__(
        self,
        extractor: Any = None,
        leaderboards: Any = None,
        game_feed: Any = None,
    ) -> None:
        self._extractor = extractor
        self._leaderboards = leaderboards
        self._game_feed = game_feed

    def _get_extractor(self) -> Any:
        if self._extractor is None:
            from baseballpy.sources.statcast.extractor import StatcastExtractor

            self._extractor = StatcastExtractor()
        return self._extractor

    def _get_leaderboards(self) -> Any:
        if self._leaderboards is None:
            from baseballpy.sources.statcast.leaderboards import StatcastLeaderboardExtractor

            self._leaderboards = StatcastLeaderboardExtractor()
        return self._leaderboards

    def _get_game_feed(self) -> Any:
        if self._game_feed is None:
            from baseballpy.sources.statcast.game_feed import StatcastGameFeed

            self._game_feed = StatcastGameFeed()
        return self._game_feed

    def all_seasons(self) -> Sequence[int]:
        """All available seasons for Statcast (2008 to current year)."""
        return range(FIRST_SEASON, datetime.now().year + 1)

    def plan(self, selection: Selection) -> list[Job]:
        """Generate planned jobs matching the given selection."""
        if selection.datasets:
            unknown = [d for d in selection.datasets if d not in KNOWN_DATASETS]
            if unknown:
                raise ValueError(
                    f"unknown dataset(s) for statcast: {unknown}; known: {sorted(KNOWN_DATASETS)}"
                )
            wanted = set(selection.datasets)
        else:
            wanted = set(DEFAULT_DATASETS)

        if not selection.seasons:
            return []

        jobs: list[Job] = []
        if "documents" in wanted:
            jobs.append(make_job("statcast", "documents"))
        for season in selection.seasons:
            if "pitches" in wanted:
                jobs.append(make_job("statcast", "pitches", season=season))
            if "pitches_minors" in wanted and season >= FIRST_MINORS_SEASON:
                jobs.append(make_job("statcast", "pitches", minors=True, season=season))
            if "leaderboards" in wanted:
                jobs.append(make_job("statcast", "leaderboards", season=season))
            if "game_feed" in wanted:
                jobs.append(
                    make_job("statcast", "game_feed", season=season, **selection.limit_params())
                )
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a single Statcast ingest job."""
        if job.task == "documents":
            kept = self._get_extractor().keep_documents(refresh=refresh)
            if not kept:
                return JobResult(
                    job=job, status=JobStatus.SKIPPED, rows=None, detail="already kept"
                )
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=len(kept))

        if job.task == "pitches":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            minors = bool(job.param("minors", False))
            report = self._get_extractor().ingest_season(season, refresh=refresh, minors=minors)
            if report.skipped_reason:
                return JobResult(
                    job=job,
                    status=JobStatus.SKIPPED,
                    rows=None,
                    detail=report.skipped_reason,
                )
            if report.chunks > 0 and report.chunks == report.cached_chunks:
                return JobResult(
                    job=job,
                    status=JobStatus.SKIPPED,
                    rows=None,
                    detail="already complete",
                )
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=report.rows)

        if job.task == "leaderboards":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            reports = self._get_leaderboards().ingest_all(years=[season], refresh=refresh)
            counts: list[int | None] = []
            for r in reports:
                if season in r.seasons:
                    counts.append(r.seasons[season])
            return counts_to_result(job, counts)

        if job.task == "game_feed":
            season_val = job.param("season")
            if season_val is None:
                raise ValueError(f"job {job.job_id} missing 'season' parameter")
            season = int(season_val)
            report = self._get_game_feed().ingest_season(
                season, max_games=job.limit, refresh=refresh
            )
            if report.fetched == 0 and report.games > 0:
                return JobResult(
                    job=job,
                    status=JobStatus.SKIPPED,
                    rows=None,
                    detail="already complete",
                )
            return JobResult(job=job, status=JobStatus.COMPLETED, rows=report.fetched)

        raise ValueError(f"unknown task {job.task!r} for statcast")


__all__ = ["StatcastAdapter"]
