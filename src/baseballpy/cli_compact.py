"""CLI: ``baseballpy compact`` merges small download chunks into a few big Parquet files."""

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.rawconvert import compress_raw
from baseballpy.sources import catalog

console = Console()


@click.command("compact")
@click.option("--source", "sources", multiple=True, help="Limit to a source (repeatable).")
@click.option("--dataset", "datasets", multiple=True, help="Limit to a dataset name (repeatable).")
@click.option("--dry-run", is_flag=True, help="Show what would be merged; change nothing.")
@click.option(
    "--migrate/--no-migrate",
    default=True,
    show_default=True,
    help="First rewrite files written under an older schema (slow the first time; the download "
    "queue skips it and leaves it to a run of its own).",
)
def compact_cmd(
    sources: tuple[str, ...], datasets: tuple[str, ...], dry_run: bool, migrate: bool
) -> None:
    """Merge each dataset's small chunk files into big ones (run when no ingest is running).

    Every new file is read back and compared with its source chunks before the small files
    are removed. Chunks stay known to the download records, so later ingests still resume.

    Files written before a schema gained columns are rewritten to the registered schema first;
    values that sat in the `_extras` column move to their new columns (ADR 87).
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
    migrated = failed = 0
    for spec in specs:
        report = compact_dataset(spec, config, dry_run=dry_run, migrate=migrate)
        empty_files += report.empty_files
        migrated += report.migrated_files
        failed += report.migrate_failed
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
    if migrated:
        console.print(
            f"{'would rewrite' if dry_run else 'rewrote'} {migrated:,} file(s) written under an "
            "older schema to the registered one (values in _extras moved to their new columns)"
        )
    if failed:
        console.print(f"[red]{failed:,} file(s) could not be rewritten (see the log)[/red]")
        raise click.ClickException("some files kept their old schema")


@click.command("compress-raw")
@click.option("--source", "sources", multiple=True, help="Limit to a source (repeatable).")
@click.option("--dry-run", is_flag=True, help="Show what would be compressed; change nothing.")
def compress_raw_cmd(sources: tuple[str, ...], dry_run: bool) -> None:
    """Gzip raw text files (json, csv) of the configured sources (run when no ingest is running).

    Each file is checked against its recorded sha256, written compressed, read back and checked
    again before the original is removed. The checksum stays that of the original bytes.
    """
    report = compress_raw(LakeConfig(), sources=sources or None, dry_run=dry_run)
    verb = "would compress" if dry_run else "compressed"
    after = "" if dry_run else f" -> {report.bytes_after / 1e9:,.2f} GB"
    console.print(f"{verb} {report.files:,} files: {report.bytes_before / 1e9:,.2f} GB{after}")
    for line in report.skipped[:20]:
        console.print(f"[yellow]skipped[/yellow] {line}")
    if report.skipped:
        raise click.ClickException(f"{len(report.skipped)} file(s) were left as they are")


def register_compact_command(group: click.Group) -> None:
    """Attach ``compact`` to the main group."""
    group.add_command(compact_cmd)
    group.add_command(compress_raw_cmd)
