"""CLI: ``baseballpy export`` sends cached typed datasets to Parquet, CSV, DuckDB or PostgreSQL."""

import json
from dataclasses import asdict

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import SOURCES, DatasetSpec, datasets_for
from baseballpy.export import (
    DEFAULT_SCHEMA,
    MODES,
    POSTGRES_URL_ENV,
    TARGETS,
    ExportError,
    ExportResult,
    NoCachedDataError,
    export_dataset,
)
from baseballpy.ingest.selection import parse_seasons
from baseballpy.sources import catalog

console = Console()


def _select(specs: tuple[str, ...]) -> list[tuple[DatasetSpec, bool]]:
    """``(dataset, explicitly named)`` for each ``source`` or ``source:dataset[,dataset]`` given."""
    catalog.register_all()
    chosen: list[tuple[DatasetSpec, bool]] = []
    for text in specs:
        source, _, names = text.partition(":")
        if source not in SOURCES:
            raise click.BadParameter(f"unknown source {source!r}; known: {', '.join(SOURCES)}")
        available = {spec.name: spec for spec in datasets_for(source)}
        if not names:
            chosen.extend((spec, False) for spec in available.values())
            continue
        for name in (n.strip() for n in names.split(",") if n.strip()):
            if name not in available:
                raise click.BadParameter(
                    f"unknown dataset {name!r} for {source}; known: {', '.join(sorted(available))}"
                )
            chosen.append((available[name], True))
    return chosen


@click.command("export")
@click.argument("specs", nargs=-1, required=True)
@click.option(
    "--to",
    "target",
    required=True,
    type=click.Choice(sorted(TARGETS)),
    help="Where to send the data: "
    + "; ".join(f"{t.name} = {t.description}" for t in TARGETS.values()),
)
@click.option(
    "--out",
    type=click.Path(),
    help="Folder for files (or a .duckdb file); default: the lake's exports/.",
)
@click.option(
    "--url", help=f"PostgreSQL URL (default: the {POSTGRES_URL_ENV} environment variable)."
)
@click.option("--schema", default=DEFAULT_SCHEMA, show_default=True, help="PostgreSQL schema.")
@click.option(
    "--mode",
    type=click.Choice(list(MODES)),
    default="replace",
    show_default=True,
    help="replace, append, or merge on the registry key (databases only).",
)
@click.option(
    "--seasons",
    help="Seasons of season-partitioned datasets, e.g. 2023 or 2015-2024 (default: all cached).",
)
@click.option("--no-verify", is_flag=True, help="Skip the read-back check.")
@click.option("--json", "as_json", is_flag=True, help="Print one JSON object per dataset.")
def export_cmd(
    specs: tuple[str, ...],
    target: str,
    out: str | None,
    url: str | None,
    schema: str,
    mode: str,
    seasons: str | None,
    no_verify: bool,
    as_json: bool,
) -> None:
    """Export cached datasets: SPECS are `source` or `source:dataset[,dataset]`.

    Reads only what `baseballpy ingest` already stored; every export is read back and compared with
    the source unless --no-verify is given. Exit code 1 when something failed or nothing was exported.
    """
    config = LakeConfig()
    wanted = None
    if seasons and seasons.strip().lower() != "all":
        try:
            wanted = list(parse_seasons(seasons))
        except ValueError as exc:
            raise click.BadParameter(str(exc), param_hint="--seasons") from exc
    results: list[ExportResult] = []
    skipped: list[str] = []
    failed: list[str] = []
    for spec, explicit in _select(specs):
        try:
            results.append(
                export_dataset(
                    spec,
                    target,
                    config=config,
                    out=out,
                    url=url,
                    schema=schema,
                    mode=mode,
                    seasons=wanted if spec.partition == "season" else None,
                    verify=not no_verify,
                )
            )
        except NoCachedDataError as exc:  # the message already names the dataset
            (failed if explicit else skipped).append(str(exc))
        except ExportError as exc:
            failed.append(str(exc))
        except ValueError as exc:
            failed.append(f"{spec.key}: {exc}")
    if as_json:
        for result in results:
            click.echo(json.dumps(asdict(result)))
    else:
        _print(results, skipped, failed)
    if failed or not results:
        raise SystemExit(1)


def _print(results: list[ExportResult], skipped: list[str], failed: list[str]) -> None:
    if results:
        table = Table(title="Export")
        for column in ("Source", "Dataset", "Target", "Rows", "Seconds", "Verified"):
            table.add_column(column, overflow="fold")
        for r in results:
            table.add_row(
                r.source,
                r.dataset,
                r.target,
                f"{r.rows:,}",
                f"{r.seconds:.2f}",
                "yes" if r.verified else "no",
            )
        console.print(table)
        for r in results:
            console.print(f"  {r.dataset} -> {r.destination}", soft_wrap=True)
    if skipped:
        console.print(
            f"[dim]Skipped {len(skipped)} dataset(s) with nothing cached (ingest them first).[/dim]"
        )
    for message in failed:
        console.print(f"[red]{message}[/red]")
    if not results and not failed:
        console.print("[yellow]Nothing was exported: no cached data for the selection.[/yellow]")


def register_export_command(main: click.Group) -> None:
    """Register ``export`` on the main Click group."""
    main.add_command(export_cmd, "export")


__all__ = ["export_cmd", "register_export_command"]
