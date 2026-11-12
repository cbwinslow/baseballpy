"""Memory-aware scheduling: how many jobs and worker processes may run, decided from live, measured memory.

A fixed worker count (the CPU count) assumed that every job is light. A Statcast pitch season holds hundreds of
thousands of rows in memory, so 25 of them at once froze a 96 GB machine, and on Windows the operating system stopped
processes with "paging file too small" while RAM was still free (the commit limit, not the RAM, ran out).

The :class:`MemoryGovernor` never uses a fixed number of jobs:

* what it can still use is ``available``: the smaller of the free RAM and the operating system's commit headroom;
* it keeps a reserve that is a share of this machine (``max(2 GiB, 15 %)`` of its RAM);
* it measures how much one running job grows this process (``per_job_bytes``, the largest growth per running job seen)
  and starts another job only when the free memory above the reserve covers that measured growth with a safety factor;
* after starting a job it waits until the memory of the process has stopped growing, so a job that is still loading
  is not mistaken for a small one;
* the first job always starts, so something always makes progress.

The probes are injectable, so tests use a fake machine. No dependency: Windows uses ``ctypes``, Linux ``/proc``,
macOS ``sysconf``.
"""

import ctypes
import os
import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

GIB = 1 << 30
#: seconds after which a job that keeps growing is no longer waited for before the next one is considered
SETTLE_TIMEOUT = 20.0
#: two samples closer than this share of each other count as "stopped growing"
SETTLE_TOLERANCE = 0.03
#: a job that has grown this process by less than this is light: nothing to wait for before the next one
LIGHT_JOB_BYTES = 64 << 20


@dataclass(frozen=True)
class MemorySnapshot:
    """What the machine has: ``total`` RAM and ``available``, what can still be allocated."""

    total: int
    available: int

    @classmethod
    def of(
        cls, *, total: int, free_ram: int, commit_headroom: int | None = None
    ) -> "MemorySnapshot":
        """Available is the smaller of free RAM and the commit headroom (when the system reports one)."""
        available = free_ram if commit_headroom is None else min(free_ram, commit_headroom)
        return cls(total=total, available=max(0, available))


def _windows_status() -> MemorySnapshot:
    class Status(ctypes.Structure):  # MEMORYSTATUSEX
        _fields_ = [
            ("dwLength", ctypes.c_uint32),
            ("dwMemoryLoad", ctypes.c_uint32),
            ("ullTotalPhys", ctypes.c_uint64),
            ("ullAvailPhys", ctypes.c_uint64),
            ("ullTotalPageFile", ctypes.c_uint64),
            ("ullAvailPageFile", ctypes.c_uint64),
            ("ullTotalVirtual", ctypes.c_uint64),
            ("ullAvailVirtual", ctypes.c_uint64),
            ("ullAvailExtendedVirtual", ctypes.c_uint64),
        ]

    status = Status()
    status.dwLength = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return MemorySnapshot.of(
        total=int(status.ullTotalPhys),
        free_ram=int(status.ullAvailPhys),
        commit_headroom=int(status.ullAvailPageFile),
    )


def _linux_status() -> MemorySnapshot:
    values: dict[str, int] = {}
    with open("/proc/meminfo", encoding="ascii") as handle:
        for line in handle:
            key, _, rest = line.partition(":")
            values[key] = int(rest.split()[0]) * 1024
    return MemorySnapshot.of(
        total=values["MemTotal"], free_ram=values.get("MemAvailable", values["MemFree"])
    )


def _sysconf(name: str) -> int:
    """``os.sysconf`` (absent on Windows, where it is never called)."""
    return int(getattr(os, "sysconf")(name))  # noqa: B009 - the attribute does not exist on every platform


def _posix_status() -> MemorySnapshot:
    page = _sysconf("SC_PAGE_SIZE")
    return MemorySnapshot.of(
        total=int(_sysconf("SC_PHYS_PAGES")) * page,
        free_ram=int(_sysconf("SC_AVPHYS_PAGES")) * page,
    )


def system_memory() -> MemorySnapshot:
    """The machine's memory now (a probe that cannot read it reports plenty, so scheduling never stops)."""
    try:
        if sys.platform == "win32":
            return _windows_status()
        if sys.platform.startswith("linux"):
            return _linux_status()
        return _posix_status()
    except (OSError, ValueError, KeyError, AttributeError):
        return MemorySnapshot(total=64 * GIB, available=64 * GIB)


def process_private_bytes() -> int:
    """The memory this process holds now (private bytes on Windows, resident set elsewhere); 0 when unknown."""
    try:
        if sys.platform == "win32":

            class Counters(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS_EX
                _fields_ = [
                    ("cb", ctypes.c_uint32),
                    ("PageFaultCount", ctypes.c_uint32),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(Counters)
            kernel = ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            handle = kernel.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb
            )
            return int(counters.PrivateUsage) if ok else 0
        with open("/proc/self/statm", encoding="ascii") as handle_:
            return int(handle_.read().split()[1]) * _sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError, AttributeError):
        return 0


class MemoryGovernor:
    """Decides, from live and measured memory, whether one more job (or how many workers) may start."""

    def __init__(
        self,
        snapshot: Callable[[], MemorySnapshot] = system_memory,
        private: Callable[[], int] = process_private_bytes,
        *,
        reserve_fraction: float = 0.15,
        floor: int = 2 * GIB,
        safety: float = 1.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._snapshot = snapshot
        self._private = private
        self._reserve_fraction = reserve_fraction
        self._floor = floor
        self._safety = safety
        self._clock = clock
        self._baseline = private()
        self._per_job = 0
        self._samples: deque[int] = deque(maxlen=3)
        self._started_at: float | None = None
        self._start_rss = self._baseline
        self._held = False

    # ----------------------------------------------------------------- measuring
    def reserve_bytes(self) -> int:
        """Memory kept free for the operating system and everything else: a share of this machine."""
        return max(self._floor, int(self._reserve_fraction * self._snapshot().total))

    def per_job_bytes(self) -> int | None:
        """The largest growth of this process per running job seen so far (``None`` before any was measured)."""
        return self._per_job or None

    def note_started(self) -> None:
        """Call when a job starts: the next job waits until the memory of this process has settled."""
        self._started_at = self._clock()
        self._start_rss = self._private()
        self._samples.clear()

    def observe(self, running: int) -> None:
        """Sample the process while ``running`` jobs run (call it on every scheduling pass)."""
        if running < 1:
            return
        rss = self._private()
        self._samples.append(rss)
        growth = max(0, rss - self._baseline) // running
        self._per_job = max(self._per_job, growth)

    def _settled(self) -> bool:
        if self._started_at is None:
            return True
        if self._clock() - self._started_at >= SETTLE_TIMEOUT:
            return True
        if not self._samples:
            return False
        if self._samples[-1] - self._start_rss < LIGHT_JOB_BYTES:
            return True  # a light job (HTTP and small files): there is nothing to wait for
        if len(self._samples) < 2:
            return False
        a, b = self._samples[-2], self._samples[-1]
        return abs(b - a) <= SETTLE_TOLERANCE * max(a, b, 1)

    # ----------------------------------------------------------------- deciding
    def may_start(self, running: int) -> bool:
        """Whether one more job may start now (the first job always may)."""
        if running < 1:
            return True
        if self._baseline == 0 and self._private() == 0:
            return True  # the memory of this process cannot be read here: nothing to measure, nothing to hold
        if not self._settled():
            self._held = True
            return False
        room = self._snapshot().available - self.reserve_bytes()
        ok = room >= int(self._per_job * self._safety)
        self._held = not ok
        return ok

    @property
    def holding(self) -> bool:
        """True when the last :meth:`may_start` said no (a job is being held back for memory)."""
        return self._held

    def workers_for(self, requested: int, cpus: int | None = None) -> int:
        """Worker processes a pool may start: bounded by the request, the CPUs and the memory above the reserve.

        One worker costs about what this process holds after its imports (a spawned worker imports the same modules).
        There is always at least one.
        """
        cap = min(max(1, requested), max(1, cpus if cpus is not None else (os.cpu_count() or 1)))
        per_worker = max(self._baseline, self._private(), 64 << 20)
        room = self._snapshot().available - self.reserve_bytes()
        return max(1, min(cap, int(room // per_worker)))

    def status(self) -> str:
        """One sentence for the console and the log."""
        snap = self._snapshot()
        per_job = self.per_job_bytes()
        job = f"{per_job / GIB:.1f} GB per job measured" if per_job else "job size not measured yet"
        return (
            f"memory: {snap.available / GIB:.0f} GB usable of {snap.total / GIB:.0f} GB, "
            f"reserve {self.reserve_bytes() / GIB:.0f} GB, {job}; jobs are started only while they fit"
        )


def pid_alive(pid: int) -> bool:
    """Whether the process ``pid`` exists (never signals or ends it)."""
    if sys.platform == "win32":
        kernel = ctypes.windll.kernel32
        kernel.OpenProcess.restype = ctypes.c_void_p
        synchronize = 0x00100000
        handle = kernel.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        try:
            return (
                int(kernel.WaitForSingleObject(ctypes.c_void_p(handle), 0)) == 0x102
            )  # WAIT_TIMEOUT: still running
        finally:
            kernel.CloseHandle(ctypes.c_void_p(handle))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def watch_parent(
    parent_pid: int,
    *,
    interval: float = 2.0,
    alive: Callable[[int], bool] = pid_alive,
    on_orphan: Callable[[], None] = lambda: os._exit(1),
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Block until ``parent_pid`` is gone, then call ``on_orphan`` (a worker process runs this on a thread)."""
    while True:
        sleep(interval)
        if not alive(parent_pid):
            on_orphan()
            return


__all__ = [
    "GIB",
    "MemoryGovernor",
    "MemorySnapshot",
    "pid_alive",
    "process_private_bytes",
    "system_memory",
    "watch_parent",
]
