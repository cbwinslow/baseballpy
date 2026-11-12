"""CLI: ``baseballpy verify-sample`` downloads a small sample and compares it with the lake (ADR 108)."""

import json
import shutil
import tempfile
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.roundtrip import roundtrip_lake
from baseballpy.ingest import sample as sample_module
from baseballpy.sources import catalog
from baseballpy.sources.adapters import register_all_adapters

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


@click.command("verify-roundtrip")
@click.argument("sources", nargs=-1)
@click.option(
    "-d", "--datasets", multiple=True, help="Dataset name(s) to check (repeatable; default: all)."
)
@click.option(
    "--files",
    "sample_files",
    type=click.IntRange(min=1),
    default=3,
    show_default=True,
    help="Raw files compared per dataset, spread over its seasons.",
)
@click.option("--json", "as_json", is_flag=True, help="Print the verdicts as JSON.")
def verify_roundtrip_cmd(
    sources: tuple[str, ...], datasets: tuple[str, ...], sample_files: int, as_json: bool
) -> None:
    """Check that no value of the provider's text was lost or changed in our processed tables.

    For each dataset it re-reads sampled raw CSV files as text and compares every cell with the stored value
    (integers by their text, so a dropped leading zero shows; floats by value, so a 32-bit float shows),
    lists non-empty raw cells stored as NULL, raw rows missing from the processed data, and raw columns no
    schema column or _extras reads. Offline and read-only. Datasets whose raw files are not CSV are
    reported as skipped with the reason, never as clean. Exit code 1 when any dataset shows a loss.
    """
    catalog.register_all()
    register_all_adapters()  # the sources register how their raw files are read
    specs = [
        spec
        for spec in sorted(DATASETS.values(), key=lambda s: s.key)
        if (not sources or spec.source in sources) and (not datasets or spec.name in datasets)
    ]
    if not specs:
        raise click.ClickException("no registered dataset matches the sources and datasets given")
    checks = roundtrip_lake(LakeConfig(), specs, sample_files=sample_files)
    if as_json:
        click.echo(
            json.dumps(
                [c.__dict__ | {"losses": [loss.__dict__ for loss in c.losses]} for c in checks],
                default=str,
            )
        )
    else:
        table = Table(
            "Source", "Dataset", "Status", "Files", "Raw rows", "Compared", "Quarantined", "Detail"
        )
        for c in checks:
            detail = (
                c.reason
                or "; ".join(c.notes)
                or "; ".join(
                    f"{loss.kind} {loss.column or '-'} x{loss.count:,} ({loss.example})"
                    for loss in c.losses[:3]
                )
            )
            colour = {"ok": "green", "loss": "red", "skipped": "yellow"}[c.status]
            table.add_row(
                c.source,
                c.dataset,
                f"[{colour}]{c.status}[/{colour}]",
                str(len(c.files)),
                f"{c.raw_rows:,}",
                f"{c.compared:,}",
                f"{c.quarantined:,}",
                detail[:160],
            )
        console.print(table)
        counts = {s: sum(1 for c in checks if c.status == s) for s in ("ok", "loss", "skipped")}
        console.print(
            f"{counts['ok']} clean, {counts['loss']} with a loss, {counts['skipped']} skipped"
        )
    if any(c.status == "loss" for c in checks):
        raise SystemExit(1)


def register_sample_command(group: click.Group) -> None:
    """Attach ``verify-sample`` to the main group."""
    group.add_command(verify_sample_cmd)
    group.add_command(verify_roundtrip_cmd)
