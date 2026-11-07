"""Polymarket ingest adapter: one catalog job, and one price job per market start date."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection, make_job, with_needs
from baseballpy.sources.polymarket.endpoints import CATALOG_DATASETS, PRICE_DATASETS
from baseballpy.sources.polymarket.ingest import IngestOutcome
from baseballpy.sources.polymarket.price_ingest import DayOutcome

if TYPE_CHECKING:
    from baseballpy.sources.polymarket.price_ingest import MarketRow

CatalogLoader = Callable[[Sequence[str] | None], IngestOutcome]
#: ``day_runner(day, force)`` makes one start date's price history current
DayRunner = Callable[[str, bool], DayOutcome]
#: the start dates that have traded markets in the catalog, newest first
DaysSource = Callable[[], list[str]]

CATALOG_TASK = "catalog"
PRICES_TASK = "prices"


def _default_catalog(datasets: Sequence[str] | None) -> IngestOutcome:
    from baseballpy.sources.polymarket.ingest import ingest

    return ingest(datasets)


def _dataset_names() -> list[str]:
    from baseballpy.sources.polymarket.ingest import dataset_names

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
                from baseballpy.sources.polymarket.price_ingest import traded_markets

                self._markets = traded_markets(ProcessedStore(LakeConfig()))
            return self._markets

    def days(self) -> list[str]:
        from baseballpy.sources.polymarket.price_ingest import plan_days

        return plan_days(self.markets())

    def run(self, day: str, force: bool) -> DayOutcome:
        from baseballpy.core.config import LakeConfig
        from baseballpy.sources.polymarket.extractor import PolymarketExtractor
        from baseballpy.sources.polymarket.normalizer import PolymarketNormalizer
        from baseballpy.sources.polymarket.price_ingest import ingest_day

        config = LakeConfig()
        return ingest_day(
            day,
            self.markets(),
            config=config,
            extractor=PolymarketExtractor(cache_config=config),
            normalizer=PolymarketNormalizer(),
            force=force,
        )


class PolymarketAdapter:
    """IngestAdapter for Polymarket: season-less, so seasons in the selection are ignored.

    ``events``, ``markets`` and ``outcomes`` are one ``catalog`` job. ``prices`` is large and
    opt-in: one ``prices`` job per market start date (newest first, ``--limit`` keeps only the
    newest dates), planned from the catalog already in the lake. Threads and request limits come
    from the shared HTTP client and the worker pool of the runner.
    """

    source = "polymarket"

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
        """Polymarket has no seasons."""
        return []

    def plan(self, selection: Selection) -> list[Job]:
        """The catalog job (if wanted), then one job per start date for the price history."""
        names = _dataset_names()
        unknown = [d for d in selection.datasets if d not in names]
        if unknown:
            raise ValueError(f"unknown dataset(s) for polymarket: {unknown}; known: {names}")
        wanted = list(selection.datasets) or list(CATALOG_DATASETS)
        catalog = [d for d in CATALOG_DATASETS if d in wanted]
        prices = [d for d in PRICE_DATASETS if d in wanted]
        jobs: list[Job] = []
        catalog_job: Job | None = None
        if catalog:
            subset = {} if catalog == list(CATALOG_DATASETS) else {"datasets": ",".join(catalog)}
            catalog_job = make_job(self.source, CATALOG_TASK, **subset)
            jobs.append(catalog_job)
        if prices:
            days = self._days()
            if not days:
                raise ValueError(
                    "no traded markets in the catalog yet: run `baseballpy ingest polymarket` first"
                )
            if selection.limit is not None:
                days = days[: selection.limit]
            needs = (catalog_job.job_id,) if catalog_job is not None else ()
            for day in days:
                jobs.append(with_needs(make_job(self.source, PRICES_TASK, day=day), needs))
        return jobs

    def run(self, job: Job, *, refresh: bool = False) -> JobResult:
        """Execute a catalog job or one start date's job (``refresh`` fetches the date again)."""
        if job.task == CATALOG_TASK:
            chosen = job.param("datasets")
            outcome = self._loader(str(chosen).split(",") if chosen else None)
            return JobResult(
                job=job,
                status=JobStatus.COMPLETED,
                rows=sum(outcome.rows.values()),
                detail=f"{outcome.events} events; "
                + ", ".join(f"{name}={count}" for name, count in outcome.rows.items()),
            )
        if job.task == PRICES_TASK:
            result = self._day_runner(str(job.param("day")), refresh)
            return JobResult(
                job=job,
                status=JobStatus.COMPLETED,
                rows=sum(result.rows.values()),
                detail=f"{result.markets} markets; "
                + ", ".join(f"{name}={count}" for name, count in result.rows.items()),
                cache_hit=result.cached,
            )
        raise ValueError(f"unknown task {job.task!r} for polymarket")


__all__ = ["CATALOG_TASK", "PRICES_TASK", "PolymarketAdapter"]
