"""CLI: ``baseballpy verify-sample`` downloads a small sample and compares it with the lake (ADR 108)."""

import shutil
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import LakeConfig
from baseballpy.ingest import sample as sample_module
from baseballpy.sources import catalog

console = Console()


@click.command("verify-sample")
@click.argument("source")
@click.option(
    "-s", "--seasons", default=None, help="Season expression of the sample (for example 2024)."
)
@click.option("-d", "--datasets", multiple=True, help="Dataset(s) of the sample (repeatable).")
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=None,
    help="Bound the per-game or per-person fan-out.",
)
@click.option("--keep", is_flag=True, help="Keep the scratch home (its path is printed).")
def verify_sample_cmd(
    source: str, seasons: str | None, datasets: tuple[str, ...], limit: int | None, keep: bool
) -> None:
    """Download a small sample into a scratch home and compare it with the lake.

    The real lake is not touched. Every completed processed chunk of the sample is compared with the same
    chunk of the lake (rows sorted by the registered keys) and every raw file by sha256. Exit code 1 when
    any chunk or raw file differs; a chunk the lake never fetched is reported but is not a difference. A
    provider answer can change over time, so a difference is information to explain or fix.
    """
    catalog.register_all()
    lake = LakeConfig()
    scratch = Path(tempfile.mkdtemp(prefix="baseballpy-sample-"))
    try:
        code = sample_module.run_scratch_ingest(
            source, scratch, seasons=seasons, datasets=datasets, limit=limit
        )
        if code != 0:
            raise click.ClickException(
                f"the sample download exited with {code}; nothing was compared"
            )
        report = sample_module.compare_lakes(LakeConfig(home=scratch), lake, (source,))
    finally:
        if keep:
            console.print(f"scratch home kept: {scratch}")
        else:
            shutil.rmtree(scratch, ignore_errors=True)
    table = Table("Processed chunks", "Identical", "Missing in lake", "Raw files", "Raw identical")
    table.add_row(
        str(report.compared),
        str(report.identical),
        str(report.missing_in_lake),
        str(report.raw_compared),
        str(report.raw_identical),
    )
    console.print(table)
    for difference in report.differences[:30]:
        colour = "yellow" if difference.kind == sample_module.MISSING_IN_LAKE else "red"
        console.print(
            f"[{colour}]{difference.kind}[/{colour}] {difference.source}.{difference.dataset} "
            f"{difference.item}: {difference.detail}"
        )
    if len(report.differences) > 30:
        console.print(f"... and {len(report.differences) - 30} more")
    if report.failed:
        raise click.ClickException("the sample differs from the lake (see above)")
    if report.missing_in_lake:
        console.print("no differences (some chunks are not in the lake)")
    else:
        console.print("the sample matches the lake")


def register_sample_command(group: click.Group) -> None:
    """Attach ``verify-sample`` to the main group."""
    group.add_command(verify_sample_cmd)
