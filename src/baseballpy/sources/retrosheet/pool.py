"""CPU-bound Retrosheet parsing, one file at a time, optionally in a bounded process pool.

Workers return one Arrow table per file so callers can stream them into Parquet row groups instead
of accumulating whole-season Python lists.
"""

import concurrent.futures
import itertools
from collections.abc import Iterator, Sequence
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


def parse_stream(
    kind: str, paths: Sequence[Path], year: int | None, workers: int = 0
) -> Iterator[pa.Table | tuple[pa.Table, pa.Table]]:
    """Yield one parsed table per file, in input order.

    ``workers <= 1`` (or a single file) parses in-process; otherwise a bounded
    ``ProcessPoolExecutor`` parses files in parallel while results are consumed as they arrive.
    """
    if workers <= 1 or len(paths) <= 1:
        for path in paths:
            yield parse_one(kind, str(path), year)
        return
    with concurrent.futures.ProcessPoolExecutor(max_workers=min(workers, len(paths))) as pool:
        yield from pool.map(
            parse_one, itertools.repeat(kind), (str(p) for p in paths), itertools.repeat(year)
        )
