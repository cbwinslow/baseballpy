"""CLI: ``baseballpy cache check`` verifies the raw tier and reports upstream changes."""

import json
from collections import Counter

import click
from rich.console import Console
from rich.table import Table

from baseballpy.cache_check import (
    CHANGED,
    CORRUPT,
    CURRENT,
    MISSING,
    NO_FINGERPRINT,
    OK,
    REMOVED,
    UNREACHABLE,
    FileCheck,
    check_raw,
)
from baseballpy.core.config import LakeConfig

console = Console()


@click.group("cache")
def cache_group() -> None:
    """Inspect the raw download cache."""


@click.command("check")
@click.option("--source", "sources", multiple=True, help="Limit to a source (repeatable).")
@click.option(
    "--upstream",
    is_flag=True,
    help="Also compare git file fingerprints with upstream's latest commit (needs the network).",
)
@click.option("--json", "as_json", is_flag=True, help="Print every checked file as JSON.")
def cache_check_cmd(sources: tuple[str, ...], upstream: bool, as_json: bool) -> None:
    """Verify raw files against their recorded sha256 and optionally against upstream.

    Exit code 1 when a file is missing or corrupt. Files whose upstream version changed are
    reported only: refresh them with ``baseballpy ingest <source> --refresh``.
    """
    results = check_raw(LakeConfig(), sources=sources, upstream=upstream)
    broken = [r for r in results if r.integrity in (CORRUPT, MISSING)]
    if as_json:
        for r in results:
            click.echo(json.dumps(r.__dict__))
    else:
        _print_summary(results, upstream)
        _print_problems(results, upstream)
    raise SystemExit(1 if broken else 0)


def _print_summary(results: list[FileCheck], upstream: bool) -> None:
    if not results:
        console.print("[dim]No raw files with a recorded sha256 were found.[/dim]")
        return
    groups: dict[tuple[str, str], Counter[str]] = {}
    for r in results:
        counts = groups.setdefault((r.source, r.dataset), Counter())
        counts["files"] += 1
        counts[r.integrity] += 1
        counts[r.upstream] += 1
    table = Table(title="Raw cache check")
    table.add_column("Source", overflow="fold")
    table.add_column("Dataset", overflow="fold")
    for column in ("Files", "OK", "Corrupt", "Missing"):
        table.add_column(column)
    if upstream:
        for column in ("Changed upstream", "No fingerprint"):
            table.add_column(column)
    for (source, dataset), c in sorted(groups.items()):
        row = [source, dataset, str(c["files"]), str(c[OK]), str(c[CORRUPT]), str(c[MISSING])]
        if upstream:
            row += [str(c[CHANGED] + c[REMOVED]), str(c[NO_FINGERPRINT])]
        table.add_row(*row)
    console.print(table)


def _print_problems(results: list[FileCheck], upstream: bool) -> None:
    problems = [
        r for r in results if r.integrity != OK or r.upstream in (CHANGED, REMOVED, UNREACHABLE)
    ]
    for r in problems[:30]:
        where = f"{r.source}/{r.dataset}" + (f"/season={r.season}" if r.season else "")
        console.print(f"  {where}/{r.name}: integrity={r.integrity} upstream={r.upstream}")
    if len(problems) > 30:
        console.print(f"  ... and {len(problems) - 30} more (use --json for all)")
    if any(r.upstream == CHANGED for r in results):
        console.print(
            "[yellow]Some files changed upstream; refresh with `ingest --refresh`.[/yellow]"
        )
    compared = any(r.upstream in (CURRENT, CHANGED, REMOVED, UNREACHABLE) for r in results)
    if results and not compared:
        if upstream:
            console.print(
                "[dim]Nothing could be compared with upstream: no file has a git fingerprint "
                "(files you supplied yourself and files without one are not compared).[/dim]"
            )
        else:
            console.print("[dim]Upstream was not checked (add --upstream).[/dim]")


def register_cache_commands(main: click.Group) -> None:
    """Register the ``cache`` group on the main Click group."""
    cache_group.add_command(cache_check_cmd, "check")
    main.add_command(cache_group, "cache")


__all__ = ["cache_check_cmd", "cache_group", "register_cache_commands"]
