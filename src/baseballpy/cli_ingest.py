"""CLI commands for unified ingestion, lake catalog inspection, and environment diagnosis."""

import importlib.metadata
import json
import os
import shutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import click
from pyarrow.parquet import ParquetFile
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.ingest.adapters import ADAPTERS, get_adapters
from baseballpy.ingest.runner import plan_jobs, run_jobs
from baseballpy.ingest.selection import parse_seasons
from baseballpy.ingest.types import Job, JobStatus, Selection
from baseballpy.probe import probe_cmd
from baseballpy.sources.adapters import register_all_adapters
from baseballpy.sources.catalog import register_all

console = Console()


@dataclass(frozen=True)
class DatasetStatus:
    """Status report for a registered dataset in the local lake."""

    source: str
    dataset: str
    status: str
    files: int
    rows: int
    seasons: tuple[int, ...]
    newest_mtime: str | None
    #: how ``ingest`` reaches the dataset (``IngestMode`` of its spec) and the registry's note
    ingest: str = "default"
    note: str = ""
    #: data-quality findings recorded in the processed manifest (finding -> count or message)
    quality: dict[str, object] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Alias for dataset name."""
        return self.dataset


def _quality_findings(config: LakeConfig, source: str, dataset: str) -> dict[str, object]:
    """The ``quality`` findings stored in a dataset's processed manifest (counts add up)."""
    findings: dict[str, object] = {}
    for entry in config.dataset_manifest(source, dataset).chunks().values():
        stored = entry.get("quality")
        if not isinstance(stored, dict):
            continue
        for key, value in stored.items():
            previous = findings.get(key)
            if isinstance(value, int) and isinstance(previous, int):
                findings[key] = previous + value
            else:
                findings[key] = value
    return findings


def scan_lake(config: LakeConfig | None = None) -> list[DatasetStatus]:
    """Scan the local lake processed directory for all registered datasets.

    No network calls are made. Inspects Parquet file footers for row counts without
    reading full record batches.

    Args:
        config: Optional lake configuration. If omitted, constructs a new LakeConfig.

    Returns:
        List of DatasetStatus instances for every registered dataset.
    """
    register_all()
    cfg = config if config is not None else LakeConfig()
    results: list[DatasetStatus] = []

    sorted_specs = sorted(DATASETS.values(), key=lambda d: (d.source, d.name))

    for spec in sorted_specs:
        target_dir = cfg.processed_dir(spec.source, spec.name)
        parquet_files: list[Path] = []
        if target_dir.is_dir():
            parquet_files = sorted(
                p
                for p in target_dir.rglob("*.parquet")
                if p.is_file() and not p.name.endswith(".part")
            )

        if not parquet_files:
            results.append(
                DatasetStatus(
                    source=spec.source,
                    dataset=spec.name,
                    status="MISSING",
                    files=0,
                    rows=0,
                    seasons=(),
                    newest_mtime=None,
                    ingest=spec.ingest,
                    note=spec.ingest_note,
                )
            )
            continue

        total_rows = sum(ParquetFile(p).metadata.num_rows for p in parquet_files)
        seasons_set = {
            int(part.split("=", 1)[1])
            for p in parquet_files
            for part in p.relative_to(target_dir).parts[:-1]
            if part.startswith("season=") and part.split("=", 1)[1].isdigit()
        }
        newest_ts = max(p.stat().st_mtime for p in parquet_files)
        newest_date_str = datetime.fromtimestamp(newest_ts, tz=UTC).strftime("%Y-%m-%d")
        num_files = len(parquet_files)

        results.append(
            DatasetStatus(
                source=spec.source,
                dataset=spec.name,
                status="INGESTED",
                files=num_files,
                rows=total_rows,
                seasons=tuple(sorted(seasons_set)),
                newest_mtime=newest_date_str,
                ingest=spec.ingest,
                note=spec.ingest_note,
                quality=_quality_findings(cfg, spec.source, spec.name),
            )
        )

    return results


def find_orphans(config: LakeConfig | None = None) -> list[Path]:
    """Find all orphan *.part files under raw and processed lake directories.

    Args:
        config: Optional lake configuration. If omitted, constructs a new LakeConfig.

    Returns:
        Sorted list of Path objects pointing to orphan *.part files.
    """
    cfg = config if config is not None else LakeConfig()
    orphans: set[Path] = set()
    for root in (cfg.raw_root, cfg.processed_root):
        if root.is_dir():
            for p in root.rglob("*.part"):
                if p.is_file():
                    orphans.add(p)
    return sorted(orphans)


def _pkg_version(name: str) -> str:
    """Safely resolve an installed package's version string."""
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def _disk_usage(path: Path) -> tuple[int, int]:
    """Return free and total disk space in bytes for the drive containing path."""
    curr = path.resolve()
    while not curr.exists() and curr.parent != curr:
        curr = curr.parent
    usage = shutil.disk_usage(curr)
    return usage.free, usage.total


def split_datasets(tokens: Sequence[str], sources: Sequence[str]) -> dict[str, tuple[str, ...]]:
    """Group ``--datasets`` tokens (``name`` or ``source:name``, comma-separated) by source.

    A bare name is only unambiguous with exactly one selected source; otherwise it must be
    written ``source:name``. A source named in a token but not selected is an error.
    """
    grouped: dict[str, list[str]] = {}
    for token in tokens:
        for raw in token.split(","):
            item = raw.strip()
            if not item:
                continue
            source, sep, name = item.partition(":")
            if not sep:
                if len(sources) != 1:
                    raise click.BadParameter(
                        f"dataset {item!r} is ambiguous with {len(sources)} sources; use source:name"
                    )
                source, name = sources[0], item
            if source not in sources:
                raise click.BadParameter(f"dataset {item!r} names a source that is not selected")
            grouped.setdefault(source, []).append(name)
    return {k: tuple(v) for k, v in grouped.items()}


@click.command("ingest")
@click.argument("sources", nargs=-1)
@click.option(
    "--seasons",
    "-s",
    type=str,
    default=None,
    help="Season expression (e.g. 2020, 2015-2024, or all).",
)
@click.option(
    "--datasets",
    "-d",
    "datasets",
    multiple=True,
    help="Dataset(s) to ingest: name (one source) or source:name (repeatable, comma-separated).",
)
@click.option(
    "--refresh",
    is_flag=True,
    help="Bypass local cache and force fresh download.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Plan jobs and print them without executing.",
)
@click.option(
    "--concurrency",
    "-c",
    type=click.IntRange(min=1),
    default=1,
    help="Max concurrent worker threads (minimum 1).",
)
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=None,
    help="Bound the per-game, per-player or per-game-feed fan-out of opt-in datasets (default: all).",
)
@click.option(
    "--stop-on-error",
    is_flag=True,
    help="Halt execution immediately when a job raises an error.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output results as newline-delimited JSON objects.",
)
@click.pass_context
def ingest_cmd(
    ctx: click.Context,
    sources: tuple[str, ...],
    seasons: str | None,
    datasets: tuple[str, ...],
    refresh: bool,
    dry_run: bool,
    concurrency: int,
    limit: int | None,
    stop_on_error: bool,
    as_json: bool,
) -> None:
    """Execute ingestion jobs across registered adapters with planning and concurrency."""
    register_all_adapters()

    target_sources = () if not sources or "all" in sources else tuple(sources)

    try:
        adapters = get_adapters(target_sources)
    except (ValueError, KeyError) as exc:
        raise click.BadParameter(str(exc)) from exc

    by_source = split_datasets(datasets, tuple(adapters))

    planned_jobs: list[Job] = []
    try:
        for source in sorted(adapters.keys()):
            adapter = adapters[source]
            if seasons is not None:
                parsed_seasons = parse_seasons(seasons, all_seasons=adapter.all_seasons)
            else:
                parsed_seasons = ()
            sel = Selection(
                seasons=parsed_seasons,
                sources=(source,),
                datasets=by_source.get(source, ()),
                refresh=refresh,
                limit=limit,
            )
            jobs = plan_jobs({source: adapter}, sel)
            planned_jobs.extend(jobs)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc

    if not planned_jobs:
        if not as_json:
            console.print("No jobs to run.")
        ctx.exit(0)

    if dry_run:
        if as_json:
            for job in planned_jobs:
                click.echo(
                    json.dumps(
                        {
                            "job_id": job.job_id,
                            "status": JobStatus.PLANNED.value,
                            "rows": None,
                            "seconds": 0.0,
                            "detail": "",
                            "error": None,
                        }
                    )
                )
        else:
            table = Table(title="Planned Ingest Jobs (Dry Run)")
            table.add_column("Source", style="cyan")
            table.add_column("Task")
            table.add_column("Params")
            table.add_column("Status")
            for job in planned_jobs:
                params_str = ", ".join(f"{k}={v}" for k, v in job.params)
                table.add_row(job.source, job.task, params_str, "[cyan]planned[/cyan]")
            console.print(table)
            console.print(f"Planned {len(planned_jobs)} job(s).")
        ctx.exit(0)

    report = run_jobs(
        planned_jobs,
        adapters,
        refresh=refresh,
        concurrency=concurrency,
        continue_on_error=not stop_on_error,
    )

    if as_json:
        for res in report.results:
            click.echo(
                json.dumps(
                    {
                        "job_id": res.job.job_id,
                        "status": res.status.value,
                        "rows": res.rows,
                        "seconds": res.seconds,
                        "detail": res.detail,
                        "error": res.error,
                    }
                )
            )
    else:
        table = Table(title="Ingest Results")
        table.add_column("Source", style="cyan")
        table.add_column("Task")
        table.add_column("Params")
        table.add_column("Status")
        table.add_column("Rows", justify="right")
        table.add_column("Seconds", justify="right")

        for res in report.results:
            params_str = ", ".join(f"{k}={v}" for k, v in res.job.params)
            rows_str = f"{res.rows:,}" if res.rows is not None else "-"
            status_styles = {
                JobStatus.COMPLETED: "bold green",
                JobStatus.SKIPPED: "yellow",
                JobStatus.FAILED: "bold red",
                JobStatus.CANCELLED: "red",
                JobStatus.PLANNED: "cyan",
            }
            style = status_styles.get(res.status, "white")
            table.add_row(
                res.job.source,
                res.job.task,
                params_str,
                f"[{style}]{res.status.value}[/{style}]",
                rows_str,
                f"{res.seconds:.2f}",
            )
        console.print(table)

        counts = report.counts()
        summary_parts = [f"{status}: {count}" for status, count in sorted(counts.items())]
        summary_str = ", ".join(summary_parts) if summary_parts else "0 jobs"
        console.print(f"Summary: {summary_str}")

    ctx.exit(report.exit_code)


@click.command("status")
@click.option(
    "--source",
    "sources",
    multiple=True,
    help="Filter by source (repeatable).",
)
@click.option(
    "--missing",
    is_flag=True,
    help="Show only MISSING datasets.",
)
@click.option(
    "--gaps",
    is_flag=True,
    help="Show only MISSING datasets that the default ingest selection should have filled.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print status as JSON lines (one object per dataset).",
)
@click.pass_context
def catalog_status_cmd(
    ctx: click.Context,
    sources: tuple[str, ...],
    missing: bool,
    gaps: bool,
    as_json: bool,
) -> None:
    """Inspect local lake processed Parquet datasets and reporting status.

    The Ingest column says why a dataset is not in the lake: opt_in and on_demand datasets need an
    option or an input, api_only ones are filled by the Python API, and a default dataset can be
    empty for a season the provider does not publish (its note says which).
    """
    config = LakeConfig()
    statuses = scan_lake(config)
    if sources:
        source_set = set(sources)
        statuses = [s for s in statuses if s.source in source_set]
    if missing or gaps:
        statuses = [s for s in statuses if s.status == "MISSING"]
    if gaps:
        statuses = [s for s in statuses if s.ingest == "default"]

    if as_json:
        for s in statuses:
            click.echo(
                json.dumps(
                    {
                        "source": s.source,
                        "dataset": s.dataset,
                        "status": s.status,
                        "files": s.files,
                        "rows": s.rows,
                        "seasons": list(s.seasons),
                        "newest_mtime": s.newest_mtime,
                        "ingest": s.ingest,
                        "note": s.note,
                        "quality": s.quality,
                    }
                )
            )
    else:
        table = Table(title="Catalog Status")
        table.add_column("Source", style="cyan")
        table.add_column("Dataset")
        table.add_column("Status", no_wrap=True)
        table.add_column("Files", justify="right")
        table.add_column("Rows", justify="right")
        table.add_column("Seasons")
        table.add_column("Newest", style="dim")
        table.add_column("Ingest", style="dim", no_wrap=True)
        if missing or gaps:
            table.add_column("Note", style="dim", overflow="fold")

        for s in statuses:
            status_style = "bold green" if s.status == "INGESTED" else "dim red"
            seasons_str = ", ".join(str(y) for y in s.seasons) if s.seasons else "-"
            table.add_row(
                s.source,
                s.dataset,
                f"[{status_style}]{s.status}[/{status_style}]",
                f"{s.files:,}" if s.files else "-",
                f"{s.rows:,}" if s.rows else "-",
                seasons_str,
                s.newest_mtime or "-",
                s.ingest,
                *([s.note or "-"] if missing or gaps else []),
            )
        console.print(table)
        for s in statuses:
            if s.quality:
                findings = "; ".join(f"{k}={v}" for k, v in s.quality.items())
                console.print(
                    f"  [yellow]data quality[/yellow] {s.source}.{s.dataset}: {findings}",
                    soft_wrap=True,
                )

    ctx.exit(0)


@click.command("doctor")
@click.option(
    "--clean",
    is_flag=True,
    help="Delete orphan .part files under raw and processed tiers.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print system and lake diagnosis as a JSON object.",
)
@click.pass_context
def doctor_cmd(
    ctx: click.Context,
    clean: bool,
    as_json: bool,
) -> None:
    """Diagnose data lake layout, disk usage, package versions, and orphan files."""
    register_all_adapters()
    register_all()

    config = LakeConfig()
    orphans = find_orphans(config)
    cleaned_count = 0

    if clean and orphans:
        for p in orphans:
            p.unlink()
            cleaned_count += 1

    free_bytes, total_bytes = _disk_usage(config.home)
    env_vars = {k: v for k, v in sorted(os.environ.items()) if k.startswith("BASEBALLPY_")}
    dataset_count = len(DATASETS)
    adapter_count = len(ADAPTERS)

    if as_json:
        doc_data = {
            "lake": {
                "home": str(config.home),
                "raw_root": str(config.raw_root),
                "processed_root": str(config.processed_root),
                "quarantine_root": str(config.quarantine_root),
                "http_cache_root": str(config.http_cache_root),
                "database_path": str(config.database_path),
            },
            "disk": {
                "free_bytes": free_bytes,
                "total_bytes": total_bytes,
            },
            "versions": {
                "python": sys.version.split()[0],
                "baseballpy": _pkg_version("baseballpy"),
                "pyarrow": _pkg_version("pyarrow"),
                "duckdb": _pkg_version("duckdb"),
            },
            "env": env_vars,
            "registered_datasets": dataset_count,
            "registered_adapters": adapter_count,
            "orphans": {
                "count": len(orphans),
                "samples": [str(p) for p in orphans[:20]],
                "cleaned": cleaned_count if clean else 0,
            },
        }
        click.echo(json.dumps(doc_data, indent=2))
    else:
        table = Table(title="baseballpy Doctor")
        table.add_column("Property", style="bold cyan")
        table.add_column("Value")

        table.add_row("Home", str(config.home))
        table.add_row("Raw root", str(config.raw_root))
        table.add_row("Processed root", str(config.processed_root))
        table.add_row("Quarantine root", str(config.quarantine_root))
        table.add_row("HTTP cache root", str(config.http_cache_root))
        table.add_row("Database path", str(config.database_path))

        free_gb = free_bytes / (1024**3)
        total_gb = total_bytes / (1024**3)
        table.add_row("Disk free", f"{free_gb:.1f} GB of {total_gb:.1f} GB")

        table.add_row("Python", sys.version.split()[0])
        table.add_row("pyarrow", _pkg_version("pyarrow"))
        table.add_row("duckdb", _pkg_version("duckdb"))
        table.add_row("baseballpy", _pkg_version("baseballpy"))

        table.add_row("Registered datasets", str(dataset_count))
        table.add_row("Registered adapters", str(adapter_count))

        if env_vars:
            env_str = ", ".join(f"{k}={v}" for k, v in env_vars.items())
            table.add_row("Environment", env_str)
        else:
            table.add_row("Environment", "(none)")

        if clean:
            table.add_row("Cleaned orphans", str(cleaned_count))
        else:
            table.add_row("Orphan .part files", str(len(orphans)))

        console.print(table)

        if clean and cleaned_count > 0:
            console.print(
                f"[green]Successfully deleted {cleaned_count} orphan .part file(s).[/green]"
            )

        if not clean and orphans:
            console.print(f"[bold red]Found {len(orphans)} orphan .part file(s):[/bold red]")
            for p in orphans[:20]:
                console.print(f"  [dim]{p}[/dim]")
            if len(orphans) > 20:
                console.print(f"  [dim]... and {len(orphans) - 20} more[/dim]")

    if orphans and not clean:
        ctx.exit(1)
    ctx.exit(0)


def register_commands(main: click.Group, catalog_group: click.Group) -> None:
    """Register ingest and doctor on main, and status on catalog_group.

    Args:
        main: Top-level Click command group.
        catalog_group: Catalog Click sub-command group.
    """
    main.add_command(ingest_cmd, "ingest")
    main.add_command(doctor_cmd, "doctor")
    main.add_command(probe_cmd, "probe")
    catalog_group.add_command(catalog_status_cmd, "status")


__all__ = [
    "DatasetStatus",
    "catalog_status_cmd",
    "doctor_cmd",
    "find_orphans",
    "ingest_cmd",
    "register_commands",
    "scan_lake",
]
