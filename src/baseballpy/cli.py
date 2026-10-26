"""Command-line interface for baseballpy."""

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.audit import default_audit_logger
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sources.statcast.extractor import StatcastExtractor

console = Console()


@click.group()
@click.version_option()
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
