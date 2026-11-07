"""FanGraphs ingest adapter: type the files you supplied, or (with ``-o download=yes``) download.

* Default: one ``inbox`` job types the files in ``inbox/fangraphs/`` (no request to any host).
* ``--option download=yes``: leaderboards (batting, pitching, fielding) are downloaded one season per
  job (``--seasons``, default the current season) and projections one system and stat group per job,
  from FanGraphs' own website API, slowly and honestly (see ``extractor.py``).
"""

import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job
from baseballpy.sources.fangraphs.web import (
    FIRST_SEASON,
    LEADERBOARDS,
    PRESEASON_SYSTEMS,
    PROJECTION_GROUPS,
    ROS_SYSTEMS,
    current_season,
)

if TYPE_CHECKING:
    from baseballpy.sources.fangraphs.download import DownloadOutcome
    from baseballpy.sources.fangraphs.extractor import FangraphsWeb
    from baseballpy.sources.fangraphs.ingest import IngestOutcome

#: ``loader(datasets, refresh)`` makes the inbox files current and says what it did per dataset.
Loader = Callable[[Sequence[str] | None, bool], "IngestOutcome"]
#: ``downloader(job, refresh)`` runs one download job
Downloader = Callable[[Job, bool], "DownloadOutcome"]

INBOX_TASK = "inbox"
SEASON_TASK = "season"
PROJECTION_TASK = "projection"
DOWNLOADABLE = (*LEADERBOARDS, "projection")


def _default_loader(datasets: Sequence[str] | None, refresh: bool) -> "IngestOutcome":
    from baseballpy.sources.fangraphs.ingest import ingest

    return ingest(datasets, refresh=refresh)


def _dataset_names() -> list[str]:
    from baseballpy.sources.fangraphs.ingest import dataset_names

    return dataset_names()


class _Web:
    """One web client per process, made on first use (so planning needs no network or lake)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._web: FangraphsWeb | None = None

    def run(self, job: Job, refresh: bool) -> "DownloadOutcome":
        from baseballpy.core.config import LakeConfig
        from baseballpy.sources.fangraphs.download import download_projection, download_season
        from baseballpy.sources.fangraphs.extractor import FangraphsWeb
        from baseballpy.sources.fangraphs.normalizer import FangraphsNormalizer

        config = LakeConfig()
        with self._lock:
            web = self._web = self._web or FangraphsWeb(config)
        normalizer = FangraphsNormalizer()
        if job.task == SEASON_TASK:
            return download_season(
                str(job.param("dataset")),
                int(job.param("season") or 0),
                config=config,
                web=web,
                normalizer=normalizer,
                force=refresh,
            )
        return download_projection(
            str(job.param("system")),
            str(job.param("group")),
            config=config,
            web=web,
            normalizer=normalizer,
        )


class FangraphsAdapter:
    """IngestAdapter for FanGraphs: the inbox files by default, downloads on request."""

    source = "fangraphs"

    def __init__(self, loader: Loader | None = None, downloader: Downloader | None = None) -> None:
        self._loader = loader or _default_loader
        self._downloader = downloader or _Web().run

    def all_seasons(self) -> Sequence[int]:
        """Every season the leaderboards serve, 1871 to this year (used by ``--seasons all``)."""
        return list(range(FIRST_SEASON, current_season() + 1))

    def plan(self, selection: Selection) -> list[Job]:
        """Inbox job by default; download jobs with ``-o download=yes``."""
        names = _dataset_names()
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for fangraphs: {unknown}; known: {names}")
        if not selection.flag("download"):
            if not selection.datasets:
                return [make_job(self.source, INBOX_TASK)]
            chosen = [d for d in names if d in selection.datasets]
            return [make_job(self.source, INBOX_TASK, datasets=",".join(chosen))]
        wanted = [d for d in (selection.datasets or DOWNLOADABLE) if d in names]
        blocked = [d for d in wanted if d not in DOWNLOADABLE]
        if blocked:
            raise ValueError(
                f"no downloader for fangraphs {blocked}; downloadable: {list(DOWNLOADABLE)} "
                "(the other datasets are typed from files in inbox/fangraphs)"
            )
        jobs: list[Job] = []
        seasons = list(selection.seasons) or [current_season()]
        for dataset in wanted:
            if dataset == "projection":
                jobs += [
                    make_job(self.source, PROJECTION_TASK, system=system, group=group)
                    for system in (*PRESEASON_SYSTEMS, *ROS_SYSTEMS)
                    for group in PROJECTION_GROUPS
                ]
            else:
                jobs += [
                    make_job(self.source, SEASON_TASK, dataset=dataset, season=season)
                    for season in sorted(seasons, reverse=True)
                ]
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute an inbox job or one download job."""
        if job.task == INBOX_TASK:
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
        if job.task in (SEASON_TASK, PROJECTION_TASK):
            result = self._downloader(job, refresh)
            return JobResult(
                job=job,
                status=JobStatus.COMPLETED,
                rows=sum(result.rows.values()),
                detail=result.detail,
                cache_hit=result.cached,
            )
        raise ValueError(f"unknown task {job.task!r} for fangraphs")


__all__ = ["DOWNLOADABLE", "FangraphsAdapter"]
