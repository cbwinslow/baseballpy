"""Backfill orchestration: a plan file of stages run through the ordinary ingest jobs.

A plan is TOML with one ``[[stage]]`` table per step::

    [[stage]]
    name = "reference tables"
    sources = ["lahman", "chadwick"]
    estimate_gb = 0.2

    [[stage]]
    name = "1990s"
    sources = ["retrosheet", "statcast"]
    seasons = "1990-1999"
    datasets = ["pitches"]      # optional; ``source:name`` when more than one source
    limit = 50                  # optional fan-out bound, as ``ingest --limit``
    estimate_gb = 12

Nothing here knows a source: stages become :class:`Selection` objects and the adapters plan and run
the jobs, so a finished chunk is skipped by the adapter on a re-run and a plan resumes by running
again. Disk use is measured as the drop in free space, because that is what the lake costs.
"""

import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from baseballpy.ingest.adapters import IngestAdapter
from baseballpy.ingest.runner import plan_jobs, run_jobs
from baseballpy.ingest.selection import parse_seasons
from baseballpy.ingest.types import Job, JobResult, JobStatus, Selection

GB = 1_000_000_000
_STAGE_KEYS = {"name", "sources", "seasons", "datasets", "limit", "estimate_gb"}


class BackfillError(ValueError):
    """The plan is malformed, or the run is refused before it starts."""


@dataclass(frozen=True)
class Stage:
    """One step of a backfill plan."""

    name: str
    sources: tuple[str, ...]
    seasons: str | None = None
    datasets: tuple[str, ...] = ()
    limit: int | None = None
    #: expected growth of the lake in GB, used by the free-space pre-flight
    estimate_gb: float = 0.0


@dataclass(frozen=True)
class BackfillPlan:
    """An ordered list of stages."""

    stages: tuple[Stage, ...]

    @property
    def estimate_gb(self) -> float:
        """Total expected growth of the lake."""
        return sum(s.estimate_gb for s in self.stages)


@dataclass
class StageReport:
    """What one stage did."""

    stage: Stage
    results: list[JobResult] = field(default_factory=list)
    planned: int = 0
    #: growth of the lake during the stage, measured as the drop in free space
    grown_bytes: int = 0

    def count(self, status: JobStatus) -> int:
        """Number of jobs of the stage that ended with ``status``."""
        return sum(1 for r in self.results if r.status == status)

    @property
    def rows(self) -> int:
        """Rows reported by the stage's jobs."""
        return sum(r.rows or 0 for r in self.results)

    @property
    def seconds(self) -> float:
        """Seconds spent by the stage's jobs."""
        return sum(r.seconds for r in self.results)


@dataclass
class BackfillReport:
    """The outcome of a run: per-stage results, disk growth and why it stopped (if early)."""

    stages: list[StageReport] = field(default_factory=list)
    grown_bytes: int = 0
    stopped: str = ""

    @property
    def exit_code(self) -> int:
        """130 when cancelled, 2 when stopped by a limit, 1 on a failed job, else 0."""
        results = [r for s in self.stages for r in s.results]
        if any(r.status == JobStatus.CANCELLED for r in results):
            return 130
        if self.stopped:
            return 2
        return 1 if any(r.status == JobStatus.FAILED for r in results) else 0


def load_plan(path: Path) -> BackfillPlan:
    """Read and validate a TOML plan file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise BackfillError(f"{path}: not valid TOML: {exc}") from exc
    return parse_plan(data)


def parse_plan(data: Mapping[str, Any]) -> BackfillPlan:
    """Validate a decoded plan (a mapping with a ``stage`` list)."""
    raw_stages = data.get("stage")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise BackfillError("a plan needs at least one [[stage]]")
    stages = []
    for index, raw in enumerate(raw_stages, start=1):
        unknown = set(raw) - _STAGE_KEYS
        if unknown:
            raise BackfillError(f"stage {index}: unknown key(s) {sorted(unknown)}")
        sources = tuple(raw.get("sources", ()))
        if not sources or not all(isinstance(s, str) for s in sources):
            raise BackfillError(f"stage {index}: `sources` must be a non-empty list of names")
        seasons = raw.get("seasons")
        if seasons is not None:
            try:
                parse_seasons(str(seasons), all_seasons=lambda: [2000])
            except ValueError as exc:
                raise BackfillError(f"stage {index}: {exc}") from exc
        limit = raw.get("limit")
        if limit is not None and (not isinstance(limit, int) or limit < 1):
            raise BackfillError(f"stage {index}: `limit` must be a positive integer")
        estimate = raw.get("estimate_gb", 0.0)
        if not isinstance(estimate, int | float) or estimate < 0:
            raise BackfillError(f"stage {index}: `estimate_gb` must be a number >= 0")
        stages.append(
            Stage(
                name=str(raw.get("name", f"stage {index}")),
                sources=sources,
                seasons=None if seasons is None else str(seasons),
                datasets=tuple(raw.get("datasets", ())),
                limit=limit,
                estimate_gb=float(estimate),
            )
        )
    return BackfillPlan(tuple(stages))


def _datasets_for(stage: Stage, source: str) -> tuple[str, ...]:
    """The stage's ``datasets`` that belong to ``source`` (``source:name`` or a bare name)."""
    names = []
    for item in stage.datasets:
        owner, sep, name = item.partition(":")
        if not sep:
            if len(stage.sources) != 1:
                raise BackfillError(
                    f"stage {stage.name!r}: dataset {item!r} is ambiguous; use source:name"
                )
            owner, name = stage.sources[0], item
        if owner not in stage.sources:
            raise BackfillError(
                f"stage {stage.name!r}: dataset {item!r} names an unselected source"
            )
        if owner == source:
            names.append(name)
    return tuple(names)


def plan_stage(stage: Stage, adapters: Mapping[str, IngestAdapter], *, refresh: bool) -> list[Job]:
    """The jobs of one stage, planned by the adapters of its sources."""
    jobs: list[Job] = []
    for source in stage.sources:
        adapter = adapters.get(source)
        if adapter is None:
            raise BackfillError(f"stage {stage.name!r}: unknown source {source!r}")
        seasons = (
            ()
            if stage.seasons is None
            else parse_seasons(stage.seasons, all_seasons=adapter.all_seasons)
        )
        selection = Selection(
            seasons=seasons,
            sources=(source,),
            datasets=_datasets_for(stage, source),
            refresh=refresh,
            limit=stage.limit,
        )
        jobs.extend(plan_jobs({source: adapter}, selection))
    return jobs


def preflight(plan: BackfillPlan, free_bytes: int, *, min_free_gb: float) -> None:
    """Refuse a plan whose estimate would leave less than ``min_free_gb`` free."""
    need = plan.estimate_gb * GB + min_free_gb * GB
    if need > free_bytes:
        raise BackfillError(
            f"not enough free space: plan estimates {plan.estimate_gb:.1f} GB and "
            f"{min_free_gb:.1f} GB must stay free, but only {free_bytes / GB:.1f} GB is free"
        )


def run_backfill(
    plan: BackfillPlan,
    adapters: Mapping[str, IngestAdapter],
    *,
    free_bytes: Callable[[], int],
    max_gb: float | None = None,
    min_free_gb: float = 5.0,
    refresh: bool = False,
    concurrency: int = 1,
    on_stage: Callable[[StageReport], None] | None = None,
) -> BackfillReport:
    """Run the plan stage by stage; stop early when the lake has grown by ``max_gb``.

    Raises :class:`BackfillError` before anything runs when the free-space pre-flight or the
    planning fails. Jobs run in batches of ``concurrency``; the growth is checked between batches,
    so a run can overshoot ``max_gb`` by at most one batch. A cancelled batch (Ctrl-C) ends the run.
    """
    start_free = free_bytes()
    preflight(plan, start_free, min_free_gb=min_free_gb)
    planned = [(stage, plan_stage(stage, adapters, refresh=refresh)) for stage in plan.stages]
    report = BackfillReport()
    for stage, jobs in planned:
        stage_report = StageReport(stage=stage, planned=len(jobs))
        stage_start_free = free_bytes()
        report.stages.append(stage_report)
        for offset in range(0, len(jobs), concurrency):
            report.grown_bytes = max(0, start_free - free_bytes())
            if max_gb is not None and report.grown_bytes > max_gb * GB:
                report.stopped = f"--max-gb {max_gb:g} reached in stage {stage.name!r}"
                break
            if free_bytes() < min_free_gb * GB:
                report.stopped = f"free space fell below {min_free_gb:g} GB in {stage.name!r}"
                break
            batch = run_jobs(
                jobs[offset : offset + concurrency],
                adapters,
                refresh=refresh,
                concurrency=concurrency,
            )
            stage_report.results.extend(batch.results)
            if batch.cancelled:
                report.stopped = "interrupted"
                break
        stage_report.grown_bytes = max(0, stage_start_free - free_bytes())
        if on_stage is not None:
            on_stage(stage_report)
        if report.stopped:
            break
    report.grown_bytes = max(0, start_free - free_bytes())
    return report


__all__ = [
    "BackfillError",
    "BackfillPlan",
    "BackfillReport",
    "Stage",
    "StageReport",
    "load_plan",
    "parse_plan",
    "plan_stage",
    "preflight",
    "run_backfill",
]
