"""CLI: ``baseballpy compact`` merges small download chunks into a few big Parquet files."""

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.sources import catalog

console = Console()


@click.command("compact")
@click.option("--source", "sources", multiple=True, help="Limit to a source (repeatable).")
@click.option("--dataset", "datasets", multiple=True, help="Limit to a dataset name (repeatable).")
@click.option("--dry-run", is_flag=True, help="Show what would be merged; change nothing.")
def compact_cmd(sources: tuple[str, ...], datasets: tuple[str, ...], dry_run: bool) -> None:
    """Merge each dataset's small chunk files into big ones (run when no ingest is running).

    Every new file is read back and compared with its source chunks before the small files
    are removed. Chunks stay known to the download records, so later ingests still resume.
    """
    catalog.register_all()
    config = LakeConfig()
    specs = [
        spec
        for spec in DATASETS.values()
        if (not sources or spec.source in sources) and (not datasets or spec.name in datasets)
    ]
    if not specs:
        raise click.ClickException("no dataset matches --source/--dataset")
    table = Table(
        "Dataset", "Seasons", "Chunks", "Files before", "Files after", "MB before", "MB after"
    )
    totals = [0, 0, 0, 0, 0]
    empty_files = 0
    for spec in specs:
        report = compact_dataset(spec, config, dry_run=dry_run)
        empty_files += report.empty_files
        if not report.groups:
            continue
        table.add_row(
            report.dataset,
            str(report.groups),
            str(report.chunks),
            str(report.files_before),
            str(report.files_after),
            f"{report.bytes_before / 1e6:,.1f}",
            "-" if dry_run else f"{report.bytes_after / 1e6:,.1f}",
        )
        totals = [
            totals[0] + report.chunks,
            totals[1] + report.files_before,
            totals[2] + report.files_after,
            totals[3] + report.bytes_before,
            totals[4] + report.bytes_after,
        ]
    console.print(table)
    verb = "would merge" if dry_run else "merged"
    console.print(
        f"{verb} {totals[0]:,} chunks: {totals[1]:,} files -> {totals[2]:,} files, "
        f"{totals[3] / 1e6:,.0f} MB -> {totals[4] / 1e6:,.0f} MB"
    )
    if empty_files:
        console.print(
            f"{'would remove' if dry_run else 'removed'} {empty_files:,} empty (0 row) files"
        )


def register_compact_command(group: click.Group) -> None:
    """Attach ``compact`` to the main group."""
    group.add_command(compact_cmd)
