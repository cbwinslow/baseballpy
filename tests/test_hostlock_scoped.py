"""Direct tests for the scoped lock held_named in core/hostlock.py (ADR 124)."""

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from baseballpy.core.hostlock import (
    HostBusyError,
    claim_named,
    held_named,
    release_all,
    release_named,
)

#: claims a lock name, says so, then waits for a line and ends abruptly with no clean-up (a crash)
_HOLD = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from baseballpy.core.hostlock import claim_named\n"
    "claim_named(Path(sys.argv[1]), sys.argv[2], 'busy')\n"
    "print('held', flush=True)\n"
    "sys.stdin.readline()\n"
    "os._exit(1)\n"
)

#: attempts to claim a lock name in a subprocess and exits 0 on success, or raises HostBusyError
_CLAIM = (
    "import sys\n"
    "from pathlib import Path\n"
    "from baseballpy.core.hostlock import claim_named\n"
    "claim_named(Path(sys.argv[1]), sys.argv[2], 'busy')\n"
)


def _hold(directory: Path, name: str) -> "subprocess.Popen[str]":
    """Start a subprocess that claims ``name`` and holds it until stdin receives a newline."""
    process = subprocess.Popen(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", _HOLD, str(directory), name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        assert line == "held", f"expected 'held', got {line!r}"
    except Exception:
        process.kill()
        process.wait(timeout=10)
        raise
    return process


def _crash(process: "subprocess.Popen[str]") -> None:
    """End the holder abruptly and wait until it is gone."""
    try:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.write("\n")
            process.stdin.flush()
        process.wait(timeout=30)
    except Exception:
        process.kill()
        process.wait(timeout=10)
        raise


def _try_claim(directory: Path, name: str) -> "subprocess.CompletedProcess[str]":
    """Attempt to claim ``name`` in a separate process; returns CompletedProcess."""
    return subprocess.run(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", _CLAIM, str(directory), name],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_scoped_lock_held_inside_block_and_freed_afterwards(tmp_path: Path) -> None:
    """Inside the block the lock is held: a subprocess is refused; after the block it gets it."""
    try:
        with held_named(tmp_path, "res-1", "res-1 is busy"):
            res = _try_claim(tmp_path, "res-1")
            assert res.returncode != 0
            assert "HostBusyError" in res.stderr

        # After the block ends, the second process gets it
        holder = _hold(tmp_path, "res-1")
        _crash(holder)
    finally:
        release_all(tmp_path)


def test_nested_blocks_hold_lock_until_outer_block_exits(tmp_path: Path) -> None:
    """Nested blocks of one process: lock stays held until outer block ends, then is free."""
    try:
        with held_named(tmp_path, "nested-res", "nested-res is busy"):
            with held_named(tmp_path, "nested-res", "nested-res is busy"):
                res_inner = _try_claim(tmp_path, "nested-res")
                assert res_inner.returncode != 0
                assert "HostBusyError" in res_inner.stderr

            # Inner block has exited, outer block still active: subprocess must still be refused
            res_between = _try_claim(tmp_path, "nested-res")
            assert res_between.returncode != 0
            assert "HostBusyError" in res_between.stderr

        # Outer block has exited: lock is free
        holder = _hold(tmp_path, "nested-res")
        _crash(holder)
    finally:
        release_all(tmp_path)


def test_overlapping_threads_hold_lock_until_last_thread_exits(tmp_path: Path) -> None:
    """Two threads enter same lock name; first leaves before second; lock stays held until second leaves."""
    t1_in = threading.Event()
    t2_in = threading.Event()
    t1_can_exit = threading.Event()
    t1_out = threading.Event()
    t2_can_exit = threading.Event()
    t2_out = threading.Event()
    errors: list[BaseException] = []

    def worker_1() -> None:
        try:
            with held_named(tmp_path, "thread-res", "thread-res is busy"):
                t1_in.set()
                if not t1_can_exit.wait(timeout=10):
                    raise TimeoutError("timed out waiting for t1_can_exit")
        except BaseException as exc:
            errors.append(exc)
        finally:
            t1_out.set()

    def worker_2() -> None:
        try:
            with held_named(tmp_path, "thread-res", "thread-res is busy"):
                t2_in.set()
                if not t2_can_exit.wait(timeout=10):
                    raise TimeoutError("timed out waiting for t2_can_exit")
        except BaseException as exc:
            errors.append(exc)
        finally:
            t2_out.set()

    t1 = threading.Thread(target=worker_1, daemon=True)
    t2 = threading.Thread(target=worker_2, daemon=True)
    try:
        t1.start()
        assert t1_in.wait(timeout=10), "t1 failed to enter held_named"

        t2.start()
        assert t2_in.wait(timeout=10), "t2 failed to enter held_named"

        # Allow thread 1 to exit first
        t1_can_exit.set()
        assert t1_out.wait(timeout=10), "t1 failed to exit"
        t1.join(timeout=10)

        # Thread 1 has left, thread 2 is still inside: lock must still be held
        res = _try_claim(tmp_path, "thread-res")
        assert res.returncode != 0
        assert "HostBusyError" in res.stderr

        # Now allow thread 2 to exit
        t2_can_exit.set()
        assert t2_out.wait(timeout=10), "t2 failed to exit"
        t2.join(timeout=10)

        assert not errors, f"thread errors occurred: {errors}"

        # Both threads have exited: lock is free
        holder = _hold(tmp_path, "thread-res")
        _crash(holder)
    finally:
        t1_can_exit.set()
        t2_can_exit.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        release_all(tmp_path)


def test_borrowed_lock_stays_held_after_held_named_block(tmp_path: Path) -> None:
    """claim_named first, then held_named: after block, lock is still held; release_named frees it."""
    try:
        claimed = claim_named(tmp_path, "borrowed-res", "borrowed-res is busy")
        assert claimed is True

        with held_named(tmp_path, "borrowed-res", "borrowed-res is busy"):
            res_inside = _try_claim(tmp_path, "borrowed-res")
            assert res_inside.returncode != 0
            assert "HostBusyError" in res_inside.stderr

        # After the block, the lock is STILL held (a subprocess is still refused)
        res_after = _try_claim(tmp_path, "borrowed-res")
        assert res_after.returncode != 0
        assert "HostBusyError" in res_after.stderr

        # release_named then frees it
        release_named(tmp_path, "borrowed-res")

        # Now a subprocess gets it
        holder = _hold(tmp_path, "borrowed-res")
        _crash(holder)
    finally:
        release_all(tmp_path)


def test_refused_block_raises_host_busy_error_and_leaves_no_entry_behind(
    tmp_path: Path,
) -> None:
    """When a subprocess holds the lock, held_named raises HostBusyError and leaves no entry behind."""
    holder = _hold(tmp_path, "contested-res")
    try:
        with (
            pytest.raises(HostBusyError, match="contested-res is busy"),
            held_named(tmp_path, "contested-res", "contested-res is busy"),
        ):
            pytest.fail("held_named block must not be entered when lock is held")
    finally:
        _crash(holder)
        release_all(tmp_path)

    # Afterwards (subprocess gone), same name can be claimed normally in this process
    claimed = claim_named(tmp_path, "contested-res", "contested-res is busy")
    assert claimed is True
    release_all(tmp_path)

    # And held_named can also claim and release it cleanly
    with held_named(tmp_path, "contested-res", "contested-res is busy"):
        pass
    release_all(tmp_path)


def test_different_lock_names_are_independent(tmp_path: Path) -> None:
    """Different lock names are independent: one held does not block the other."""
    foreign_holder = _hold(tmp_path, "external-res")
    try:
        # external-res is held by subprocess, but name-a is independent and can be held here
        with held_named(tmp_path, "name-a", "name-a is busy"):
            res_a = _try_claim(tmp_path, "name-a")
            assert res_a.returncode != 0
            assert "HostBusyError" in res_a.stderr

            # name-b is independent of name-a and external-res; can also be held in this process
            with held_named(tmp_path, "name-b", "name-b is busy"):
                res_b = _try_claim(tmp_path, "name-b")
                assert res_b.returncode != 0
                assert "HostBusyError" in res_b.stderr

            # name-b has exited and is free for a subprocess even while name-a is still held
            holder_b = _hold(tmp_path, "name-b")
            _crash(holder_b)

            # name-a is still held
            res_a_still = _try_claim(tmp_path, "name-a")
            assert res_a_still.returncode != 0
            assert "HostBusyError" in res_a_still.stderr
    finally:
        _crash(foreign_holder)
        release_all(tmp_path)


def test_exception_inside_held_named_gives_lock_back(tmp_path: Path) -> None:
    """An exception inside the block still gives the lock back."""

    class CustomError(Exception):
        pass

    try:
        with (
            pytest.raises(CustomError, match="failure inside block"),
            held_named(tmp_path, "err-res", "err-res is busy"),
        ):
            raise CustomError("failure inside block")

        # After the exception, the lock must have been given back
        holder = _hold(tmp_path, "err-res")
        _crash(holder)
    finally:
        release_all(tmp_path)


def test_exception_in_inner_block_keeps_outer_lock_held_until_outer_exits(
    tmp_path: Path,
) -> None:
    """An exception in an inner block drops only inner scope; outer block keeps lock until it exits."""

    class InnerError(Exception):
        pass

    try:
        with held_named(tmp_path, "inner-err-res", "inner-err-res is busy"):
            with (
                pytest.raises(InnerError),
                held_named(tmp_path, "inner-err-res", "inner-err-res is busy"),
            ):
                raise InnerError("inner failure")

            # Inner block raised and exited, but outer block is still active
            res = _try_claim(tmp_path, "inner-err-res")
            assert res.returncode != 0
            assert "HostBusyError" in res.stderr

        # Outer block has exited; lock is free
        holder = _hold(tmp_path, "inner-err-res")
        _crash(holder)
    finally:
        release_all(tmp_path)
