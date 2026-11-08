"""``baseballpy run``: keep a plan running (retries, rounds, resume) with plain Python."""

import re
import signal
import threading
import types

import click
from rich.console import Console

from baseballpy.cli_ingest import _disk_usage
from baseballpy.core.config import LakeConfig
from baseballpy.core.hostlock import HostBusyError, claim_named
from baseballpy.ingest.backfill import BackfillError, load_plan
from baseballpy.ingest.queue import child_compact_runner, child_stage_runner, run_queue

console = Console()

_DURATION = re.compile(r"^(\d+(?:\.\d+)?)\s*([smhd])$")
_UNITS = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def parse_duration(text: str) -> float:
    """``90s``, ``30m``, ``6h`` or ``1d`` in seconds."""
    match = _DURATION.match(text.strip().lower())
    if match is None:
        raise click.BadParameter(f"{text!r} is not a duration; use a number and s, m, h or d (6h)")
    return float(match.group(1)) * _UNITS[match.group(2)]


@click.command("run")
@click.argument("plan_file", metavar="PLAN")
@click.option(
    "--every",
    default=None,
    help="Start a new round this long after the last one began (30m, 6h, 1d) and keep going "
    "until stopped. Without it the command ends when the plan is done.",
)
@click.option("--retries", type=click.IntRange(min=0), default=3, show_default=True)
@click.option("--wait-initial", type=click.FloatRange(min=0), default=60.0, show_default=True)
@click.option("--wait-max", type=click.FloatRange(min=0), default=900.0, show_default=True)
@click.option("--max-gb", type=click.FloatRange(min=0, min_open=True), default=None)
@click.option("--min-free-gb", type=click.FloatRange(min=0), default=5.0, show_default=True)
@click.option("--concurrency", "-c", type=click.IntRange(min=1), default=1)
@click.option(
    "--compact/--no-compact",
    default=True,
    show_default=True,
    help="After each finished stage, merge the small files it wrote (returns disk space).",
)
@click.option("--dry-run", is_flag=True, help="Show the stages and the settings; run nothing.")
@click.pass_context
def run_cmd(
    ctx: click.Context,
    plan_file: str,
    every: str | None,
    retries: int,
    wait_initial: float,
    wait_max: float,
    max_gb: float | None,
    min_free_gb: float,
    concurrency: int,
    compact: bool,
    dry_run: bool,
) -> None:
    """Work through a plan and keep it going: retry what fails, repeat it on a timer.

    Each stage runs in its own child process, so a crash or a memory spike ends only that attempt.
    A failed stage is retried with growing waits and the next stage still runs. State is kept in
    `<home>/state/queue.json`; start the command again after a restart and it resumes the unfinished
    round. Stop it with Ctrl-C. It needs no operating-system scheduler, so it works the same on
    Linux, macOS and Windows.
    """
    interval = parse_duration(every) if every else None
    try:
        plan = load_plan(plan_file)
    except BackfillError as exc:
        raise click.ClickException(str(exc)) from exc
    names = [stage.name for stage in plan.stages]
    if dry_run:
        console.print(f"Plan {plan_file!r}: {len(names)} stage(s): {', '.join(names)}")
        console.print(
            f"retries {retries}, waits {wait_initial:g}-{wait_max:g} s, "
            f"{'every ' + every if every else 'one round'}"
        )
        ctx.exit(0)

    config = LakeConfig()
    try:
        claim_named(
            config.state_root,
            "queue",
            "another baseballpy run is already working on this home; stop it first "
            f"(its state is in {config.state_root / 'queue.json'})",
        )
    except HostBusyError as exc:
        raise click.ClickException(str(exc)) from exc

    stop = threading.Event()

    def request_stop(signum: int, frame: types.FrameType | None) -> None:
        console.print("[yellow]Stopping: the running stage is ended and can be resumed.[/yellow]")
        stop.set()

    previous = {}
    for name in ("SIGINT", "SIGTERM"):
        number = getattr(signal, name, None)
        if number is not None:
            previous[number] = signal.signal(number, request_stop)
    extra = ["--min-free-gb", str(min_free_gb), "--concurrency", str(concurrency)]
    if max_gb is not None:
        extra += ["--max-gb", str(max_gb)]
    runner = child_stage_runner(plan_file, extra, stop)
    sources = {stage.name: stage.sources for stage in plan.stages}
    compactor = child_compact_runner(lambda name: sources[name], stop) if compact else None
    try:
        report = run_queue(
            plan_file,
            names,
            runner,
            state_path=config.state_root / "queue.json",
            stop=stop,
            every=interval,
            retries=retries,
            initial_wait=wait_initial,
            max_wait=wait_max,
            after_stage=compactor,
            on_event=lambda message: console.print(message),
        )
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    free_gb = _disk_usage(config.home)[0] / 1e9
    console.print(
        f"{report.rounds} round(s); failed: {', '.join(report.failed) or 'none'}; "
        f"{free_gb:.1f} GB free." + (f" Stopped: {report.stopped}." if report.stopped else "")
    )
    ctx.exit(report.exit_code)


def register_queue_command(main: click.Group) -> None:
    """Add ``run`` to the top-level group."""
    main.add_command(run_cmd, "run")


__all__ = ["parse_duration", "register_queue_command", "run_cmd"]
