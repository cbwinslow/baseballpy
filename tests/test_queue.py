"""The download queue: stages in order, retries, rounds, resume, one supervisor, a child process."""

import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.cli_queue import parse_duration
from baseballpy.core.hostlock import HostBusyError, claim_named, release_all
from baseballpy.ingest.backfill import BackfillError, BackfillPlan, Stage, select_stages
from baseballpy.ingest.queue import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_LIMIT,
    EXIT_OK,
    child_stage_runner,
    load_state,
    run_queue,
)

PLAN = BackfillPlan(tuple(Stage(name=n, sources=("lahman",)) for n in ("a", "b", "c")))


def test_select_stages_by_name_and_number() -> None:
    chosen = select_stages(PLAN, ["c", "2"])
    assert [s.name for s in chosen.stages] == ["b", "c"]  # plan order, not the order asked
    assert select_stages(PLAN, []) is PLAN


def test_select_stages_refuses_an_unknown_stage() -> None:
    with pytest.raises(BackfillError, match=r"no stage 'zzz'.*1: a, 2: b, 3: c"):
        select_stages(PLAN, ["zzz"])
    with pytest.raises(BackfillError, match="no stage '9'"):
        select_stages(PLAN, ["9"])


def _fast(tmp_path: Path, **kwargs: Any) -> dict[str, Any]:
    return {
        "state_path": tmp_path / "state" / "queue.json",
        "stop": threading.Event(),
        "initial_wait": 0.0,
        "max_wait": 0.0,
        **kwargs,
    }


def test_a_failed_stage_is_retried_and_does_not_block_the_next(tmp_path: Path) -> None:
    calls: list[str] = []

    def run(name: str) -> int:
        calls.append(name)
        if name == "a":
            return EXIT_OK if calls.count("a") == 3 else EXIT_FAILED  # fails twice, then works
        return EXIT_FAILED if name == "b" else EXIT_OK  # b never works

    report = run_queue("p", ["a", "b", "c"], run, retries=2, **_fast(tmp_path))
    assert calls == ["a", "a", "a", "b", "b", "b", "c"]
    assert report.failed == ["b"] and report.exit_code == 1
    state = load_state(tmp_path / "state" / "queue.json", "p")
    assert (state.stages["a"].status, state.stages["a"].attempts) == ("done", 3)
    assert (state.stages["b"].status, state.stages["b"].last_exit) == ("failed", EXIT_FAILED)
    assert state.stages["c"].status == "done"


def test_a_stage_stopped_by_a_limit_is_not_retried(tmp_path: Path) -> None:
    calls: list[str] = []

    def run(name: str) -> int:
        calls.append(name)
        return EXIT_LIMIT

    report = run_queue("p", ["a", "b"], run, retries=5, **_fast(tmp_path))
    assert calls == ["a"]  # not retried, and the queue stops
    assert "limit" in report.stopped and report.exit_code == EXIT_LIMIT


def test_every_starts_new_rounds_until_stopped(tmp_path: Path) -> None:
    stop = threading.Event()
    calls: list[str] = []

    def run(name: str) -> int:
        calls.append(name)
        if len(calls) == 2:
            stop.set()  # told to stop during the second round
        return EXIT_OK

    options = _fast(tmp_path, stop=stop)
    report = run_queue("p", ["a"], run, every=0.01, **options)
    assert calls == ["a", "a"] and report.rounds == 2
    assert report.exit_code == EXIT_INTERRUPTED


def test_a_restart_skips_the_stages_already_done(tmp_path: Path) -> None:
    first_stop = threading.Event()

    def interrupted(name: str) -> int:
        if name == "b":
            first_stop.set()
            return EXIT_INTERRUPTED
        return EXIT_OK

    first = run_queue("p", ["a", "b", "c"], interrupted, **_fast(tmp_path, stop=first_stop))
    assert first.exit_code == EXIT_INTERRUPTED
    calls: list[str] = []

    def again(name: str) -> int:
        calls.append(name)
        return EXIT_OK

    second = run_queue("p", ["a", "b", "c"], again, **_fast(tmp_path))
    assert calls == ["b", "c"] and second.exit_code == 0  # a was done in the unfinished round


def test_a_state_file_of_another_plan_or_a_damaged_one_starts_fresh(tmp_path: Path) -> None:
    path = tmp_path / "queue.json"
    path.write_bytes(b"{not json")
    assert load_state(path, "p").round == 1
    run_queue("p", ["a"], lambda _n: EXIT_OK, **{**_fast(tmp_path), "state_path": path})
    assert load_state(path, "p").stages["a"].status == "done"
    assert load_state(path, "other").stages == {}


_HOLD = (
    "import sys\n"
    "from pathlib import Path\n"
    "from baseballpy.core.hostlock import claim_named\n"
    "claim_named(Path(sys.argv[1]), 'queue', 'busy')\n"
    "print('held', flush=True)\n"
    "sys.stdin.readline()\n"
)


def test_only_one_supervisor_runs_per_home(tmp_path: Path) -> None:
    holder = subprocess.Popen(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", _HOLD, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        with pytest.raises(HostBusyError, match="busy"):
            claim_named(tmp_path, "queue", "busy")
    finally:
        assert holder.stdin is not None
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=30)
        release_all(tmp_path)
    claim_named(tmp_path, "queue", "busy")  # free once the holder is gone
    release_all(tmp_path)


class _Child:
    """A stand-in for ``subprocess.Popen`` that finishes with a code, or never does."""

    instances: list["_Child"] = []

    def __init__(self, command: list[str], code: int | None) -> None:
        self.command, self.code = command, code
        self.terminated = False
        _Child.instances.append(self)

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None and not self.terminated:
            raise subprocess.TimeoutExpired(self.command, timeout or 0)
        return self.code if self.code is not None else -15

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


def test_the_child_runner_uses_the_current_python_and_stops_the_child() -> None:
    _Child.instances = []
    stop = threading.Event()
    run = child_stage_runner(
        "daily", ["--min-free-gb", "5"], stop, popen=lambda cmd: _Child(cmd, 1)
    )
    assert run("mlb current") == 1
    command = _Child.instances[0].command
    assert command[0] == sys.executable
    assert command[2:4] == ["from baseballpy.cli import main; main()", "backfill"]
    assert command[4:] == ["daily", "--stage", "mlb current", "--min-free-gb", "5"]

    hanging = child_stage_runner("daily", [], stop, popen=lambda cmd: _Child(cmd, None))
    stop.set()
    assert hanging("x") == EXIT_INTERRUPTED and _Child.instances[-1].terminated


def test_durations() -> None:
    assert parse_duration("90s") == 90 and parse_duration("30m") == 1800
    assert parse_duration("6h") == 21600 and parse_duration("1d") == 86400
    with pytest.raises(click.BadParameter):
        parse_duration("soon")


def test_the_run_command_dry_run_and_one_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = CliRunner()
    dry = runner.invoke(main, ["run", "daily", "--dry-run"])
    assert dry.exit_code == 0 and "stage(s)" in dry.output

    seen: list[str] = []
    monkeypatch.setattr(
        "baseballpy.cli_queue.child_stage_runner",
        lambda plan, extra, stop: lambda name: seen.append(name) or EXIT_OK,
    )
    result = runner.invoke(main, ["run", "daily"])
    assert result.exit_code == 0, result.output
    assert len(seen) == 3 and "1 round(s)" in result.output
    release_all()


def test_status_shows_the_queue(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from baseballpy.cli_status import queue_overview
    from baseballpy.core.config import LakeConfig

    config = LakeConfig(home=tmp_path)
    assert queue_overview(config) is None
    run_queue(
        "daily",
        ["a", "b"],
        lambda name: EXIT_OK if name == "a" else EXIT_FAILED,
        retries=0,
        **_fast(tmp_path, state_path=config.state_root / "queue.json"),
    )
    overview = queue_overview(config)
    assert overview is not None and not overview.running
    assert overview.done == ["a"] and list(overview.failed) == ["b"]
    assert "plan daily, round 1, not running; 1 stage(s) done; failed: b" in overview.line()


def test_a_finished_stage_is_compacted_and_a_compact_failure_does_not_fail_it(
    tmp_path: Path,
) -> None:
    after: list[str] = []

    def compact(name: str) -> int:
        after.append(name)
        return EXIT_FAILED if name == "b" else EXIT_OK

    report = run_queue(
        "p",
        ["a", "b"],
        lambda _n: EXIT_OK,
        after_stage=compact,
        **_fast(tmp_path),
    )
    assert after == ["a", "b"] and report.exit_code == 0
    state = load_state(tmp_path / "state" / "queue.json", "p")
    assert state.stages["b"].status == "done" and "after-stage" in state.stages["b"].last_error


def test_the_compact_runner_runs_compact_for_every_source_of_the_stage() -> None:
    from baseballpy.ingest.queue import child_compact_runner

    _Child.instances = []
    run = child_compact_runner(
        lambda _name: ["mlb_api", "statcast"],
        threading.Event(),
        popen=lambda cmd: _Child(cmd, 0),
    )
    assert run("x") == 0
    assert [c.command[3:] for c in _Child.instances] == [
        ["compact", "--no-migrate", "--source", "mlb_api"],
        ["compact", "--no-migrate", "--source", "statcast"],
    ]


def test_a_finished_stage_is_on_disk_before_its_compaction_runs(tmp_path: Path) -> None:
    """A crash during the compaction must not forget that the stage is done."""
    seen: list[str] = []
    path = tmp_path / "state" / "queue.json"

    def compact(name: str) -> int:
        seen.append(load_state(path, "p").stages[name].status)
        return EXIT_OK

    run_queue("p", ["a"], lambda _n: EXIT_OK, after_stage=compact, **_fast(tmp_path))
    assert seen == ["done"]


def test_the_speed_watch_prints_each_interval_and_stops_with_the_queue(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from baseballpy import cli_queue

    class _Report:
        def line(self) -> str:
            return "speed: test line"

    seen: list[float] = []

    def fake_measure(path: Path, seconds: float) -> _Report:
        seen.append(seconds)
        return _Report()

    monkeypatch.setattr(cli_queue, "measure", fake_measure)
    monkeypatch.setattr(cli_queue, "default_audit_path", lambda: Path("audit.jsonl"))
    stop = threading.Event()
    assert cli_queue._start_speed_watch("0", stop) is None  # turned off
    watch = cli_queue._start_speed_watch("1s", stop)
    assert watch is not None
    deadline = 50
    while not seen and deadline:
        stop.wait(0.1)
        deadline -= 1
    stop.set()
    watch.join(timeout=5)
    assert not watch.is_alive() and seen and seen[0] == 1.0
    assert "speed: test line" in capsys.readouterr().out
