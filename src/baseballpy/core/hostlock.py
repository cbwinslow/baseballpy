"""One baseballpy process per remote host: the rate and in-flight caps are per process.

``HttpClient`` keeps the caps of a host for its own process, so two programs downloading from the
same host at once would send twice the allowed rate (a real run did: two Kalshi jobs, HTTP 429).
A process therefore claims a host with an operating-system file lock the first time it asks it
something; a second process that asks the same host is refused with a clear message. The lock is
released when the process ends, however it ends, so a crash never leaves a stale claim.
"""

import os
import re
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

#: claims held by this process: (lock folder, host) -> open file descriptor
_HELD: dict[tuple[str, str], int] = {}
_SCOPED: dict[
    tuple[str, str], int
] = {}  # key -> how many ``held_named`` blocks of this process use the lock
_LOCK = threading.Lock()
_SAFE = re.compile(r"[^A-Za-z0-9.-]+")


class HostBusyError(RuntimeError):
    """Another baseballpy process is already downloading from this host."""


def _try_lock(fd: int) -> bool:
    """Take an exclusive, non-blocking OS lock on the file; False when someone else holds it."""
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    """Drop the OS lock taken by :func:`_try_lock` before the descriptor is closed.

    Closing a descriptor with a byte-range lock on Windows leaves the release to the operating system
    ("eventually"), so a process that gave a host up and asked for it again could be told it is busy.
    """
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass  # the descriptor is closed next, which releases the lock in any case


def wait_file_lock(path: Path, timeout: float) -> int:
    """Take the exclusive OS lock of ``path`` (made if missing), WAITING up to ``timeout`` seconds.

    Unlike the claims above, which refuse at once, this is for short critical sections that many
    threads and processes queue for (a manifest save). Every call opens its own descriptor, so threads
    of one process exclude each other too. Returns the descriptor for :func:`release_file_lock`;
    raises ``TimeoutError`` when the lock stays taken. The operating system frees the lock when its
    holder ends, however it ends, so there is no stale lock and nothing to break; the file stays.
    """
    deadline = time.monotonic() + timeout
    while True:
        fd = os.open(path, os.O_CREAT | os.O_RDWR)
        try:
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")  # Windows locks a byte range, so the file needs a byte to lock
            if _try_lock(fd):
                return fd
        except PermissionError:
            pass  # Windows: the holder has the byte locked while we tried to write it: still busy
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)
        if time.monotonic() >= deadline:
            raise TimeoutError(f"could not acquire file lock {path}")
        time.sleep(0.01)


def release_file_lock(fd: int) -> None:
    """Give back a lock taken by :func:`wait_file_lock` and close its descriptor."""
    _unlock(fd)
    os.close(fd)


def claim_named(directory: Path, name: str, busy_message: str) -> bool:
    """Claim ``name`` for this process (idempotent); raises :class:`HostBusyError` if taken.

    Returns True when this call took the lock and False when the process already held it, so a caller
    that only borrowed the lock can leave it to its owner (release only what you claimed).

    The same operating-system lock serves hosts and the download queue (one supervisor per home).
    """
    key = (str(directory), name)
    with _LOCK:
        if key in _SCOPED:
            raise RuntimeError(
                f"lock {name!r} is held by a held_named block of this process: claim_named cannot take it over "
                "(use one family of calls per lock name)"
            )
        if key in _HELD:
            return False
        _claim_locked(directory, name, busy_message)
        return True


def _claim_locked(directory: Path, name: str, busy_message: str) -> None:
    """Take the OS lock and remember it (the caller holds ``_LOCK`` and knows this process lacks the lock)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_SAFE.sub('_', name)}.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")  # Windows locks a byte range, so the file needs a byte to lock
    except (
        PermissionError
    ):  # Windows: another process locked that byte between our check and our write
        os.close(fd)
        raise HostBusyError(busy_message) from None
    if not _try_lock(fd):
        os.close(fd)
        raise HostBusyError(busy_message)
    _HELD[(str(directory), name)] = fd


def _drop_locked(key: tuple[str, str]) -> None:
    """Give a lock of this process back (the caller holds ``_LOCK``)."""
    fd = _HELD.pop(key, None)
    if fd is not None:
        _unlock(fd)
        os.close(fd)


def claim_host(directory: Path, host: str) -> None:
    """Claim ``host`` for this process (idempotent); raises :class:`HostBusyError` if taken."""
    claim_named(
        directory,
        host,
        f"another baseballpy process is already downloading from {host}: its speed caps "
        "are per process, so a second one would double the request rate. Wait for it to "
        "finish, or set BASEBALLPY_RATE_ALLOW_PARALLEL_PROCESSES=1 if you know the host "
        "allows it.",
    )


@contextmanager
def held_named(directory: Path, name: str, busy_message: str) -> Iterator[None]:
    """Hold ``name`` for the length of the ``with`` block; ``HostBusyError`` at once when another process has it.

    Blocks of one process may overlap (threads writing the same dataset and season): the lock is taken by the
    first one and given back by the last. A lock the process already holds for good (``claim_named``) is only
    borrowed and stays held afterwards. Nothing stays open once the block ends, so a process that writes many
    datasets does not collect open files.
    """
    key = (str(directory), name)
    with _LOCK:
        count = _SCOPED.get(key, 0)
        if count == 0 and key in _HELD:
            borrowed = True  # held for good by a claim_named of this process
        else:
            borrowed = False
            if count == 0:
                _claim_locked(directory, name, busy_message)
            _SCOPED[key] = count + 1
    try:
        yield
    finally:
        if not borrowed:
            with _LOCK:
                left = _SCOPED[key] - 1
                if left:
                    _SCOPED[key] = left
                else:
                    del _SCOPED[key]
                    _drop_locked(key)


def release_named(directory: Path, name: str) -> None:
    """Give up this process's claim on ``name`` (nothing happens when it holds no such claim)."""
    with _LOCK:
        key = (str(directory), name)
        if key in _SCOPED:
            return  # owned by a held_named block, which gives it back itself
        fd = _HELD.pop(key, None)
        if fd is not None:
            _unlock(fd)
            os.close(fd)


def release_all(directory: Path | None = None) -> None:
    """Give up this process's claims (all of them, or those under one lock folder)."""
    with _LOCK:
        for key in [
            k for k in _HELD if k not in _SCOPED and (directory is None or k[0] == str(directory))
        ]:  # a lock of a running held_named block is not ours to give up (HttpClient.close calls this)
            fd = _HELD.pop(key)
            _unlock(fd)
            os.close(fd)


def busy_hosts(directory: Path) -> list[str]:
    """Hosts some process is downloading from right now (their lock cannot be taken).

    Each lock is tried and, when it was free, dropped again at once, so looking changes nothing.
    """
    busy: list[str] = []
    if not directory.is_dir():
        return busy
    for path in sorted(directory.glob("*.lock")):
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            continue
        try:
            if _try_lock(fd):
                _unlock(fd)  # we only looked: give the lock back at once
            else:
                busy.append(path.name.removesuffix(".lock"))
        finally:
            os.close(fd)
    return busy


__all__ = [
    "HostBusyError",
    "busy_hosts",
    "claim_host",
    "claim_named",
    "release_all",
    "release_file_lock",
    "release_named",
    "wait_file_lock",
]
