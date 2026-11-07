"""``baseballpy status``: one screen that says what the lake holds, what runs and what needs care."""

import json
from dataclasses import dataclass

import click
from rich.console import Console
from rich.table import Table

from baseballpy.cli_ingest import DatasetStatus, _disk_usage, find_orphans, scan_lake
from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import busy_hosts

console = Console()
GB = 1_000_000_000


@dataclass(frozen=True)
class SourceSummary:
    """What the lake holds for one source."""

    source: str
    datasets_held: int
    datasets_registered: int
    rows: int
    first_season: int | None
    last_season: int | None
    newest: str | None
    #: registered default datasets with no data (what a plain `ingest` would still fill)
    gaps: int


def summarize(statuses: list[DatasetStatus]) -> list[SourceSummary]:
    """Group dataset statuses by source."""
    out: list[SourceSummary] = []
    for source in sorted({s.source for s in statuses}):
        mine = [s for s in statuses if s.source == source]
        held = [s for s in mine if s.status == "INGESTED"]
        seasons = [y for s in held for y in s.seasons]
        stamps = [s.newest_mtime for s in held if s.newest_mtime]
        out.append(
            SourceSummary(
                source=source,
                datasets_held=len(held),
                datasets_registered=len(mine),
                rows=sum(s.rows for s in held),
                first_season=min(seasons) if seasons else None,
                last_season=max(seasons) if seasons else None,
                newest=max(stamps) if stamps else None,
                gaps=sum(1 for s in mine if s.status == "MISSING" and s.ingest == "default"),
            )
        )
    return out


def _seasons(item: SourceSummary) -> str:
    if item.first_season is None:
        return "-"
    return (
        str(item.first_season)
        if item.first_season == item.last_season
        else f"{item.first_season}-{item.last_season}"
    )


@click.command("status")
@click.option("--json", "as_json", is_flag=True, help="Print the overview as one JSON object.")
def status_cmd(as_json: bool) -> None:
    """Show what the lake holds per source, what is running and what needs attention.

    Fast (it reads manifests, not data). For one row per dataset use `catalog status`; for gaps in
    a season use `catalog coverage`; to fetch what is new use `update`.
    """
    config = LakeConfig()
    summaries = summarize(scan_lake(config))
    free, total = _disk_usage(config.home)
    running = busy_hosts(config.locks_root)
    quarantined = (
        sum(1 for _ in config.quarantine_root.rglob("*.jsonl"))
        if config.quarantine_root.is_dir()
        else 0
    )
    orphans = len(find_orphans(config))
    report = {
        "home": str(config.home),
        "disk_free_gb": round(free / GB, 1),
        "disk_total_gb": round(total / GB, 1),
        "downloading_from": running,
        "quarantine_files": quarantined,
        "orphan_part_files": orphans,
        "sources": [s.__dict__ for s in summaries],
    }
    if as_json:
        click.echo(json.dumps(report, indent=2))
        return

    table = Table(title=f"Lake at {config.home}")
    for column in ("Source", "Datasets", "Rows", "Seasons", "Newest", "Not yet filled"):
        table.add_column(column, justify="left" if column in ("Source", "Seasons") else "right")
    for item in summaries:
        table.add_row(
            item.source,
            f"{item.datasets_held}/{item.datasets_registered}",
            f"{item.rows:,}",
            _seasons(item),
            item.newest or "-",
            str(item.gaps) if item.gaps else "-",
        )
    console.print(table)
    console.print(f"Disk: {free / GB:.1f} GB free of {total / GB:.1f} GB.")
    console.print(
        "Downloading now from: "
        + (", ".join(running) if running else "nothing (no ingest running).")
    )
    if quarantined:
        console.print(
            f"[yellow]{quarantined} quarantine file(s)[/yellow]: values that could not be typed "
            "(see `baseballpy quarantine list`)."
        )
    if orphans:
        console.print(
            f"[yellow]{orphans} leftover .part file(s)[/yellow] (run `baseballpy doctor --clean` "
            "when nothing is downloading)."
        )
    console.print(
        "Next: `baseballpy update` fetches what is new; `baseballpy catalog coverage` lists gaps; "
        "`baseballpy catalog layout` checks the files are shaped for fast reads."
    )


def register_status_command(main: click.Group) -> None:
    """Add ``status`` to the top-level group."""
    main.add_command(status_cmd, "status")


__all__ = ["SourceSummary", "register_status_command", "status_cmd", "summarize"]
