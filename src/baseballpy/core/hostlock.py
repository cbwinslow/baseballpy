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
from pathlib import Path

#: claims held by this process: (lock folder, host) -> open file descriptor
_HELD: dict[tuple[str, str], int] = {}
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


def claim_named(directory: Path, name: str, busy_message: str) -> None:
    """Claim ``name`` for this process (idempotent); raises :class:`HostBusyError` if taken.

    The same operating-system lock serves hosts and the download queue (one supervisor per home).
    """
    key = (str(directory), name)
    with _LOCK:
        if key in _HELD:
            return
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{_SAFE.sub('_', name)}.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")  # Windows locks a byte range, so the file needs a byte to lock
        if not _try_lock(fd):
            os.close(fd)
            raise HostBusyError(busy_message)
        _HELD[key] = fd


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


def release_named(directory: Path, name: str) -> None:
    """Give up this process's claim on ``name`` (nothing happens when it holds no such claim)."""
    with _LOCK:
        fd = _HELD.pop((str(directory), name), None)
        if fd is not None:
            os.close(fd)  # closing the descriptor drops the OS lock


def release_all(directory: Path | None = None) -> None:
    """Give up this process's claims (all of them, or those under one lock folder)."""
    with _LOCK:
        for key in [k for k in _HELD if directory is None or k[0] == str(directory)]:
            os.close(_HELD.pop(key))  # closing the descriptor drops the OS lock


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
            if not _try_lock(fd):
                busy.append(path.name.removesuffix(".lock"))
        finally:
            os.close(fd)  # closing drops a lock we just took
    return busy


__all__ = [
    "HostBusyError",
    "busy_hosts",
    "claim_host",
    "claim_named",
    "release_all",
    "release_named",
]
