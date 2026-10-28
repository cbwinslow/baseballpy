"""CLI commands for inspecting registered datasets and their lake ingestion status."""

import difflib
import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from baseballpy.cli_ingest import DatasetStatus, scan_lake
from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.sources.catalog import register_all

console = Console()


def resolve_dataset(spec_str: str) -> DatasetSpec:
    """Resolve a SPEC token (full 'source.name' key or unique bare dataset name).

    Args:
        spec_str: Dataset identifier as 'source.name' or a bare dataset name.

    Returns:
        The matched DatasetSpec from the registry.

    Raises:
        click.BadParameter: If the spec is unknown or ambiguous across registered sources.
    """
    register_all()
    if spec_str in DATASETS:
        return DATASETS[spec_str]

    matches = [d for d in DATASETS.values() if d.name == spec_str]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        ambiguous_keys = ", ".join(sorted(d.key for d in matches))
        raise click.BadParameter(
            f"dataset {spec_str!r} is ambiguous; matching keys: {ambiguous_keys}"
        )

    close_matches = difflib.get_close_matches(spec_str, sorted(DATASETS.keys()))
    if close_matches:
        close_str = ", ".join(close_matches)
        raise click.BadParameter(f"unknown dataset {spec_str!r}; close matches: {close_str}")
    raise click.BadParameter(f"unknown dataset {spec_str!r}")


@click.command("list")
@click.option(
    "--source",
    "sources",
    multiple=True,
    help="Filter by source (repeatable).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output datasets as newline-delimited JSON objects.",
)
@click.pass_context
def catalog_list_cmd(
    ctx: click.Context,
    sources: tuple[str, ...],
    as_json: bool,
) -> None:
    """List registered datasets with schema, partition, and primary key metadata."""
    register_all()
    specs = list(DATASETS.values())
    if sources:
        source_set = set(sources)
        specs = [s for s in specs if s.source in source_set]

    sorted_specs = sorted(specs, key=lambda d: (d.source, d.name))

    if as_json:
        for spec in sorted_specs:
            click.echo(
                json.dumps(
                    {
                        "source": spec.source,
                        "name": spec.name,
                        "view": spec.view,
                        "partition": spec.partition,
                        "columns": len(spec.schema),
                        "keys": ", ".join(spec.keys),
                    }
                )
            )
    else:
        table = Table(title="Catalog Datasets")
        table.add_column("Source", style="cyan")
        table.add_column("Name")
        table.add_column("View")
        table.add_column("Partition")
        table.add_column("Columns", justify="right")
        table.add_column("Keys")

        for spec in sorted_specs:
            table.add_row(
                spec.source,
                spec.name,
                spec.view,
                spec.partition,
                str(len(spec.schema)),
                ", ".join(spec.keys),
            )
        console.print(table)

    ctx.exit(0)


@click.command("show")
@click.argument("spec", type=str)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output dataset details as a single JSON object.",
)
@click.pass_context
def catalog_show_cmd(
    ctx: click.Context,
    spec: str,
    as_json: bool,
) -> None:
    """Show detailed metadata, schema columns, and lake status for a registered dataset."""
    dataset_spec = resolve_dataset(spec)

    statuses = scan_lake()
    lake_status = next(
        (s for s in statuses if s.source == dataset_spec.source and s.dataset == dataset_spec.name),
        None,
    )
    if lake_status is None:
        lake_status = DatasetStatus(
            source=dataset_spec.source,
            dataset=dataset_spec.name,
            status="MISSING",
            files=0,
            rows=0,
            seasons=(),
            newest_mtime=None,
            ingest=dataset_spec.ingest,
            note=dataset_spec.ingest_note,
        )

    if as_json:
        data: dict[str, Any] = {
            "key": dataset_spec.key,
            "source": dataset_spec.source,
            "name": dataset_spec.name,
            "view": dataset_spec.view,
            "description": dataset_spec.description,
            "partition": dataset_spec.partition,
            "keys": list(dataset_spec.keys),
            "endpoint_doc": dataset_spec.endpoint_doc,
            "ingest": dataset_spec.ingest,
            "ingest_note": dataset_spec.ingest_note,
            "status": lake_status.status,
            "files": lake_status.files,
            "rows": lake_status.rows,
            "seasons": list(lake_status.seasons),
            "columns": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                }
                for field in dataset_spec.schema
            ],
        }
        click.echo(json.dumps(data))
    else:
        meta_table = Table(title=f"Dataset: {dataset_spec.key}", show_header=False)
        meta_table.add_column("Property", style="bold cyan")
        meta_table.add_column("Value")

        meta_table.add_row("Key", dataset_spec.key)
        meta_table.add_row("View", dataset_spec.view)
        meta_table.add_row("Description", dataset_spec.description)
        meta_table.add_row("Partition", dataset_spec.partition)
        meta_table.add_row("Keys", ", ".join(dataset_spec.keys) if dataset_spec.keys else "-")
        meta_table.add_row("Endpoint Doc", dataset_spec.endpoint_doc)
        meta_table.add_row(
            "Ingest",
            f"{dataset_spec.ingest}: {dataset_spec.ingest_note}"
            if dataset_spec.ingest_note
            else dataset_spec.ingest,
        )

        status_style = "bold green" if lake_status.status == "INGESTED" else "dim red"
        meta_table.add_row("Status", f"[{status_style}]{lake_status.status}[/{status_style}]")
        meta_table.add_row("Files", f"{lake_status.files:,}")
        meta_table.add_row("Rows", f"{lake_status.rows:,}")
        seasons_str = ", ".join(str(s) for s in lake_status.seasons) if lake_status.seasons else "-"
        meta_table.add_row("Seasons", seasons_str)

        console.print(meta_table)

        col_table = Table(title=f"Schema Columns ({len(dataset_spec.schema)})")
        col_table.add_column("Name", style="cyan")
        col_table.add_column("Type")
        col_table.add_column("Nullable")
        for field in dataset_spec.schema:
            col_table.add_row(field.name, str(field.type), str(field.nullable))
        console.print(col_table)

    ctx.exit(0)


def register_catalog_commands(catalog_group: click.Group) -> None:
    """Register catalog list and show subcommands on a Click catalog group.

    Args:
        catalog_group: Click command group to receive the subcommands.
    """
    catalog_group.add_command(catalog_list_cmd, "list")
    catalog_group.add_command(catalog_show_cmd, "show")


__all__ = [
    "catalog_list_cmd",
    "catalog_show_cmd",
    "register_catalog_commands",
    "resolve_dataset",
]
