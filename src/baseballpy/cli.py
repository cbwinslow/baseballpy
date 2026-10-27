"""Command-line interface for baseballpy."""

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig
from baseballpy.core.migrate import migrate_layout
from baseballpy.core.sources_lock import ENV_OVERRIDES, get_source_ref, load_lock, update_lock
from baseballpy.database import BaseballDatabase
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sources.statcast.extractor import StatcastExtractor

console = Console()


DATA_LICENSE_SUMMARY = """baseballpy is GPL-3.0-or-later and ships no data. Upstream terms apply to downloaded data:
  MLB / Statcast / Stats API : MLBAM copyright notice (non-commercial, non-bulk) http://gdx.mlb.com/components/copyright.txt
  Retrosheet                 : attribution required; https://www.retrosheet.org
  Lahman Database            : (c) SABR / Sean Lahman; https://sabr.org/lahman-database/
  Chadwick Register          : ODC-By 1.0; http://opendatacommons.org/licenses/by/1.0/
Details: docs/DATA_LICENSES.md"""


def _print_licenses(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if value and not ctx.resilient_parsing:
        click.echo(DATA_LICENSE_SUMMARY)
        ctx.exit()


@click.group()
@click.version_option()
@click.option(
    "--licenses",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_licenses,
    help="Show the license/attribution terms of the upstream data sources and exit.",
)
def main() -> None:
    """baseballpy: Fast, modular, and strongly-typed baseball data ingestion layer."""
    pass


@main.command("statcast")
@click.option("--start", "-s", type=str, required=True, help="Start date (YYYY-MM-DD)")
@click.option("--end", "-e", type=str, required=True, help="End date (YYYY-MM-DD)")
@click.option(
    "--destination", "-d", type=str, default="baseball.duckdb", help="Target destination path"
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["duckdb", "parquet"]),
    default="duckdb",
    help="Output format",
)
@click.option("--table", "-t", type=str, default="statcast_pitches", help="DuckDB table name")
@click.option("--refresh", is_flag=True, help="Bypass local cache and force fresh download")
def statcast_cmd(
    start: str, end: str, destination: str, format: str, table: str, refresh: bool
) -> None:
    """Download Statcast pitch-level tracking data with chunking and rate limits."""
    console.print(
        f"[bold green]baseballpy[/bold green] - Fetching Statcast from [cyan]{start}[/cyan] to [cyan]{end}[/cyan]"
    )
    extractor = StatcastExtractor()
    arrow_table = extractor.extract(start_date=start, end_date=end, refresh=refresh)
    console.print(f"Extracted [bold]{len(arrow_table):,}[/bold] pitch records.")

    if format == "duckdb":
        sink = DuckDBSink()
        written = sink.write(arrow_table, destination=destination, table_name=table)
        console.print(
            f"Loaded [bold green]{written:,}[/bold green] rows into DuckDB [yellow]{destination}[/yellow] table [cyan]{table}[/cyan]."
        )
    elif format == "parquet":
        psink = ParquetSink()
        written = psink.write(arrow_table, destination=destination)
        console.print(
            f"Wrote [bold green]{written:,}[/bold green] rows to Parquet file [yellow]{destination}[/yellow]."
        )


@main.command("migrate-layout")
@click.option("--dry-run", is_flag=True, help="Print the plan without touching any file.")
@click.option(
    "--delete-old",
    is_flag=True,
    help="Delete migrated v1 files after verification (unknown files are never touched).",
)
def migrate_layout_cmd(dry_run: bool, delete_old: bool) -> None:
    """Migrate a v1 data lake (cache/<source>/...) to layout v2 (raw/ + processed/)."""
    config = LakeConfig()
    report = migrate_layout(config, dry_run=dry_run, delete_old=delete_old)
    if report.already_migrated:
        console.print(
            f"[green]Lake at {config.home} is already on layout v2; nothing to do.[/green]"
        )
        return
    if not report.steps and not report.unknown:
        console.print(
            f"[dim]No v1 data found under {config.home / 'cache'}; nothing to migrate.[/dim]"
        )
        return
    if dry_run:
        plan = Table(title=f"Migration plan for {config.home} (dry run)")
        plan.add_column("v1 file", style="dim")
        plan.add_column("v2 location", style="cyan")
        for step in report.steps:
            plan.add_row(
                str(step.src.relative_to(config.home)), str(step.dst.relative_to(config.home))
            )
        console.print(plan)
    summary = Table(title="Migration summary", show_header=False)
    for label, count in report.summary_rows():
        summary.add_row(label, f"{count:,}")
    console.print(summary)
    for path in report.unknown:
        console.print(f"[yellow]unknown, left in place:[/yellow] {path}")
    if not dry_run and report.version_written:
        console.print("[bold green]Layout v2 VERSION written.[/bold green]")


@main.group()
def db() -> None:
    """Manage the DuckDB catalog (views over processed/ Parquet)."""
    pass


@db.command("sync")
def db_sync() -> None:
    """Create or refresh a DuckDB view for every dataset that has processed data."""
    database = BaseballDatabase()
    count = database.sync_views()
    console.print(
        f"Registered [bold green]{count}[/bold green] views in [yellow]{database.db_path}[/yellow]."
    )


@main.group()
def refs() -> None:
    """Show or update the pinned upstream commit SHAs (reproducible GitHub sources)."""
    pass


@refs.command("show")
def refs_show() -> None:
    """List the effective pinned ref of every GitHub-hosted source."""
    table = Table(title="Pinned source refs")
    table.add_column("Source", style="cyan")
    table.add_column("Repository")
    table.add_column("Ref", style="green")
    table.add_column("Env override", style="dim")
    for key in sorted(load_lock()):
        src = get_source_ref(key)
        table.add_row(key, src.repo, src.ref, ENV_OVERRIDES.get(key, ""))
    console.print(table)


@refs.command("update")
@click.option("--dry-run", is_flag=True, help="Resolve and print the latest SHAs without writing.")
def refs_update(dry_run: bool) -> None:
    """Resolve the latest commit SHA of each source (set GITHUB_TOKEN to avoid rate limits)."""
    changes = update_lock(dry_run=dry_run)
    table = Table(title="Source refs (dry run)" if dry_run else "Source refs")
    table.add_column("Source", style="cyan")
    table.add_column("Old", style="dim")
    table.add_column("New", style="green")
    table.add_column("Changed")
    for change in changes:
        table.add_row(
            change.key,
            change.old[:12],
            change.new[:12],
            "[yellow]yes[/yellow]" if change.changed else "-",
        )
    console.print(table)
    if any(c.changed for c in changes) and not dry_run:
        console.print(
            "Lock updated. Chunks fetched at an older ref are refreshed the next time they are requested."
        )


@main.group()
def audit() -> None:
    """Inspect and analyze pipeline execution logs, benchmarks, and audit telemetry."""
    pass


@audit.command("summary")
@click.option("--limit", "-n", type=int, default=15, help="Number of recent events to display")
def audit_summary(limit: int) -> None:
    """Display a formatted summary table of recent operations."""
    events = default_audit_logger.read_events(limit=limit)
    if not events:
        console.print(
            "[dim]No audit log records found at:[/dim]", str(default_audit_logger.log_path)
        )
        return

    table = Table(title=f"baseballpy Audit Log (Last {len(events)} Operations)", show_lines=False)
    table.add_column("Timestamp (UTC)", style="dim")
    table.add_column("Operation", style="cyan")
    table.add_column("Source", style="blue")
    table.add_column("Status")
    table.add_column("Records", justify="right", style="green")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Throughput", justify="right", style="magenta")
    table.add_column("Cached", justify="center")

    for ev in events:
        status_style = (
            "[bold green]SUCCESS[/bold green]"
            if ev.status == "SUCCESS"
            else f"[bold red]{ev.status}[/bold red]"
        )
        cached_str = "[green]Y[/green]" if ev.cache_hit else "[dim]-[/dim]"
        throughput_str = f"{ev.throughput_rps:,.0f} r/s" if ev.throughput_rps > 0 else "-"
        table.add_row(
            ev.timestamp_utc[:19],
            ev.operation,
            ev.source,
            status_style,
            f"{ev.records_count:,}",
            f"{ev.duration_seconds:.2f}",
            throughput_str,
            cached_str,
        )

    console.print(table)


@audit.command("tail")
@click.option(
    "--limit", "-n", type=int, default=5, help="Number of recent events to inspect in detail"
)
def audit_tail(limit: int) -> None:
    """Print detailed telemetry records for the most recent operations."""
    events = default_audit_logger.read_events(limit=limit)
    if not events:
        console.print("[dim]No audit log records found.[/dim]")
        return

    for ev in events:
        status_color = "green" if ev.status == "SUCCESS" else "red"
        time_info = (
            f"started: {ev.started_at_utc[11:19]}Z -> completed: {ev.completed_at_utc[11:19]}Z"
            if ev.started_at_utc and ev.completed_at_utc
            else ev.timestamp_utc
        )
        console.print(
            f"[{status_color}]●[/{status_color}] [bold]{ev.operation}[/bold] ({ev.source}) - {time_info}"
        )
        timing_detail = f"{ev.duration_seconds}s"
        if ev.download_seconds is not None:
            timing_detail += (
                f" (download: {ev.download_seconds}s, processing: {ev.processing_seconds or 0.0}s)"
            )
        console.print(
            f"   Status: {ev.status} | Records: {ev.records_count:,} | Duration: {timing_detail} | Cache Hit: {ev.cache_hit}"
        )
        if ev.endpoint:
            console.print(f"   Endpoint: [dim]{ev.endpoint}[/dim]")
        if ev.destination:
            console.print(f"   Destination: [dim]{ev.destination}[/dim]")
        if ev.error:
            console.print(f"   [bold red]Error:[/bold red] {ev.error}")
        console.print("")


@audit.command("stats")
def audit_stats() -> None:
    """Compute and display aggregate throughput, success rate, and cache hit metrics."""
    stats = default_audit_logger.get_stats()
    if stats["total_operations"] == 0:
        console.print("[dim]No audit records available to compute stats.[/dim]")
        return

    table = Table(title="baseballpy Pipeline Metrics & Telemetry", show_header=False)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Operations", f"{stats['total_operations']:,}")
    table.add_row("Total Records Ingested", f"{stats['total_records']:,}")
    table.add_row("Pipeline Success Rate", f"{stats['success_rate'] * 100:.1f}%")
    table.add_row("Cache Hit Ratio", f"{stats['cache_hit_rate'] * 100:.1f}%")
    table.add_row("Average Duration", f"{stats['average_duration_seconds']:.2f} seconds")

    console.print(table)


if __name__ == "__main__":
    main()
