"""The memory governor: concurrency follows live, measured memory, never a fixed number (change memory-governor).

Written first. The interface these tests fix (``baseballpy.core.memguard``):

* ``MemorySnapshot(total, available)``: ``available`` is what can still be allocated, the smaller of free RAM and the
  operating system's commit headroom (Windows stops with "paging file too small" while RAM is still free).
* ``MemoryGovernor(snapshot=..., private=..., reserve_fraction=0.15, floor=2 GiB, safety=1.5)`` with injectable probes:
  ``observe(running)`` samples the process; ``note_started()`` is called when a job starts; ``may_start(running)`` says
  whether one more job may start (the first job always may); ``per_job_bytes()`` is the largest growth per running job
  seen so far; ``workers_for(requested, cpus)`` bounds a process pool by the memory left; ``status()`` is a sentence.
* The reserve is ``max(floor, reserve_fraction * total)``: a share of this machine, not a constant.
* ``run_jobs`` starts jobs through the governor, so a job is held back (and the hold is audit-logged) while the
  measured memory of the running jobs leaves no room for another.
"""

import threading
import time
from collections.abc import Callable

import pytest

from baseballpy.core.memguard import MemoryGovernor, MemorySnapshot

GIB = 1 << 30


class Machine:
    """A fake machine: total RAM, free memory and the memory this process holds, all settable."""

    def __init__(
        self, total_gib: float = 96, available_gib: float = 60, private_gib: float = 1
    ) -> None:
        self.total = int(total_gib * GIB)
        self.available = int(available_gib * GIB)
        self.private = int(private_gib * GIB)

    def snapshot(self) -> MemorySnapshot:
        return MemorySnapshot(self.total, self.available)

    def rss(self) -> int:
        return self.private


def _governor(machine: Machine) -> MemoryGovernor:
    return MemoryGovernor(snapshot=machine.snapshot, private=machine.rss)


def test_the_first_job_always_starts_even_when_memory_is_scarce() -> None:
    machine = Machine(available_gib=0.5)
    assert _governor(machine).may_start(0) is True, "no job could ever run otherwise"


def test_a_second_job_waits_until_the_first_has_been_measured_and_has_settled() -> None:
    machine = Machine(available_gib=80)
    gov = _governor(machine)
    gov.note_started()
    assert gov.may_start(1) is False, "nothing is known about the size of a job yet"
    machine.private = 4 * GIB
    gov.observe(1)
    assert gov.may_start(1) is False, "the first job is still growing: one sample is not settled"
    gov.observe(1)
    assert gov.per_job_bytes() == 3 * GIB
    assert gov.may_start(1) is True, "80 GB free, 3 GB per job, a 14.4 GB reserve"


def test_admission_follows_the_measured_growth_and_the_live_free_memory() -> None:
    machine = Machine(total_gib=96, available_gib=20, private_gib=1)
    gov = _governor(machine)
    gov.note_started()
    machine.private = 4 * GIB  # one job grew the process by 3 GB
    gov.observe(1)
    gov.observe(1)
    # reserve 14.4 GB, one more job needs 3 GB x 1.5 = 4.5 GB: 20 - 14.4 = 5.6 GB is enough
    assert gov.may_start(1) is True
    machine.available = int(18 * GIB)  # the machine got busier: 18 - 14.4 = 3.6 GB is not
    assert gov.may_start(1) is False
    machine.available = int(30 * GIB)  # memory came back: more jobs may start again
    assert gov.may_start(1) is True


def test_the_reserve_is_a_share_of_the_machine() -> None:
    small = Machine(total_gib=8, available_gib=4, private_gib=0.5)
    big = Machine(total_gib=96, available_gib=20, private_gib=0.5)
    for machine, expected_reserve in ((small, 2 * GIB), (big, int(0.15 * 96 * GIB))):
        gov = _governor(machine)
        assert gov.reserve_bytes() == expected_reserve


def test_the_operating_system_commit_headroom_counts_as_memory() -> None:
    """Windows reported 'paging file too small' with RAM free: available is the smaller of the two."""
    snap = MemorySnapshot.of(total=96 * GIB, free_ram=60 * GIB, commit_headroom=3 * GIB)
    assert snap.available == 3 * GIB and snap.total == 96 * GIB


def test_a_process_pool_is_sized_by_the_memory_left_and_the_cpus() -> None:
    machine = Machine(total_gib=96, available_gib=40, private_gib=0.4)
    gov = _governor(machine)
    # per worker: this process after its imports is about 0.4 GB; reserve 14.4 GB; 25.6 GB / 0.4 GB = 64 workers
    assert gov.workers_for(requested=32, cpus=32) == 32
    assert gov.workers_for(requested=32, cpus=8) == 8, "never more than the CPUs"
    machine.available = int(15 * GIB)  # only 0.6 GB above the reserve
    assert gov.workers_for(requested=32, cpus=32) == 1, "one worker always, never zero"
    machine.available = int(16 * GIB)  # 1.6 GB above the reserve: 4 workers
    assert gov.workers_for(requested=32, cpus=32) == 4


def test_the_status_sentence_names_the_numbers() -> None:
    machine = Machine(total_gib=96, available_gib=41, private_gib=1)
    text = _governor(machine).status()
    assert "41" in text and "96" in text and "reserve" in text


def _run(jobs: int, machine: Machine, work: Callable[[], None]) -> int:
    """Run ``jobs`` jobs through the real runner with the fake machine; return the most that ran at once."""
    from baseballpy.ingest.runner import _run_pool
    from baseballpy.ingest.types import Job, JobResult, JobStatus, make_job

    planned = [make_job("fake", "season", season=i) for i in range(jobs)]
    gov = _governor(machine)
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def run_single(job: Job, blocked: str | None) -> JobResult:
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
            machine.private += GIB  # each running job holds 1 GB
            machine.available -= GIB
        work()
        with lock:
            state["now"] -= 1
            machine.private -= GIB
            machine.available += GIB
        return JobResult(job=job, status=JobStatus.COMPLETED, rows=0, seconds=0.0)

    results: list[JobResult | None] = [None] * jobs
    _run_pool(planned, run_single, 16, results, [[] for _ in planned], governor=gov)
    assert all(r is not None and r.status == JobStatus.COMPLETED for r in results)
    return state["peak"]


def test_the_runner_runs_jobs_side_by_side_when_memory_is_plentiful() -> None:
    peak = _run(6, Machine(total_gib=96, available_gib=90, private_gib=1), lambda: time.sleep(3.0))
    assert peak >= 3, f"only {peak} jobs ran at once with 90 GB free"


def test_the_runner_holds_jobs_back_when_memory_is_scarce_and_still_finishes() -> None:
    peak = _run(5, Machine(total_gib=96, available_gib=17, private_gib=1), lambda: time.sleep(0.4))
    assert peak <= 2, (
        f"{peak} jobs ran at once with only 17 GB free (14.4 GB reserve, 1 GB per job)"
    )


@pytest.mark.parametrize("running", [0, 1, 5])
def test_may_start_never_blocks_forever_when_nothing_runs(running: int) -> None:
    machine = Machine(available_gib=0.1)
    assert _governor(machine).may_start(0) is True
    del running


def test_a_worker_exits_when_its_parent_is_gone() -> None:
    """Orphaned spawn workers held 27 GB of commit after a crashed run: a worker must leave with its parent."""
    from baseballpy.core.memguard import watch_parent

    alive = {"parent": True}
    left: list[int] = []
    ticks = {"n": 0}

    def sleep(_seconds: float) -> None:
        ticks["n"] += 1
        if ticks["n"] == 3:
            alive["parent"] = False

    watch_parent(
        4242, alive=lambda pid: alive["parent"], on_orphan=lambda: left.append(1), sleep=sleep
    )
    assert left == [1] and ticks["n"] == 3, (
        "the watcher checks on every pass and acts once the parent is gone"
    )


def test_this_process_is_alive_and_a_dead_pid_is_not() -> None:
    import os

    from baseballpy.core.memguard import pid_alive

    assert pid_alive(os.getpid()) is True
    assert pid_alive(2_000_000_000) is False


def test_a_shared_pool_is_sized_once_from_the_memory_left() -> None:
    from baseballpy.sources.retrosheet import pool

    machine = Machine(total_gib=96, available_gib=16, private_gib=0.4)
    pool._sizes.clear()
    assert pool.pool_size(32, _governor(machine)) == 4, (
        "1.6 GB above the reserve, 0.4 GB per worker"
    )
    machine.available = int(80 * GIB)
    assert pool.pool_size(32, _governor(machine)) == 4, (
        "decided once: the pool keeps its size for the run"
    )
    pool._sizes.clear()
