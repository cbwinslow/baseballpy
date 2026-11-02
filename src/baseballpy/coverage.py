"""Season-level expected vs. held coverage inspection and gap remediation."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for
from baseballpy.sources.catalog import register_all

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverageItem:
    """Expected vs held report for one entity or dataset family in a season."""

    source: str
    season: int
    entity: str
    expected_count: int
    held_count: int
    missing_count: int
    held_percent: float
    remediation_cmd: str
    missing_ids: tuple[Any, ...] = ()
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "source": self.source,
            "season": self.season,
            "entity": self.entity,
            "expected_count": self.expected_count,
            "held_count": self.held_count,
            "missing_count": self.missing_count,
            "held_percent": self.held_percent,
            "remediation_cmd": self.remediation_cmd,
            "missing_ids": list(self.missing_ids),
            "note": self.note,
        }


@dataclass
class SeasonCoverageReport:
    """Aggregate coverage report across sources for a season."""

    season: int
    items: list[CoverageItem] = field(default_factory=list)

    @property
    def total_expected(self) -> int:
        """Total expected entities."""
        return sum(item.expected_count for item in self.items)

    @property
    def total_held(self) -> int:
        """Total held entities."""
        return sum(item.held_count for item in self.items)

    @property
    def overall_percent(self) -> float:
        """Overall held percentage."""
        if self.total_expected == 0:
            return 100.0
        return round((self.total_held / self.total_expected) * 100.0, 1)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "season": self.season,
            "total_expected": self.total_expected,
            "total_held": self.total_held,
            "overall_percent": self.overall_percent,
            "items": [item.to_dict() for item in self.items],
        }


def check_mlb_games(season: int, config: LakeConfig) -> CoverageItem:
    """Inspect MLB Stats API scheduled vs held games for a season."""
    sched_dir = config.processed_dir("mlb_api", "schedule_hydrated", season)
    sched_files = sorted(sched_dir.glob("part-*.parquet")) if sched_dir.is_dir() else []
    expected_pks: set[int] = set()
    if sched_files:
        try:
            tbl = pa.concat_tables(
                [
                    pq.read_table(f, columns=["game_pk", "status_abstract_game_state"])
                    for f in sched_files
                ]
            )
            final_mask = [
                s == "Final" for s in tbl.column("status_abstract_game_state").to_pylist()
            ]
            pks = tbl.column("game_pk").to_pylist()
            expected_pks = {
                pk
                for pk, is_final in zip(pks, final_mask, strict=False)
                if is_final and pk is not None
            }
        except (pa.ArrowInvalid, OSError, ValueError, KeyError) as exc:
            logger.debug("could not read schedule_hydrated for %s: %s", season, exc)

    expected_count = len(expected_pks) if expected_pks else 2430

    box_dir = config.processed_dir("mlb_api", "game_boxscores", season)
    held_files = sorted(box_dir.glob("part-*.parquet")) if box_dir.is_dir() else []
    held_pks: set[int] = set()
    if held_files:
        try:
            tbl = pa.concat_tables([pq.read_table(f, columns=["game_pk"]) for f in held_files])
            held_pks = {pk for pk in tbl.column("game_pk").to_pylist() if pk is not None}
        except (pa.ArrowInvalid, OSError, ValueError, KeyError) as exc:
            logger.debug("could not read game_boxscores for %s: %s", season, exc)

    held_count = len(held_pks)
    missing = sorted(expected_pks - held_pks) if expected_pks else []
    missing_count = len(missing) if expected_pks else max(0, expected_count - held_count)
    pct = round((held_count / expected_count * 100.0), 1) if expected_count > 0 else 0.0

    cmd = (
        "(up to date)"
        if missing_count <= 0
        else f"baseballpy ingest mlb_api --seasons {season} -d games"
    )
    note = "" if expected_pks else "schedule not yet ingested, assuming 2,430 regular season games"

    return CoverageItem(
        source="mlb_api",
        season=season,
        entity="games (boxscores)",
        expected_count=expected_count,
        held_count=held_count,
        missing_count=missing_count,
        held_percent=min(pct, 100.0),
        remediation_cmd=cmd,
        missing_ids=tuple(missing[:50]),
        note=note,
    )


def check_retrosheet_games(season: int, config: LakeConfig) -> CoverageItem:
    """Inspect Retrosheet scheduled vs held games for a season."""
    gamelogs_dir = config.processed_dir("retrosheet", "gamelogs", season)
    gl_files = sorted(gamelogs_dir.glob("part-*.parquet")) if gamelogs_dir.is_dir() else []
    expected_count = 0
    if gl_files:
        try:
            for f in gl_files:
                expected_count += pq.ParquetFile(f).metadata.num_rows
        except (pa.ArrowInvalid, OSError, ValueError, KeyError) as exc:
            logger.debug("could not read gamelogs for %s: %s", season, exc)
    if expected_count == 0:
        expected_count = 2430

    box_dir = config.processed_dir("retrosheet", "box_games", season)
    box_files = sorted(box_dir.glob("part-*.parquet")) if box_dir.is_dir() else []
    held_count = 0
    if box_files:
        try:
            for f in box_files:
                held_count += pq.ParquetFile(f).metadata.num_rows
        except (pa.ArrowInvalid, OSError, ValueError, KeyError) as exc:
            logger.debug("could not read box_games for %s: %s", season, exc)

    missing_count = max(0, expected_count - held_count)
    pct = round((held_count / expected_count * 100.0), 1) if expected_count > 0 else 0.0
    cmd = (
        "(up to date)"
        if missing_count <= 0
        else f"baseballpy ingest retrosheet --seasons {season} -d events,boxscores"
    )
    note = "" if gl_files else "gamelogs not yet ingested, assuming 2,430 games"

    return CoverageItem(
        source="retrosheet",
        season=season,
        entity="games (box accounts)",
        expected_count=expected_count,
        held_count=held_count,
        missing_count=missing_count,
        held_percent=min(pct, 100.0),
        remediation_cmd=cmd,
        note=note,
    )


def check_statcast_pitches(season: int, config: LakeConfig) -> CoverageItem:
    """Inspect Statcast pitch chunk completeness for a season."""
    pitch_dir = config.processed_dir("statcast", "pitches", season)
    files = sorted(pitch_dir.glob("part-*.parquet")) if pitch_dir.is_dir() else []
    held_chunks = len(files)
    expected_chunks = 31 if season >= 2008 else 0
    pct = round((held_chunks / expected_chunks * 100.0), 1) if expected_chunks > 0 else 0.0
    missing_count = max(0, expected_chunks - held_chunks)
    cmd = "(up to date)" if missing_count <= 0 else f"baseballpy ingest statcast --seasons {season}"

    return CoverageItem(
        source="statcast",
        season=season,
        entity="pitch weekly chunks",
        expected_count=expected_chunks,
        held_count=held_chunks,
        missing_count=missing_count,
        held_percent=min(pct, 100.0),
        remediation_cmd=cmd,
    )


def check_dataset_tables(source: str, season: int, config: LakeConfig) -> CoverageItem:
    """Inspect registered dataset tables presence for a source and season."""
    register_all()
    specs = [s for s in datasets_for(source) if s.partition == "season"]
    expected_count = len(specs)
    held_count = 0
    missing_names: list[str] = []
    for s in specs:
        target_dir = config.processed_dir(source, s.name, season)
        if target_dir.is_dir() and any(target_dir.glob("part-*.parquet")):
            held_count += 1
        else:
            missing_names.append(s.name)

    missing_count = expected_count - held_count
    pct = round((held_count / expected_count * 100.0), 1) if expected_count > 0 else 0.0
    cmd = "(up to date)" if missing_count <= 0 else f"baseballpy ingest {source} --seasons {season}"

    return CoverageItem(
        source=source,
        season=season,
        entity="season datasets",
        expected_count=expected_count,
        held_count=held_count,
        missing_count=missing_count,
        held_percent=pct,
        remediation_cmd=cmd,
        missing_ids=tuple(missing_names[:20]),
    )


def audit_season_coverage(
    season: int | None = None,
    sources: Sequence[str] | None = None,
    config: LakeConfig | None = None,
) -> SeasonCoverageReport:
    """Audit expected vs held entities across sources for a season.

    Args:
        season: Year to inspect (defaults to current year).
        sources: Subset of sources to inspect (defaults to mlb_api, retrosheet, statcast).
        config: Optional lake configuration.

    Returns:
        SeasonCoverageReport with items per source and entity.
    """
    cfg = config or LakeConfig()
    target_season = season if season is not None else date.today().year
    wanted_sources = set(sources) if sources else {"mlb_api", "retrosheet", "statcast"}

    items: list[CoverageItem] = []
    if "mlb_api" in wanted_sources:
        items.append(check_mlb_games(target_season, cfg))
        items.append(check_dataset_tables("mlb_api", target_season, cfg))

    if "retrosheet" in wanted_sources:
        items.append(check_retrosheet_games(target_season, cfg))
        items.append(check_dataset_tables("retrosheet", target_season, cfg))

    if "statcast" in wanted_sources:
        items.append(check_statcast_pitches(target_season, cfg))
        items.append(check_dataset_tables("statcast", target_season, cfg))

    return SeasonCoverageReport(season=target_season, items=items)


def remediate_coverage_gaps(
    report: SeasonCoverageReport,
    config: LakeConfig | None = None,
    concurrency: int = 1,
) -> Any:
    """Execute remediation jobs for missing entities reported in SeasonCoverageReport."""
    from baseballpy.ingest.adapters import get_adapters
    from baseballpy.ingest.runner import plan_jobs, run_jobs
    from baseballpy.ingest.types import RunReport, Selection
    from baseballpy.sources.adapters import register_all_adapters

    register_all_adapters()

    all_jobs = []
    adapters_map = get_adapters()

    for item in report.items:
        if item.missing_count <= 0 or item.remediation_cmd == "(up to date)":
            continue

        datasets: tuple[str, ...] = ()
        if item.source == "mlb_api" and "games" in item.entity:
            datasets = ("games",)
        elif item.source == "retrosheet" and "games" in item.entity:
            datasets = ("events", "boxscores")

        sel = Selection(
            sources=(item.source,),
            seasons=(item.season,),
            datasets=datasets,
        )
        source_adapters = (
            {item.source: adapters_map[item.source]}
            if item.source in adapters_map
            else adapters_map
        )
        jobs = plan_jobs(source_adapters, sel)
        all_jobs.extend(jobs)

    if not all_jobs:
        return RunReport()

    seen: set[str] = set()
    unique_jobs = []
    for job in all_jobs:
        if job.job_id not in seen:
            seen.add(job.job_id)
            unique_jobs.append(job)

    return run_jobs(unique_jobs, adapters_map, concurrency=concurrency)


__all__ = [
    "CoverageItem",
    "SeasonCoverageReport",
    "audit_season_coverage",
    "check_dataset_tables",
    "check_mlb_games",
    "check_retrosheet_games",
    "check_statcast_pitches",
    "remediate_coverage_gaps",
]
