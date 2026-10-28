"""``baseballpy backfill``: run a plan file of ingest stages with a disk budget."""

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from baseballpy.cli_ingest import _disk_usage
from baseballpy.core.config import LakeConfig
from baseballpy.ingest.adapters import get_adapters
from baseballpy.ingest.backfill import (
    GB,
    BackfillError,
    BackfillPlan,
    StageReport,
    load_plan,
    plan_stage,
    run_backfill,
)
from baseballpy.ingest.types import JobStatus
from baseballpy.sources.adapters import register_all_adapters

console = Console()


def _print_plan(plan: BackfillPlan, counts: dict[str, int], free_bytes: int) -> None:
    table = Table(title="Backfill plan (dry run)")
    for column in ("Stage", "Sources", "Seasons", "Jobs", "Estimate GB"):
        table.add_column(column)
    for stage in plan.stages:
        table.add_row(
            stage.name,
            ", ".join(stage.sources),
            stage.seasons or "-",
            str(counts[stage.name]),
            f"{stage.estimate_gb:.1f}",
        )
    console.print(table)
    console.print(
        f"{sum(counts.values())} job(s); estimated {plan.estimate_gb:.1f} GB; "
        f"{free_bytes / GB:.1f} GB free."
    )


@click.command("backfill")
@click.argument("plan_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--max-gb",
    type=click.FloatRange(min=0, min_open=True),
    default=None,
    help="Stop when the lake has grown by this many GB (measured as the drop in free space).",
)
@click.option(
    "--min-free-gb",
    type=click.FloatRange(min=0),
    default=5.0,
    show_default=True,
    help="Refuse to start, and stop, when less than this much space would stay free.",
)
@click.option("--refresh", is_flag=True, help="Bypass local cache and force fresh download.")
@click.option("--dry-run", is_flag=True, help="Plan the jobs and the disk check; run nothing.")
@click.option(
    "--concurrency",
    "-c",
    type=click.IntRange(min=1),
    default=1,
    help="Max concurrent worker threads (minimum 1).",
)
@click.option("--json", "as_json", is_flag=True, help="Print one JSON object per stage.")
@click.pass_context
def backfill_cmd(
    ctx: click.Context,
    plan_file: Path,
    max_gb: float | None,
    min_free_gb: float,
    refresh: bool,
    dry_run: bool,
    concurrency: int,
    as_json: bool,
) -> None:
    """Run a TOML plan of ingest stages (sources, seasons, datasets) into the lake.

    Re-running the same plan resumes: the adapters skip every chunk that is already complete.
    """
    register_all_adapters()
    home = LakeConfig().home

    def free() -> int:
        return _disk_usage(home)[0]

    try:
        plan = load_plan(plan_file)
        sources = sorted({s for stage in plan.stages for s in stage.sources})
        adapters = get_adapters(sources)
        if dry_run:
            counts = {
                stage.name: len(plan_stage(stage, adapters, refresh=refresh))
                for stage in plan.stages
            }
            _print_plan(plan, counts, free())
            ctx.exit(0)

        def show(stage_report: StageReport) -> None:
            if as_json:
                click.echo(
                    json.dumps(
                        {
                            "stage": stage_report.stage.name,
                            "planned": stage_report.planned,
                            "completed": stage_report.count(JobStatus.COMPLETED),
                            "skipped": stage_report.count(JobStatus.SKIPPED),
                            "failed": stage_report.count(JobStatus.FAILED),
                            "cancelled": stage_report.count(JobStatus.CANCELLED),
                            "rows": stage_report.rows,
                            "bytes": stage_report.grown_bytes,
                            "seconds": round(stage_report.seconds, 1),
                        }
                    )
                )
            else:
                console.print(
                    f"[cyan]{stage_report.stage.name}[/cyan]: "
                    f"{stage_report.count(JobStatus.COMPLETED)} completed, "
                    f"{stage_report.count(JobStatus.SKIPPED)} skipped, "
                    f"{stage_report.count(JobStatus.FAILED)} failed of {stage_report.planned}; "
                    f"{stage_report.rows:,} rows, {stage_report.grown_bytes / GB:.2f} GB, "
                    f"{stage_report.seconds:.0f} s"
                )

        report = run_backfill(
            plan,
            adapters,
            free_bytes=free,
            max_gb=max_gb,
            min_free_gb=min_free_gb,
            refresh=refresh,
            concurrency=concurrency,
            on_stage=show,
        )
    except (BackfillError, ValueError, KeyError) as exc:
        raise click.ClickException(str(exc)) from exc

    if not as_json:
        console.print(f"Lake grew by {report.grown_bytes / GB:.2f} GB.")
        if report.stopped:
            console.print(
                f"[yellow]Stopped:[/yellow] {report.stopped}. Run the plan again to resume."
            )
    ctx.exit(report.exit_code)


def register_backfill_command(main: click.Group) -> None:
    """Add ``backfill`` to the top-level group."""
    main.add_command(backfill_cmd, "backfill")


__all__ = ["backfill_cmd", "register_backfill_command"]
