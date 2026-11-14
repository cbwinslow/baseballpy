"""The manifest lock is an operating-system lock: no stale lock to break (ADR 131).

The old lock file was broken after 60 s by stat then unlink, so two processes could both believe
they held it. These tests use real processes.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from baseballpy.core import atomic
from baseballpy.core.atomic import ManifestTracker, _FileLock

#: takes the manifest lock, says so, waits for a line, then ends with no clean-up (or cleanly)
_HOLD = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from baseballpy.core import atomic\n"
    "atomic.LOCK_STALE_SECONDS = 1.0\n"
    "with atomic._FileLock(Path(sys.argv[1])):\n"
    "    print('held', flush=True)\n"
    "    sys.stdin.readline()\n"
    "    if sys.argv[2] == 'crash':\n"
    "        os._exit(1)\n"
)

#: saves 15 chunk keys of its own into one manifest
_SAVER = (
    "import sys\n"
    "from baseballpy.core.atomic import ManifestTracker\n"
    "tracker = ManifestTracker(sys.argv[1])\n"
    "for i in range(15):\n"
    "    tracker.set_completed(sys.argv[2] + '-' + str(i), records_count=i)\n"
)


def _hold(lock: Path, how: str) -> "subprocess.Popen[str]":
    process = subprocess.Popen(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", _HOLD, str(lock), how],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "held"
    return process


def _let_go(process: "subprocess.Popen[str]") -> None:
    assert process.stdin is not None
    process.stdin.write("\n")
    process.stdin.flush()
    process.wait(timeout=30)


def test_a_process_killed_holding_the_lock_does_not_block_the_next(tmp_path: Path) -> None:
    lock = tmp_path / "_manifest.json.lock"
    _let_go(_hold(lock, "crash"))  # ends abruptly with the lock file still on disk
    assert lock.exists()
    start = time.monotonic()
    with _FileLock(lock, timeout=5):
        pass
    assert time.monotonic() - start < 3


def test_a_lock_held_longer_than_the_old_stale_limit_is_not_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = tmp_path / "_manifest.json.lock"
    monkeypatch.setattr(atomic, "LOCK_STALE_SECONDS", 1.0, raising=False)
    holder = _hold(lock, "clean")
    entered = threading.Event()
    errors: list[BaseException] = []

    def other() -> None:
        try:
            with _FileLock(lock, timeout=20):
                entered.set()
        except BaseException as exc:  # noqa: BLE001 - reported by the assertion below
            errors.append(exc)

    waiter = threading.Thread(target=other)
    waiter.start()
    time.sleep(2.5)  # more than twice the old stale limit
    assert not entered.is_set(), "the held lock was broken from under its holder"
    with pytest.raises(TimeoutError, match="could not acquire manifest lock"):
        _FileLock(lock, timeout=0.3).__enter__()  # the message of the old lock is kept
    _let_go(holder)
    waiter.join(timeout=20)
    assert not errors
    assert entered.is_set()


def test_threads_and_processes_saving_different_chunks_lose_no_entry(tmp_path: Path) -> None:
    path = tmp_path / "_manifest.json"
    ManifestTracker(path).set_completed("seed", records_count=1)
    processes = [
        subprocess.Popen([sys.executable, "-c", _SAVER, str(path), f"proc{n}"])  # noqa: S603
        for n in range(2)
    ]

    def work(n: int) -> None:
        tracker = ManifestTracker(path)  # one tracker per thread: only the file lock excludes
        for i in range(15):
            tracker.set_completed(f"thread{n}-{i}", records_count=i)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    for process in processes:
        assert process.wait(timeout=60) == 0
    keys = ManifestTracker(path).chunk_keys()
    expected = {"seed"}
    expected |= {f"thread{n}-{i}" for n in range(4) for i in range(15)}
    expected |= {f"proc{n}-{i}" for n in range(2) for i in range(15)}
    assert keys == expected
