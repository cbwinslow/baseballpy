"""Kalshi ingest adapter: one catalog job, and one job per close date for trades and candlesticks."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job, with_needs
from baseballpy.sources.kalshi.day_ingest import DayOutcome
from baseballpy.sources.kalshi.endpoints import CATALOG_DATASETS, MARKET_DATASETS
from baseballpy.sources.kalshi.ingest import IngestOutcome

if TYPE_CHECKING:
    from baseballpy.sources.kalshi.market_data import MarketRow

CatalogLoader = Callable[[Sequence[str] | None], IngestOutcome]
#: ``day_runner(day, datasets, force)`` makes one close date's datasets current
DayRunner = Callable[[str, Sequence[str], bool], DayOutcome]
#: the close dates that have traded markets in the catalog, newest first
DaysSource = Callable[[], list[str]]

CATALOG_TASK = "catalog"
MARKET_TASK = "market_data"


def _default_catalog(datasets: Sequence[str] | None) -> IngestOutcome:
    from baseballpy.sources.kalshi.ingest import ingest

    return ingest(datasets)


def _dataset_names() -> list[str]:
    from baseballpy.sources.kalshi.ingest import dataset_names

    return dataset_names()


class _LakeDays:
    """Reads the catalog's traded markets from the lake once per process (not once per job)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._markets: list[MarketRow] | None = None

    def markets(self) -> list[MarketRow]:
        with self._lock:
            if self._markets is None:
                from baseballpy.core.config import LakeConfig
                from baseballpy.core.stores import ProcessedStore
                from baseballpy.sources.kalshi.day_ingest import traded_markets

                self._markets = traded_markets(ProcessedStore(LakeConfig()))
            return self._markets

    def days(self) -> list[str]:
        from baseballpy.sources.kalshi.day_ingest import plan_days

        return plan_days(self.markets())

    def run(self, day: str, datasets: Sequence[str], force: bool) -> DayOutcome:
        from baseballpy.core.config import LakeConfig
        from baseballpy.core.http import get_http_client
        from baseballpy.sources.kalshi.day_ingest import ingest_day
        from baseballpy.sources.kalshi.market_data import KalshiMarketData
        from baseballpy.sources.kalshi.normalizer import KalshiNormalizer
        from baseballpy.sources.kalshi.signing import sign_with_environment

        http = get_http_client()
        sign_with_environment(http)
        return ingest_day(
            day,
            datasets,
            self.markets(),
            config=LakeConfig(),
            data=KalshiMarketData(http),
            normalizer=KalshiNormalizer(),
            force=force,
        )


class KalshiAdapter:
    """IngestAdapter for Kalshi: season-less, so seasons in the selection are ignored.

    ``series``, ``events`` and ``markets`` are one ``catalog`` job. ``trades`` and ``candlesticks``
    are large and opt-in: one ``market_data`` job per close date (newest first, ``--limit`` keeps
    only the newest dates), planned from the catalog already in the lake. Threads and request limits
    come from the shared HTTP client and the worker pool of the runner.
    """

    source = "kalshi"

    def __init__(
        self,
        loader: CatalogLoader | None = None,
        days: DaysSource | None = None,
        day_runner: DayRunner | None = None,
    ) -> None:
        lake = _LakeDays()
        self._loader = loader or _default_catalog
        self._days = days or lake.days
        self._day_runner = day_runner or lake.run

    def all_seasons(self) -> Sequence[int]:
        """Kalshi has no seasons."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """The catalog job (if wanted), then one job per close date for the per-market datasets."""
        names = _dataset_names()
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for kalshi: {unknown}; known: {names}")
        wanted = list(selection.datasets) or list(CATALOG_DATASETS)
        catalog = [d for d in CATALOG_DATASETS if d in wanted]
        market = [d for d in MARKET_DATASETS if d in wanted]
        jobs: list[Job] = []
        catalog_job: Job | None = None
        if catalog:
            subset = {} if catalog == list(CATALOG_DATASETS) else {"datasets": ",".join(catalog)}
            catalog_job = make_job(self.source, CATALOG_TASK, **subset)
            jobs.append(catalog_job)
        if market:
            days = self._days()
            if not days:
                raise ValueError(
                    "no traded markets in the catalog yet: run `baseballpy ingest kalshi` first"
                )
            if selection.limit is not None:
                days = days[: selection.limit]
            needs = (catalog_job.job_id,) if catalog_job is not None else ()
            for day in days:
                job = make_job(self.source, MARKET_TASK, day=day, datasets=",".join(market))
                jobs.append(with_needs(job, needs))
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a catalog job or one close date's job (``refresh`` fetches the date again)."""
        if job.task == CATALOG_TASK:
            chosen = job.param("datasets")
            outcome = self._loader(str(chosen).split(",") if chosen else None)
            return JobResult(
                job=job,
                status=JobStatus.COMPLETED,
                rows=sum(outcome.rows.values()),
                detail=f"{outcome.series} series; "
                + ", ".join(f"{name}={count}" for name, count in outcome.rows.items()),
            )
        if job.task == MARKET_TASK:
            day = str(job.param("day"))
            datasets = str(job.param("datasets") or ",".join(MARKET_DATASETS)).split(",")
            result = self._day_runner(day, datasets, refresh)
            return JobResult(
                job=job,
                status=JobStatus.COMPLETED,
                rows=sum(result.rows.values()),
                detail=f"{result.markets} markets; "
                + ", ".join(f"{name}={count}" for name, count in result.rows.items()),
                cache_hit=result.cached,
            )
        raise ValueError(f"unknown task {job.task!r} for kalshi")


__all__ = ["CATALOG_TASK", "MARKET_TASK", "KalshiAdapter"]
