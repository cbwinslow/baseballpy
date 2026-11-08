"""A supervisor that keeps a plan running: retries, rounds, a state file, no OS scheduler.

``run_queue`` works through the stages of a backfill plan. Each stage attempt is a function that
returns an exit code (the real one runs ``baseballpy backfill --stage`` in a child process, so a
crash or a memory spike ends only that attempt). A failed stage is retried with exponential backoff
and jitter (``tenacity``: ``wait_exponential`` plus ``wait_random``) and never blocks the next stage. With ``every`` the queue starts a new
round after that interval and runs until stopped. Progress is written to a small JSON state file,
so a restarted supervisor continues the unfinished round.

Exit codes of ``backfill`` decide what happens: 0 done, 1 failed jobs (retry), 2 stopped by a size
or disk limit (a retry would stop the same way: the queue stops), 130 interrupted (the queue stops).
"""

import logging
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import msgspec
import tenacity

from baseballpy.core.atomic import atomic_write

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_LIMIT = 2
EXIT_INTERRUPTED = 130

#: exit codes that end a stage for good: done, stopped by a limit, interrupted
_FINAL = frozenset({0, 2, 130})

PENDING = "pending"
DONE = "done"
FAILED = "failed"


class StageState(msgspec.Struct):
    """What the queue knows about one stage in the current round."""

    status: str = PENDING
    attempts: int = 0
    last_exit: int | None = None
    last_error: str = ""
    finished_at: str = ""


class QueueState(msgspec.Struct):
    """The state file: the plan, the round, and every stage's progress."""

    plan: str
    round: int = 1
    round_started_at: str = ""
    next_round_at: str = ""
    updated_at: str = ""
    stages: dict[str, StageState] = {}


@dataclass
class QueueReport:
    """How a queue run ended."""

    rounds: int = 0
    failed: list[str] = field(default_factory=list)
    stopped: str = ""

    @property
    def exit_code(self) -> int:
        """130 when interrupted, 2 when a limit stopped it, 1 when a stage ended failed, else 0."""
        if self.stopped == "interrupted":
            return EXIT_INTERRUPTED
        if self.stopped:
            return EXIT_LIMIT
        return EXIT_FAILED if self.failed else EXIT_OK


def _now() -> datetime:
    return datetime.now(UTC)


def load_state(path: Path, plan: str) -> QueueState:
    """The saved state for ``plan``, or a fresh one (also when the file is for another plan)."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return QueueState(plan=plan)
    try:
        state = msgspec.json.decode(data, type=QueueState)
    except (msgspec.DecodeError, UnicodeDecodeError):
        logger.warning("queue state %s is damaged; starting a fresh round", path)
        return QueueState(plan=plan)
    return state if state.plan == plan else QueueState(plan=plan)


def read_state(path: Path) -> QueueState | None:
    """The saved state whatever its plan, or None when there is none or it is unreadable."""
    try:
        return msgspec.json.decode(path.read_bytes(), type=QueueState)
    except (FileNotFoundError, msgspec.DecodeError, UnicodeDecodeError):
        return None


def save_state(path: Path, state: QueueState) -> None:
    """Write the state atomically."""
    state.updated_at = _now().isoformat()
    with atomic_write(path) as part:
        part.write_bytes(msgspec.json.encode(state))


def run_queue(
    plan: str,
    stages: Sequence[str],
    run_stage: Callable[[str], int],
    *,
    state_path: Path,
    stop: threading.Event,
    every: float | None = None,
    retries: int = 3,
    initial_wait: float = 60.0,
    max_wait: float = 900.0,
    max_rounds: int | None = None,
    failed_wait: float = 1800.0,
    after_stage: Callable[[str], int] | None = None,
    on_event: Callable[[str], None] | None = None,
) -> QueueReport:
    """Run ``stages`` in order, round after round, until done (no ``every``) or stopped.

    ``run_stage(name)`` returns an exit code. A stage is tried up to ``retries + 1`` times; one
    that is still failing is marked failed and the next stage runs. ``stop`` ends the run at the
    next safe point (it also interrupts the waits). ``max_rounds`` bounds the rounds (tests).
    A round with failed stages does not wait for the whole ``every`` interval: it runs again after
    ``failed_wait`` seconds (30 minutes) with only the failed stages (a disk that compaction frees,
    a host that was down).
    ``after_stage(name)`` runs after a stage ends well (compaction) in the background, beside the next
    stage (one at a time: the next one waits for it); a failure there is recorded and reported but
    does not fail the stage.
    """

    def say(message: str) -> None:
        logger.info(message)
        if on_event is not None:
            on_event(message)

    state = load_state(state_path, plan)
    report = QueueReport()
    background = _Background(after_stage, state, state_path, say)
    try:
        return _run_rounds(
            stages,
            run_stage,
            state,
            state_path,
            stop,
            every,
            retries,
            initial_wait,
            max_wait,
            max_rounds,
            failed_wait,
            background,
            report,
            say,
        )
    finally:
        background.close()


def _run_rounds(
    stages: Sequence[str],
    run_stage: Callable[[str], int],
    state: QueueState,
    state_path: Path,
    stop: threading.Event,
    every: float | None,
    retries: int,
    initial_wait: float,
    max_wait: float,
    max_rounds: int | None,
    failed_wait: float,
    background: "_Background",
    report: QueueReport,
    say: Callable[[str], None],
) -> QueueReport:
    while True:
        if not state.round_started_at:
            state.round_started_at = _now().isoformat()
        for name in stages:
            state.stages.setdefault(name, StageState())
        round_began = time.monotonic()
        report.failed = []
        for name in stages:
            stage = state.stages[name]
            if stage.status == DONE:
                say(f"round {state.round}: {name} already done, skipping")
                continue
            if stop.is_set():
                report.stopped = "interrupted"
                break
            code = _attempt(
                name,
                stage,
                run_stage,
                state,
                state_path,
                stop,
                retries,
                initial_wait,
                max_wait,
                say,
            )
            save_state(state_path, state)  # a stage that just ended is on disk before anything else
            if code == EXIT_OK:
                if not stop.is_set():
                    background.start(name)
                continue
            if code == EXIT_INTERRUPTED or stop.is_set():
                report.stopped = "interrupted"
                break
            if code == EXIT_LIMIT:
                report.stopped = f"{name} stopped at a size or disk limit"
                break
            report.failed.append(name)
        save_state(state_path, state)
        report.rounds = state.round
        if report.stopped:
            return report
        if every is None or (max_rounds is not None and state.round >= max_rounds):
            return report
        wait = max(0.0, every - (time.monotonic() - round_began))
        if report.failed:
            wait = min(wait, failed_wait)  # what failed is tried again soon, not tomorrow
        state.next_round_at = datetime.fromtimestamp(time.time() + wait, UTC).isoformat()
        save_state(state_path, state)
        say(
            f"round {state.round} finished ({len(report.failed)} failed); next round in {wait:.0f} s"
        )
        if stop.wait(wait):
            report.stopped = "interrupted"
            return report
        if report.failed:
            continue  # the same round: stages that are done stay done, only the failed ones run
        state.round += 1
        state.round_started_at = ""
        state.next_round_at = ""
        state.stages = {}


class _Background:
    """The after-stage step of finished stages (compaction), run beside the next download.

    Compaction used to run between stages, and at the size of a season (tens of thousands of small
    files) it took longer than the download: the download sat idle for 45 minutes. It touches only
    the finished season's files, so it can run while the next season downloads; the next step waits
    for the one before it, and the queue waits for the last one before it ends.
    """

    def __init__(
        self,
        work: Callable[[str], int] | None,
        state: QueueState,
        state_path: Path,
        say: Callable[[str], None],
    ) -> None:
        self._work = work
        self._state = state
        self._state_path = state_path
        self._say = say
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="after-stage")
        self._pending: tuple[str, Future[int]] | None = None

    def start(self, name: str) -> None:
        """Run the step for ``name`` in the background (after the previous one has ended)."""
        if self._work is None:
            return
        self.settle()
        self._pending = (name, self._pool.submit(self._work, name))

    def settle(self) -> None:
        """Wait for the running step and record how it ended."""
        if self._pending is None:
            return
        name, future = self._pending
        self._pending = None
        code = future.result()
        if code != EXIT_OK:
            stage = self._state.stages.get(name)
            message = f"after-stage step exited with {code}"
            if stage is not None:
                stage.last_error = message
                save_state(self._state_path, self._state)
            self._say(f"{name}: {message}")

    def close(self) -> None:
        """Wait for the last step and release the thread."""
        try:
            self.settle()
        finally:
            self._pool.shutdown(wait=True)


def _wait(stop: threading.Event, seconds: float) -> None:
    """Sleep that ends early when the queue is told to stop."""
    stop.wait(seconds)


def _attempt(
    name: str,
    stage: StageState,
    run_stage: Callable[[str], int],
    state: QueueState,
    state_path: Path,
    stop: threading.Event,
    retries: int,
    initial_wait: float,
    max_wait: float,
    say: Callable[[str], None],
) -> int:
    """Run one stage with retries; record every attempt in the state file; return the last code."""

    def once() -> int:
        stage.attempts += 1
        say(f"round {state.round}: {name}, attempt {stage.attempts}")
        save_state(state_path, state)
        try:
            code = run_stage(name)
        except OSError as exc:  # the child could not even start: a failed attempt, not a crash
            stage.last_error = f"{type(exc).__name__}: {exc}"
            code = EXIT_FAILED
        stage.last_exit = code
        if code != EXIT_OK:
            stage.last_error = stage.last_error or f"exit code {code}"
            say(f"round {state.round}: {name} exited with {code}")
        return code

    retrying = tenacity.Retrying(
        stop=tenacity.stop_after_attempt(retries + 1),
        wait=tenacity.wait_exponential(multiplier=initial_wait, max=max_wait)
        + tenacity.wait_random(0, initial_wait),
        # any other code is a failed or crashed attempt (a native crash is 139, -11 or 0xC0000005)
        retry=tenacity.retry_if_result(lambda code: code not in _FINAL and not stop.is_set()),
        sleep=lambda seconds: _wait(stop, seconds),
        retry_error_callback=lambda state_: (
            state_.outcome.result() if state_.outcome else EXIT_FAILED
        ),
    )
    stage.attempts = 0
    code = int(retrying(once))
    stage.finished_at = _now().isoformat()
    if code == EXIT_OK:
        stage.status, stage.last_error = DONE, ""
    elif code not in _FINAL:
        stage.status = FAILED
    return code


def _run_child(
    arguments: Sequence[str],
    stop: threading.Event,
    popen: Callable[..., "subprocess.Popen[bytes]"],
    grace: float,
) -> int:
    """Run ``baseballpy ARGUMENTS`` in a child process; end the child when ``stop`` is set.

    The child is the current Python (``sys.executable``), so no console script has to be on the
    ``PATH`` and it behaves the same on every OS. The child is terminated (and killed after
    ``grace`` seconds) and the call counts as interrupted.
    """
    command = [sys.executable, "-c", "from baseballpy.cli import main; main()", *arguments]
    child = popen(command)
    while True:
        try:
            return int(child.wait(timeout=1.0))
        except subprocess.TimeoutExpired:
            if not stop.is_set():
                continue
        child.terminate()
        try:
            child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        return EXIT_INTERRUPTED


def child_stage_runner(
    plan: str,
    extra_args: Sequence[str],
    stop: threading.Event,
    *,
    popen: Callable[..., "subprocess.Popen[bytes]"] = subprocess.Popen,
    grace: float = 30.0,
) -> Callable[[str], int]:
    """A ``run_stage`` that runs ``baseballpy backfill PLAN --stage NAME`` in a child process."""

    def run(name: str) -> int:
        return _run_child(["backfill", plan, "--stage", name, *extra_args], stop, popen, grace)

    return run


def child_compact_runner(
    sources_of: Callable[[str], Sequence[str]],
    stop: threading.Event,
    *,
    popen: Callable[..., "subprocess.Popen[bytes]"] = subprocess.Popen,
    grace: float = 30.0,
) -> Callable[[str], int]:
    """An ``after_stage`` that runs ``baseballpy compact --source S`` for the sources of a stage.

    Compaction merges the small files a stage wrote (a season of games is tens of thousands) into a
    few big ones, which returns disk space, and it brings files written under an older schema up to
    date (ADR 87) only when asked: the queue passes ``--no-migrate``, because the one-time
    rewrite of every old file takes hours and must not hold up the next download.
    """

    def run(name: str) -> int:
        worst = EXIT_OK
        for source in sources_of(name):
            code = _run_child(["compact", "--no-migrate", "--source", source], stop, popen, grace)
            worst = worst or code
        return worst

    return run


__all__ = [
    "EXIT_FAILED",
    "EXIT_INTERRUPTED",
    "EXIT_LIMIT",
    "EXIT_OK",
    "QueueReport",
    "QueueState",
    "StageState",
    "child_compact_runner",
    "child_stage_runner",
    "load_state",
    "read_state",
    "run_queue",
    "save_state",
]
