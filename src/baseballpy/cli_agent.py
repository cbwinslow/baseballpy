"""CLI commands for multi-agent coordination, lock claiming, releasing, and board display."""

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from baseballpy.core.config import find_project_root

console = Console()

STALE_LOCK_HOURS = 4


def _board_and_log_paths() -> tuple[Path, Path]:
    """Find root and return paths to AGENT_BOARD.md and agent_log.jsonl."""
    root = find_project_root() or Path.cwd()
    agents_dir = root / "docs" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    board_path = agents_dir / "AGENT_BOARD.md"
    log_path = agents_dir / "agent_log.jsonl"
    return board_path, log_path


def _default_agent() -> str:
    """Return default agent identifier from env or username."""
    return os.environ.get("BASEBALLPY_AGENT") or os.environ.get("USERNAME") or "Agent"


def _parse_utc_timestamp(ts_str: str) -> datetime | None:
    """Parse 'YYYY-MM-DD HH:MM UTC' or ISO string to datetime."""
    clean = ts_str.strip().replace(" UTC", "")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(clean, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(clean).astimezone(UTC)
    except ValueError:
        return None


def _log_event(
    log_path: Path,
    agent: str,
    event: str,
    task_id: str,
    details: str,
) -> None:
    """Append a structured JSON line to agent_log.jsonl."""
    record = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": agent,
        "session_id": os.environ.get("BASEBALLPY_SESSION_ID", f"{agent.lower()}-session"),
        "event": event,
        "task_id": task_id,
        "details": details,
    }
    with open(log_path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record) + "\n")


@click.group("agent")
def agent_group() -> None:
    """Coordinate parallel AI agent sessions with checkout locks and status board."""
    pass


@agent_group.command("board")
def agent_board() -> None:
    """Display active checkouts and recent handoffs from the agent board."""
    board_path, _ = _board_and_log_paths()
    if not board_path.exists():
        console.print("[dim]No AGENT_BOARD.md found in docs/agents/.[/dim]")
        return

    text = board_path.read_text(encoding="utf-8").replace("\r\n", "\n")

    # Parse Active Checkouts
    active_match = re.search(
        r"^## Active Checkouts[^\n]*\n(.*?)(?=\n---|\n^## Recent Completed|\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    checkouts_raw = active_match.group(1).strip() if active_match else ""

    table_active = Table(title="AI Agent Active Checkouts (Locked Areas)", show_lines=True)
    table_active.add_column("Task", style="bold cyan")
    table_active.add_column("Agent", style="blue")
    table_active.add_column("Claimed At", style="dim")
    table_active.add_column("Elapsed", justify="right")
    table_active.add_column("Locked Areas", style="yellow")
    table_active.add_column("Status")

    now = datetime.now(UTC)
    count_active = 0

    if checkouts_raw and "*(No active checkouts" not in checkouts_raw:
        # Blocks start with "- **Task:**"
        blocks = re.split(r"\n(?=- \*\*Task:\*\*)", checkouts_raw)
        for block in blocks:
            if not block.strip().startswith("- **Task:**"):
                continue
            count_active += 1
            task_m = re.search(r"- \*\*Task:\*\*\s*(.+)", block)
            agent_m = re.search(r"- \*\*Agent:\*\*\s*(.+)", block)
            claimed_m = re.search(r"- \*\*Claimed At:\*\*\s*(.+)", block)
            status_m = re.search(r"- \*\*Status:\*\*\s*(.+)", block)
            areas_m = re.findall(r"-\s*`([^`]+)`", block)

            task_name = task_m.group(1).strip() if task_m else "Unknown"
            agent_name = agent_m.group(1).strip() if agent_m else "Unknown"
            claimed_str = claimed_m.group(1).strip() if claimed_m else ""
            status_str = status_m.group(1).strip() if status_m else "In progress"
            areas_str = ", ".join(areas_m) if areas_m else "None"

            elapsed_str = "-"
            is_stale = False
            if claimed_str:
                dt = _parse_utc_timestamp(claimed_str)
                if dt:
                    diff = now - dt
                    hours = int(diff.total_seconds() // 3600)
                    mins = int((diff.total_seconds() % 3600) // 60)
                    elapsed_str = f"{hours}h {mins}m"
                    if diff > timedelta(hours=STALE_LOCK_HOURS):
                        is_stale = True

            elapsed_display = (
                f"[bold red]{elapsed_str} (STALE >4h)[/bold red]" if is_stale else elapsed_str
            )
            table_active.add_row(
                task_name,
                agent_name,
                claimed_str,
                elapsed_display,
                areas_str,
                status_str,
            )

    if count_active == 0:
        console.print("[green]No active checkouts. All files and tracks are unlocked.[/green]\n")
    else:
        console.print(table_active)
        console.print("")

    # Parse Recent Handoffs
    handoff_match = re.search(
        r"^## Recent Completed Handoffs[^\n]*\n(.*?)(?=\n---|\n^## Team Notes|\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    handoffs_raw = handoff_match.group(1).strip() if handoff_match else ""
    if handoffs_raw:
        table_handoffs = Table(title="Recent Agent Handoffs", show_lines=True)
        table_handoffs.add_column("Completed (UTC)", style="dim")
        table_handoffs.add_column("Agent", style="blue")
        table_handoffs.add_column("Tasks", style="bold cyan")
        table_handoffs.add_column("Summary")

        entries = re.split(r"\n(?=- \*\*\d{4}-\d{2}-\d{2})", handoffs_raw)
        for entry in entries[:8]:  # show up to 8
            header_m = re.search(r"- \*\*(\d{4}-\d{2}-\d{2}[^\]]+)\]:\*\*", entry)
            tasks_m = re.search(r"- \*\*Tasks:\*\*\s*(.+)", entry)
            sum_m = re.search(r"- \*\*Summary:\*\*\s*(.+)", entry)
            if header_m:
                date_agent = header_m.group(1).strip()
                # e.g. "2026-11-06 22:46 UTC [Claude - Session 1"
                parts = date_agent.split(" [")
                dt_str = parts[0]
                ag_str = parts[1] if len(parts) > 1 else ""
                t_str = tasks_m.group(1).strip() if tasks_m else ""
                s_str = sum_m.group(1).strip() if sum_m else ""
                table_handoffs.add_row(dt_str, ag_str, t_str, s_str)
        console.print(table_handoffs)


@agent_group.command("claim")
@click.argument("task_id")
@click.option("--agent", default=None, help="Name of agent claiming the task.")
@click.option("--files", "-f", default=None, help="Comma-separated files or paths to lock.")
@click.option("--note", default="In progress", help="Brief note or status.")
@click.option("--force", is_flag=True, help="Force override of an existing active lock.")
def agent_claim(
    task_id: str,
    agent: str | None,
    files: str | None,
    note: str,
    force: bool,
) -> None:
    """Claim a task lock on the Agent Board to prevent clobbering."""
    board_path, log_path = _board_and_log_paths()
    if not board_path.exists():
        console.print(f"[bold red]Error:[/bold red] {board_path} not found.")
        raise SystemExit(1)

    agent_name = agent or _default_agent()
    text = board_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    now_utc = datetime.now(UTC)
    now_str = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    # Check for existing lock on task_id
    escaped_id = re.escape(task_id)
    existing_pattern = re.compile(
        rf"- \*\*Task:\*\*[^\n]*{escaped_id}[^\n]*\n"
        r"(?: {2,}[^\n]+\n)*",
        re.MULTILINE,
    )
    match = existing_pattern.search(text)
    if match:
        block = match.group(0)
        claimed_m = re.search(r"- \*\*Claimed At:\*\*\s*(.+)", block)
        claimed_str = claimed_m.group(1).strip() if claimed_m else ""
        agent_m = re.search(r"- \*\*Agent:\*\*\s*(.+)", block)
        locked_agent = agent_m.group(1).strip() if agent_m else "another agent"

        is_stale = False
        if claimed_str:
            dt = _parse_utc_timestamp(claimed_str)
            if dt and (now_utc - dt) > timedelta(hours=STALE_LOCK_HOURS):
                is_stale = True

        if not force and not is_stale:
            console.print(
                f"[bold red]Refused:[/bold red] Task [cyan]{task_id}[/cyan] is already claimed by "
                f"[blue]{locked_agent}[/blue] (claimed at {claimed_str}). "
                "Use --force to override if intentional."
            )
            raise SystemExit(1)

        if is_stale:
            console.print(
                f"[yellow]Warning:[/yellow] Overriding stale lock (> {STALE_LOCK_HOURS}h) "
                f"for task [cyan]{task_id}[/cyan] (held by {locked_agent})."
            )
            _log_event(
                log_path,
                agent_name,
                "STALE_LOCK_OVERRIDDEN",
                task_id,
                f"Overrode stale lock held by {locked_agent} since {claimed_str}",
            )
        # Remove existing block
        text = text[: match.start()] + text[match.end() :]

    # Format new block
    file_lines = ""
    if files:
        for f in files.split(","):
            clean_f = f.strip()
            if clean_f:
                file_lines += f"    - `{clean_f}`\n"
    if not file_lines:
        file_lines = "    - `(none specified)`\n"

    new_block = (
        f"- **Task:** {task_id}\n"
        f"  - **Agent:** {agent_name}\n"
        f"  - **Claimed At:** {now_str}\n"
        f"  - **Locked Areas:**\n"
        f"{file_lines}"
        f"  - **Status:** {note}\n\n"
    )

    # Insert under ## Active Checkouts
    active_header = "## Active Checkouts (Locked — Do Not Disturb)\n\n"
    if active_header in text:
        text = text.replace(active_header, active_header + new_block, 1)
    else:
        # Fallback if header variation
        text = re.sub(
            r"(## Active Checkouts[^\n]*\n+)",
            r"\1" + new_block,
            text,
            count=1,
        )

    # Remove placeholder if present
    text = text.replace("*(No active checkouts currently held — all tracks clear.)*\n\n", "")

    board_path.write_text(text, encoding="utf-8", newline="\n")
    _log_event(
        log_path,
        agent_name,
        "TASK_CLAIMED",
        task_id,
        f"Claimed task {task_id} (files: {files or 'none'}; note: {note})",
    )
    console.print(
        f"[bold green]Claimed task:[/bold green] [cyan]{task_id}[/cyan] by [blue]{agent_name}[/blue]"
    )


@agent_group.command("release")
@click.argument("task_id")
@click.argument("summary")
@click.option("--agent", default=None, help="Name of agent releasing the task.")
def agent_release(task_id: str, summary: str, agent: str | None) -> None:
    """Release a task lock and record completion in handoffs and machine log."""
    board_path, log_path = _board_and_log_paths()
    if not board_path.exists():
        console.print(f"[bold red]Error:[/bold red] {board_path} not found.")
        raise SystemExit(1)

    agent_name = agent or _default_agent()
    text = board_path.read_text(encoding="utf-8").replace("\r\n", "\n")
    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Locate active checkout for task_id
    escaped_id = re.escape(task_id)
    block_pattern = re.compile(
        rf"- \*\*Task:\*\*[^\n]*{escaped_id}[^\n]*\n"
        r"(?: {2,}[^\n]+\n)*\n*",
        re.MULTILINE,
    )
    match = block_pattern.search(text)
    if match:
        text = text[: match.start()] + text[match.end() :]

    # Format handoff entry
    handoff_entry = (
        f"- **{now_str} [{agent_name}]:**\n"
        f"  - **Tasks:** `{task_id}`.\n"
        f"  - **Summary:** {summary}\n\n"
    )

    # Prepend under ## Recent Completed Handoffs
    handoff_header = "## Recent Completed Handoffs\n\n"
    if handoff_header in text:
        text = text.replace(handoff_header, handoff_header + handoff_entry, 1)
    else:
        text = re.sub(
            r"(## Recent Completed Handoffs[^\n]*\n+)",
            r"\1" + handoff_entry,
            text,
            count=1,
        )

    board_path.write_text(text, encoding="utf-8", newline="\n")
    _log_event(
        log_path,
        agent_name,
        "TASK_COMPLETED",
        task_id,
        summary,
    )
    console.print(
        f"[bold green]Released task:[/bold green] [cyan]{task_id}[/cyan] with handoff summary."
    )


def register_agent_commands(cli: click.Group) -> None:
    """Register agent command group on the main CLI entrypoint."""
    cli.add_command(agent_group)
