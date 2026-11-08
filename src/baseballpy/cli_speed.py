"""``baseballpy speed``: is the download running as fast as it can, and if not, why."""

import json
from dataclasses import asdict

import click
from rich.console import Console
from rich.table import Table

from baseballpy.ingest.speed import default_audit_path, measure

console = Console()


@click.command("speed")
@click.option(
    "--minutes",
    type=click.FloatRange(min=0.5),
    default=10.0,
    show_default=True,
    help="Look at this many minutes of the audit log.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the report as one JSON object.")
def speed_cmd(minutes: float, as_json: bool) -> None:
    """Measure the download speed from the audit log and name what limits it.

    Per host: requests per second against the rate limit, how long an answer takes, how much of
    the in-flight allowance is used, and the limit in one sentence (the rate limit, the host, or
    the program's own work). It reads the log only; it changes nothing.
    """
    report = measure(default_audit_path(), seconds=minutes * 60)
    if as_json:
        click.echo(json.dumps(asdict(report), indent=2))
        return
    if not report.hosts:
        console.print(f"No requests in the last {minutes:g} minutes: nothing is downloading.")
        return
    table = Table(title=f"Download speed, last {minutes:g} min")
    for column in ("Host", "Req/s", "Cap", "Used", "Answer p50", "In flight", "Pushed back"):
        table.add_column(column, justify="right" if column != "Host" else "left")
    for host in report.hosts:
        table.add_row(
            host.host,
            f"{host.requests_per_second:.1f}",
            f"{host.cap:g}" if host.cap else "-",
            f"{(host.utilization or 0) * 100:.0f}%" if host.utilization is not None else "-",
            f"{host.latency_p50:.2f} s",
            f"~{host.in_flight:.1f} of {host.in_flight_limit}",
            str(host.pushed_back),
        )
    console.print(table)
    for host in report.hosts:
        console.print(f"[cyan]{host.host}[/cyan]: {host.diagnosis}")
    if report.chunks_written:
        console.print(f"{report.chunks_written:,} per-game chunks written in the window.")


def register_speed_command(main: click.Group) -> None:
    """Add ``speed`` to the top-level group."""
    main.add_command(speed_cmd, "speed")


__all__ = ["register_speed_command", "speed_cmd"]
