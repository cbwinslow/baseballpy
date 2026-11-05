"""Statcast (Baseball Savant) ingest adapter."""

from collections.abc import Sequence
from typing import Any

from baseballpy.ingest.results import counts_to_result
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job
from baseballpy.sources.statcast.seasons import FIRST_MINORS_SEASON, FIRST_SEASON

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
        calendar: Any = None,
    ) -> None:
        self._calendar_override = calendar
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

    def _calendar(self) -> Any:
        """The MLB season calendar on the extractor's lake clock and HTTP client."""
        if self._calendar_override is not None:
            return self._calendar_override
        from baseballpy.core.season_calendar import SeasonCalendar

        extractor = self._get_extractor()
        return SeasonCalendar(extractor.cache_config, extractor.http)

    def all_seasons(self) -> Sequence[int]:
        """Statcast seasons from 2008 to the newest one that has started (ADR 66)."""
        return range(FIRST_SEASON, self._calendar().latest_started_season() + 1)

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
        season_param = job.param("season")
        if season_param is not None and (
            reason := self._calendar().not_started_reason(int(season_param))
        ):
            return _skipped(job, reason)
        runners = {
            "documents": self._run_documents,
            "pitches": self._run_pitches,
            "leaderboards": self._run_leaderboards,
            "game_feed": self._run_game_feed,
        }
        runner = runners.get(job.task)
        if runner is None:
            raise ValueError(f"unknown task {job.task!r} for statcast")
        return runner(job, refresh)

    def _run_documents(self, job: Job, refresh: bool) -> JobResult:
        kept = self._get_extractor().keep_documents(refresh=refresh)
        if not kept:
            return _skipped(job, "already kept")
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=len(kept))

    def _run_pitches(self, job: Job, refresh: bool) -> JobResult:
        season = _season_of(job)
        minors = bool(job.param("minors", False))
        report = self._get_extractor().ingest_season(season, refresh=refresh, minors=minors)
        if report.skipped_reason:
            return _skipped(job, report.skipped_reason)
        if report.chunks > 0 and report.chunks == report.cached_chunks:
            return _skipped(job, "already complete")
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=report.rows)

    def _run_leaderboards(self, job: Job, refresh: bool) -> JobResult:
        season = _season_of(job)
        reports = self._get_leaderboards().ingest_all(years=[season], refresh=refresh)
        counts: list[int | None] = []
        reasons: list[str] = []
        for r in reports:
            if season in r.seasons:
                counts.append(r.seasons[season])
            elif season in r.skipped:
                reasons.append(r.skipped[season])
        if not counts and reasons:
            return _skipped(job, sorted(reasons)[0])
        return counts_to_result(job, counts)

    def _run_game_feed(self, job: Job, refresh: bool) -> JobResult:
        season = _season_of(job)
        report = self._get_game_feed().ingest_season(season, max_games=job.limit, refresh=refresh)
        if report.skipped_reason:
            return _skipped(job, report.skipped_reason)
        if report.fetched == 0 and report.games > 0:
            return _skipped(job, "already complete")
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=report.fetched)


def _season_of(job: Job) -> int:
    """The job's ``season`` parameter; a job without one is a planning bug."""
    season = job.param("season")
    if season is None:
        raise ValueError(f"job {job.job_id} missing 'season' parameter")
    return int(season)


def _skipped(job: Job, detail: str) -> JobResult:
    return JobResult(job=job, status=JobStatus.SKIPPED, rows=None, detail=detail)


__all__ = ["StatcastAdapter"]
