"""CLI commands for inspecting DuckDB catalog views, running queries, and launching the DuckDB shell."""

import csv
import io
import json
import shutil
from pathlib import Path
from typing import Any

import click
import duckdb
from rich.console import Console
from rich.table import Table

from baseballpy.core.sql import quote_ident
from baseballpy.database import BaseballDatabase, DatabaseReadOnlyError

console = Console()


def get_read_only_database() -> BaseballDatabase:
    """Instantiate a read-only BaseballDatabase and verify that the database file exists.

    Returns:
        BaseballDatabase configured in read-only mode.

    Raises:
        click.ClickException: If the underlying DuckDB database file does not exist.
    """
    db = BaseballDatabase(read_only=True)
    if str(db.db_path) != ":memory:" and not db.db_path.exists():
        raise click.ClickException(
            f"Database file not found at {db.db_path}; run `baseballpy db sync` first"
        )
    return db


def exec_duckdb(executable: str, db_path: Path) -> None:
    """Execute the duckdb CLI replacing the current process.

    Args:
        executable: Path to the duckdb executable.
        db_path: Path to the DuckDB database file.
    """
    import os

    os.execvp(executable, [executable, str(db_path)])


@click.command("views")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output views as newline-delimited JSON objects.",
)
@click.pass_context
def db_views_cmd(ctx: click.Context, as_json: bool) -> None:
    """List registered views in the DuckDB database along with their row counts."""
    db = get_read_only_database()
    try:
        with db.session() as con:
            rows = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_type = 'VIEW' ORDER BY table_name"
            ).fetchall()
            view_data: list[tuple[str, int]] = []
            for (view_name,) in rows:
                quoted = quote_ident(view_name)
                counted = con.execute(f"SELECT count(*) FROM {quoted}").fetchone()
                if counted is None:
                    raise click.ClickException(f"count(*) returned no row for view {view_name}")
                view_data.append((view_name, int(counted[0])))
    except DatabaseReadOnlyError as exc:
        raise click.ClickException(f"{exc}; run `baseballpy db sync` first") from exc
    except duckdb.Error as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        for view_name, count in view_data:
            click.echo(json.dumps({"view": view_name, "rows": count}))
    else:
        table = Table(title="Database Views")
        table.add_column("View", style="cyan")
        table.add_column("Rows", justify="right")
        for view_name, count in view_data:
            table.add_row(view_name, f"{count:,}")
        console.print(table)

    ctx.exit(0)


@click.command("query")
@click.argument("sql", type=str)
@click.option(
    "--limit",
    "-l",
    type=click.IntRange(min=0),
    default=100,
    help="Maximum rows to display (0 = unlimited, default 100).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Output rows as newline-delimited JSON objects.",
)
@click.option(
    "--csv",
    "as_csv",
    is_flag=True,
    help="Output rows as CSV.",
)
@click.pass_context
def db_query_cmd(
    ctx: click.Context,
    sql: str,
    limit: int,
    as_json: bool,
    as_csv: bool,
) -> None:
    """Run one SQL query read-only against the DuckDB database and print the results."""
    if as_json and as_csv:
        raise click.BadParameter("Cannot specify both --json and --csv")

    db = get_read_only_database()
    try:
        with db.session() as con:
            cursor = con.execute(sql)
            columns: list[str] = (
                [col[0] for col in cursor.description] if cursor.description else []
            )
            rows: list[tuple[Any, ...]] = (
                cursor.fetchmany(limit) if limit > 0 else cursor.fetchall()
            )
    except DatabaseReadOnlyError as exc:
        raise click.ClickException(f"{exc}; run `baseballpy db sync` first") from exc
    except duckdb.Error as exc:
        raise click.ClickException(str(exc)) from exc

    if as_json:
        for row in rows:
            click.echo(json.dumps(dict(zip(columns, row, strict=False)), default=str))
    elif as_csv:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        if columns:
            writer.writerow(columns)
        for row in rows:
            writer.writerow(row)
        click.echo(buffer.getvalue(), nl=False)
    else:
        table = Table(title="Query Results")
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*(str(v) if v is not None else "" for v in row))
        console.print(table)

    ctx.exit(0)


@click.command("shell")
@click.pass_context
def db_shell_cmd(ctx: click.Context) -> None:
    """Open an interactive DuckDB CLI session connected to the catalog database."""
    db = get_read_only_database()
    executable = shutil.which("duckdb")
    if not executable:
        raise click.ClickException(
            "DuckDB executable 'duckdb' not found on PATH. "
            "Install DuckDB (e.g. `winget install DuckDB.cli`, `brew install duckdb`, "
            "or download from https://duckdb.org) or use `baseballpy db query`."
        )
    exec_duckdb(executable, db.db_path)
    ctx.exit(0)


def register_db_commands(db_group: click.Group) -> None:
    """Register views, query, and shell subcommands on an existing Click db group.

    Args:
        db_group: Existing Click command group for db commands.
    """
    db_group.add_command(db_views_cmd, "views")
    db_group.add_command(db_query_cmd, "query")
    db_group.add_command(db_shell_cmd, "shell")


__all__ = [
    "db_query_cmd",
    "db_shell_cmd",
    "db_views_cmd",
    "exec_duckdb",
    "get_read_only_database",
    "register_db_commands",
]
