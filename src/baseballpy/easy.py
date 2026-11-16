"""The Python interface for getting data (change ``easy-downloads``, ADR 144; it sits beside ``baseballpy.access``, not in ``ingest/``, because the ingest core must not import sources): the same work as the commands, in one call.

``download`` is ``baseballpy ingest``, ``update`` is ``baseballpy update`` and ``backfill`` is ``baseballpy backfill``.
Each one plans the jobs, checks the disk, runs them through the adapters (rate limits, retries, resume and the audit
log are the adapters' and the runner's), syncs the DuckDB views and returns the report, so the data can be read at once
with ``baseballpy.read`` or ``baseballpy.sql``::

    import baseballpy as bp
    bp.download("statcast", seasons="2023-2024")      # one source, some seasons
    bp.download("mlb_api", seasons=2024, datasets=["games"], sports="all")  # source options as keywords
    bp.update()                                       # this season of everything live
    bp.backfill("full", min_free_gb=20)               # a built-in plan, or the path of a plan file
    df = bp.read("statcast.pitches", seasons=2024)
"""

import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from baseballpy.core.config import LakeConfig
from baseballpy.database import sync_database
from baseballpy.ingest.adapters import IngestAdapter, get_adapters
from baseballpy.ingest.backfill import (
    BackfillPlan,
    BackfillReport,
    StageReport,
    load_plan,
    plan_stage,
    run_backfill,
    select_stages,
)
from baseballpy.ingest.runner import plan_jobs, run_jobs
from baseballpy.ingest.selection import parse_seasons
from baseballpy.ingest.types import JobStatus, RunReport, Selection
from baseballpy.sources.adapters import register_all_adapters


def free_disk_bytes(path: Path) -> int:
    """Free bytes on the drive that holds ``path`` (the nearest folder that exists, so a lake not yet made works)."""
    folder = path.resolve()
    while not folder.exists() and folder.parent != folder:
        folder = folder.parent
    return shutil.disk_usage(folder).free


def _adapters(
    sources: Iterable[str], given: Mapping[str, IngestAdapter] | None
) -> Mapping[str, IngestAdapter]:
    if given is not None:
        return given
    register_all_adapters()
    try:
        return get_adapters(sorted(set(sources)))
    except KeyError as exc:
        raise ValueError(exc.args[0]) from exc


def _sync(config: LakeConfig, results: Iterable[object], sync: bool) -> None:
    """Refresh the DuckDB views when something was stored, so a read or a query sees it at once."""
    if sync and any(getattr(r, "status", None) == JobStatus.COMPLETED for r in results):
        sync_database(cache_config=config)


def _season_text(seasons: int | str | Iterable[int] | None) -> str | None:
    if seasons is None:
        return None
    if isinstance(seasons, int):
        return str(seasons)
    if isinstance(seasons, str):
        return seasons
    return ",".join(str(int(s)) for s in seasons)


def download(
    source: str,
    seasons: int | str | Iterable[int] | None = None,
    datasets: Sequence[str] = (),
    *,
    refresh: bool = False,
    concurrency: int | str | None = 1,
    limit: int | None = None,
    config: LakeConfig | None = None,
    sync: bool = True,
    adapters: Mapping[str, IngestAdapter] | None = None,
    **options: str | int | float | bool,
) -> RunReport:
    """Download ``source`` (``statcast``, ``mlb_api``, ``retrosheet``, ``lahman``, ...) into the lake.

    ``seasons`` is a year, a list of years or the text the commands take (``"2015-2024"``, ``"2024,current"``,
    ``"all"``); the newest season goes first. ``datasets`` names datasets of the source (all default ones if empty).
    Keyword arguments are the source's switches, as ``baseballpy ingest --option name=value`` (for example
    ``sports="all"`` for the games of every level, or ``download="yes"`` for FanGraphs). What is already in the lake is
    skipped. The DuckDB views are synced afterwards. Returns the :class:`RunReport` (``.failed``, ``.exit_code``).
    """
    config = config or LakeConfig()
    chosen = _adapters([source], adapters)
    if source not in chosen:
        raise ValueError(f"unknown source {source!r}; known: {', '.join(sorted(chosen))}")
    adapter = chosen[source]
    text = _season_text(seasons)
    years = () if text is None else parse_seasons(text, all_seasons=adapter.all_seasons)
    pairs = tuple((name, _text(value)) for name, value in options.items())
    selection = Selection(
        seasons=tuple(sorted(years, reverse=True)),
        sources=(source,),
        datasets=tuple(datasets),
        refresh=refresh,
        limit=limit,
        options=pairs,
    )
    jobs = plan_jobs({source: adapter}, selection)
    report = run_jobs(jobs, chosen, refresh=refresh, concurrency=concurrency)
    _sync(config, report.results, sync)
    return report


def _text(value: str | int | float | bool) -> str:
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def backfill(
    plan: BackfillPlan | str | Path = "full",
    *,
    stages: Sequence[str] = (),
    max_gb: float | None = None,
    min_free_gb: float = 5.0,
    refresh: bool = False,
    concurrency: int = 1,
    dry_run: bool = False,
    on_stage: Callable[[StageReport], None] | None = None,
    config: LakeConfig | None = None,
    sync: bool = True,
    adapters: Mapping[str, IngestAdapter] | None = None,
    free_bytes: Callable[[], int] | None = None,
) -> BackfillReport:
    """Run a plan: stages of sources, seasons and datasets, with a disk guard, stage by stage.

    ``plan`` is a built-in name (``daily``, ``full``, ``minors``, ``minors-all``), the path of a TOML plan file or a
    :class:`BackfillPlan`. ``stages`` runs only the named stages. ``min_free_gb`` and ``max_gb`` stop the run before
    the disk fills; running the plan again resumes (finished work is skipped). ``dry_run`` plans and runs nothing: the
    report has each stage's planned job count. Raises :class:`BackfillError` when the plan does not fit the disk.
    """
    config = config or LakeConfig()
    chosen_plan = plan if isinstance(plan, BackfillPlan) else load_plan(plan)
    chosen_plan = select_stages(chosen_plan, stages)
    sources = sorted({s for stage in chosen_plan.stages for s in stage.sources})
    chosen = _adapters(sources, adapters)
    free = free_bytes or (lambda: free_disk_bytes(config.home))
    if dry_run:
        report = BackfillReport()
        for stage in chosen_plan.stages:
            jobs = plan_stage(stage, chosen, refresh=refresh)
            report.stages.append(StageReport(stage=stage, planned=len(jobs)))
        return report
    report = run_backfill(
        chosen_plan,
        chosen,
        free_bytes=free,
        max_gb=max_gb,
        min_free_gb=min_free_gb,
        refresh=refresh,
        concurrency=concurrency,
        on_stage=on_stage,
    )
    _sync(config, [r for s in report.stages for r in s.results], sync)
    return report


def update(
    *,
    max_gb: float | None = None,
    min_free_gb: float = 5.0,
    refresh: bool = False,
    concurrency: int = 1,
    dry_run: bool = False,
    config: LakeConfig | None = None,
    sync: bool = True,
    adapters: Mapping[str, IngestAdapter] | None = None,
    free_bytes: Callable[[], int] | None = None,
) -> BackfillReport:
    """Bring the lake up to date: this season of Statcast and the MLB API, and the live Kalshi and Polymarket markets.

    The built-in ``daily`` plan; a rerun fetches only what is new.
    """
    return backfill(
        "daily",
        max_gb=max_gb,
        min_free_gb=min_free_gb,
        refresh=refresh,
        concurrency=concurrency,
        dry_run=dry_run,
        config=config,
        sync=sync,
        adapters=adapters,
        free_bytes=free_bytes,
    )


__all__ = ["backfill", "download", "free_disk_bytes", "update"]
