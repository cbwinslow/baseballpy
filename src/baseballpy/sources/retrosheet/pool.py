"""CPU-bound Retrosheet parsing, one file at a time, optionally in one shared process pool.

Workers return one Arrow table per file so callers can stream them into Parquet row groups instead
of accumulating whole-season Python lists. All streams of a run share one persistent pool (starting
and stopping a pool per build step cost more than the parsing at 32 workers, ADR 61), and a stream
keeps at most twice the worker count of files in flight.
"""

import atexit
import concurrent.futures
import threading
from collections import deque
from collections.abc import Iterator, Sequence
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pyarrow as pa

from baseballpy.sources.retrosheet.parser import (
    RetrosheetBoxScoreParser,
    RetrosheetDailySplitsParser,
    RetrosheetEventParser,
    RetrosheetFlatParser,
    RetrosheetGameLogParser,
    RetrosheetRosterParser,
    RetrosheetSubstitutionsParser,
)

#: parse kinds understood by :func:`parse_one`; "boxscores" yields (batting, pitching) pairs
KINDS = (
    "events",
    "boxscores",
    "daily_splits",
    "substitutions",
    "rosters",
    "gamelogs",
    "flat:<dataset>",
)

#: files a stream keeps in flight, per worker
WINDOW_PER_WORKER = 2

_pools: dict[int, concurrent.futures.ProcessPoolExecutor] = {}
_pools_lock = threading.Lock()


def parse_one(kind: str, path: str, year: int | None) -> pa.Table | tuple[pa.Table, pa.Table]:
    """Parse one file; module-level so it can run in a worker process."""
    file = Path(path)
    if kind == "events":
        return RetrosheetEventParser().parse_files([file], year=year)
    if kind == "boxscores":
        return RetrosheetBoxScoreParser().parse_files([file], year=year)
    if kind == "daily_splits":
        return RetrosheetDailySplitsParser().parse_files([file], year=year)
    if kind == "substitutions":
        return RetrosheetSubstitutionsParser().parse_files([file], year=year)
    if kind == "rosters":
        return RetrosheetRosterParser().parse_files([file], year=year)
    if kind == "gamelogs":
        return RetrosheetGameLogParser().parse_file(file)
    if kind.startswith("flat:"):
        return RetrosheetFlatParser().parse_path(kind.removeprefix("flat:"), file)
    raise ValueError(f"unknown parse kind {kind!r}")


def shared_pool(workers: int) -> concurrent.futures.ProcessPoolExecutor:
    """The persistent process pool of ``workers`` processes (started on first use)."""
    with _pools_lock:
        pool = _pools.get(workers)
        if pool is None:
            pool = concurrent.futures.ProcessPoolExecutor(max_workers=workers)
            _pools[workers] = pool
        return pool


def _discard_pool(workers: int, pool: concurrent.futures.ProcessPoolExecutor) -> None:
    """Forget a pool that lost a worker process so the next stream starts a fresh one."""
    with _pools_lock:
        if _pools.get(workers) is pool:
            del _pools[workers]
    pool.shutdown(wait=False, cancel_futures=True)


def shutdown_pools() -> None:
    """Stop every shared pool (registered at exit; tests call it to start clean)."""
    with _pools_lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        pool.shutdown(wait=True, cancel_futures=True)


atexit.register(shutdown_pools)


def parse_stream(
    kind: str, paths: Sequence[Path], year: int | None, workers: int = 0
) -> Iterator[pa.Table | tuple[pa.Table, pa.Table]]:
    """Yield one parsed table per file, in input order.

    ``workers <= 1`` (or a single file) parses in-process; otherwise the files go to the shared
    process pool, at most ``WINDOW_PER_WORKER`` x ``workers`` ahead of the consumer. A failing
    file raises and the stream's queued files are cancelled.
    """
    if workers <= 1 or len(paths) <= 1:
        for path in paths:
            yield parse_one(kind, str(path), year)
        return
    pool = shared_pool(workers)
    window = WINDOW_PER_WORKER * workers
    remaining = iter(paths)
    pending: deque[concurrent.futures.Future[pa.Table | tuple[pa.Table, pa.Table]]] = deque()

    def fill() -> None:
        while len(pending) < window:
            path = next(remaining, None)
            if path is None:
                return
            pending.append(pool.submit(parse_one, kind, str(path), year))

    try:
        fill()
        while pending:
            try:
                table = pending.popleft().result()
            except BrokenProcessPool:
                _discard_pool(workers, pool)
                raise
            yield table
            fill()
    finally:
        for future in pending:
            future.cancel()
