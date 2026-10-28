"""CLI commands for inspecting and displaying dead-letter quarantine files."""

import json
from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import QuarantineConfig

console = Console()


@dataclass(frozen=True)
class QuarantineFile:
    """Metadata summary of a quarantined dead-letter JSONL file."""

    path: str
    source: str
    dataset: str
    date: str
    records: int
    reason: str


def scan_quarantine(config: QuarantineConfig | None = None) -> list[QuarantineFile]:
    """Scan the quarantine directory and extract metadata for all dead-letter files.

    Args:
        config: Optional QuarantineConfig instance. Defaults to QuarantineConfig().

    Returns:
        List of QuarantineFile objects sorted newest first.
    """
    cfg = config or QuarantineConfig()
    quarantine_dir = cfg.quarantine_dir
    if not quarantine_dir.is_dir():
        return []

    files: list[QuarantineFile] = []
    for path in quarantine_dir.rglob("*.jsonl"):
        if not path.is_file():
            continue
        rel = path.relative_to(quarantine_dir)
        parts = rel.parts
        source = parts[0] if len(parts) >= 1 else "unknown"
        date_str = parts[1] if len(parts) >= 2 else ""
        filename = parts[-1]
        dataset = filename.rsplit("-", 1)[0] if "-" in filename else filename.removesuffix(".jsonl")

        count = 0
        first_reason: str | None = None
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                count += 1
                if first_reason is None:
                    try:
                        record = json.loads(stripped)
                        if isinstance(record, dict) and "reason" in record:
                            first_reason = str(record["reason"])
                    except json.JSONDecodeError:
                        first_reason = "corrupted JSON"

        files.append(
            QuarantineFile(
                path=rel.as_posix(),
                source=source,
                dataset=dataset,
                date=date_str,
                records=count,
                reason=first_reason or "-",
            )
        )

    files.sort(key=lambda qf: (qf.date, qf.path), reverse=True)
    return files


@click.command("list")
@click.option("--source", "source", default=None, help="Filter by data source.")
@click.option("--dataset", "dataset", default=None, help="Filter by dataset name.")
@click.option("--since", "since", default=None, help="Filter by date (YYYY-MM-DD) on or after.")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output results as newline-delimited JSON.",
)
@click.pass_context
def quarantine_list_cmd(
    ctx: click.Context,
    source: str | None,
    dataset: str | None,
    since: str | None,
    as_json: bool,
) -> None:
    """List dead-letter quarantine files and their error summaries."""
    files = scan_quarantine()
    if source is not None:
        files = [f for f in files if f.source == source]
    if dataset is not None:
        files = [f for f in files if f.dataset == dataset]
    if since is not None:
        files = [f for f in files if f.date >= since]

    if as_json:
        for f in files:
            click.echo(
                json.dumps(
                    {
                        "path": f.path,
                        "source": f.source,
                        "dataset": f.dataset,
                        "date": f.date,
                        "records": f.records,
                        "reason": f.reason,
                    }
                )
            )
    else:
        table = Table(title="Quarantined Files")
        table.add_column("Path", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Dataset")
        table.add_column("Date")
        table.add_column("Records", justify="right")
        table.add_column("Reason")
        for f in files:
            table.add_row(f.path, f.source, f.dataset, f.date, str(f.records), f.reason)
        console.print(table)

    ctx.exit(0)


@click.command("show")
@click.argument("path", type=str)
@click.option(
    "--limit",
    "-n",
    type=click.IntRange(min=1),
    default=5,
    show_default=True,
    help="Maximum records to display.",
)
@click.option("--json", "as_json", is_flag=True, help="Output raw full JSON lines.")
@click.pass_context
def quarantine_show_cmd(
    ctx: click.Context,
    path: str,
    limit: int,
    as_json: bool,
) -> None:
    """Display records from a quarantined dead-letter JSONL file."""
    cfg = QuarantineConfig()
    quarantine_dir = cfg.quarantine_dir.resolve()

    target = Path(path)
    resolved = target.resolve() if target.is_absolute() else (quarantine_dir / target).resolve()

    try:
        resolved.relative_to(quarantine_dir)
    except ValueError as exc:
        raise click.BadParameter(
            f"Path {path!r} resolves outside the quarantine directory ({quarantine_dir})"
        ) from exc

    if not resolved.is_file():
        raise click.BadParameter(f"Quarantine file not found: {path!r}")

    displayed = 0
    with open(resolved, encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line_str = raw_line.strip()
            if not line_str:
                continue

            try:
                record = json.loads(line_str)
                is_corrupt = False
                err_msg = ""
            except json.JSONDecodeError as exc:
                record = None
                is_corrupt = True
                err_msg = str(exc)

            if as_json:
                if is_corrupt:
                    click.echo(
                        json.dumps(
                            {
                                "line": line_no,
                                "error": f"corrupt JSON: {err_msg}",
                                "raw": line_str,
                            }
                        )
                    )
                else:
                    click.echo(raw_line.rstrip("\r\n"))
            else:
                if is_corrupt:
                    console.print(
                        f"[bold red]Line {line_no} [CORRUPT]:[/bold red] {err_msg} -> [dim]{line_str[:300]}[/dim]"
                    )
                else:
                    rec_dict = record if isinstance(record, dict) else {}
                    ts = str(rec_dict.get("ts", "-"))
                    reason = str(rec_dict.get("reason", "-"))
                    context_val = rec_dict.get("context", {})
                    context_str = json.dumps(context_val)
                    raw_payload = rec_dict.get("payload")
                    payload_repr = repr(raw_payload)
                    if len(payload_repr) > 300:
                        payload_repr = payload_repr[:297] + "..."

                    table = Table(
                        title=f"Record {displayed + 1} (Line {line_no})", show_header=False
                    )
                    table.add_column("Field", style="bold cyan")
                    table.add_column("Value")
                    table.add_row("Timestamp", ts)
                    table.add_row("Reason", reason)
                    table.add_row("Context", context_str)
                    table.add_row("Payload", payload_repr)
                    console.print(table)

            displayed += 1
            if displayed >= limit:
                break

    ctx.exit(0)


@click.group("quarantine")
def quarantine_group() -> None:
    """Inspect and display dead-letter quarantine files and unparseable records."""
    pass


def register_quarantine_commands(main: click.Group) -> None:
    """Register quarantine group and subcommands on the main Click command group.

    Args:
        main: Top-level Click command group.
    """
    quarantine_group.add_command(quarantine_list_cmd, "list")
    quarantine_group.add_command(quarantine_show_cmd, "show")
    main.add_command(quarantine_group, "quarantine")


__all__ = [
    "QuarantineFile",
    "quarantine_group",
    "quarantine_list_cmd",
    "quarantine_show_cmd",
    "register_quarantine_commands",
    "scan_quarantine",
]
