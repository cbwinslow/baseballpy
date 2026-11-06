"""The two ways to get data out of the lake and into Python.

* :func:`read` loads rows straight from the Parquet files into a DataFrame (Polars by default).
  Use it to pull a whole dataset or a few seasons, for example every Statcast pitch.
* :func:`sql` runs DuckDB SQL over the views (joins, group by, sum, filter) and returns a DataFrame.

Both read the same ``processed/`` files; neither copies data.
"""

from collections.abc import Iterable
from typing import Any

import duckdb
import polars as pl

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.frames import Backend, to_dataframe
from baseballpy.sources import catalog


def resolve_dataset(dataset: str) -> DatasetSpec:
    """Find a registered dataset by ``source.name``, view name or (unique) bare name."""
    catalog.register_all()
    if dataset in DATASETS:
        return DATASETS[dataset]
    matches = [d for d in DATASETS.values() if dataset in (d.view, d.name)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"unknown dataset {dataset!r}; list them with `baseballpy catalog status`")
    options = ", ".join(sorted(d.key for d in matches))
    raise ValueError(f"dataset name {dataset!r} is ambiguous; use one of: {options}")


def _season_list(seasons: int | Iterable[int]) -> list[int]:
    return [int(seasons)] if isinstance(seasons, int) else sorted({int(s) for s in seasons})


def read(
    dataset: str,
    seasons: int | Iterable[int] | None = None,
    columns: list[str] | None = None,
    *,
    backend: Backend = "polars",
    lazy: bool = False,
    config: LakeConfig | None = None,
) -> Any:
    """Load a dataset from the lake into a DataFrame.

    ``dataset`` is ``"source.name"`` (``"statcast.pitches"``), a view name or a unique bare name.
    ``seasons`` is one year or several (only those folders are opened); ``columns`` limits the
    columns read. ``lazy=True`` returns a Polars ``LazyFrame`` to filter before loading.
    ``backend`` is ``polars`` (default), ``pandas`` or ``pyarrow``.
    """
    spec = resolve_dataset(dataset)
    if lazy and backend != "polars":
        raise ValueError("lazy=True is only available with backend='polars'")
    root = (config or LakeConfig()).processed_dir(spec.source, spec.name)
    if not root.exists():
        raise FileNotFoundError(
            f"no data for {spec.key} at {root}; run `baseballpy ingest {spec.source}` first"
        )
    partitioned = spec.partition == "season"
    frame = pl.scan_parquet(str(root / "**" / "*.parquet"), hive_partitioning=partitioned)
    if seasons is not None:
        if not partitioned:
            raise ValueError(f"{spec.key} is not split by season; call read() without seasons")
        frame = frame.filter(pl.col("season").is_in(_season_list(seasons)))
    if columns is not None:
        frame = frame.select(columns)
    if lazy:
        return frame
    table = frame.collect()
    return table if backend == "polars" else to_dataframe(table.to_arrow(), backend)


def sql(
    query: str,
    *,
    backend: Backend = "polars",
    config: LakeConfig | None = None,
) -> Any:
    """Run a DuckDB SQL query over the lake views and return a DataFrame.

    Views are named like the datasets (``statcast_pitches``); the database is the one that
    ``baseballpy db sync`` keeps up to date. The connection is read-only, so this never changes data.
    """
    path = (config or LakeConfig()).database_path
    if not path.exists():
        raise FileNotFoundError(f"no database at {path}; run `baseballpy db sync` first")
    con = duckdb.connect(str(path), read_only=True)
    try:
        relation = con.sql(query)
        if relation is None:
            raise ValueError("the query returns no rows; baseballpy.sql() is read-only, use SELECT")
        table = relation.to_arrow_table()
    finally:
        con.close()
    return to_dataframe(table, backend)


__all__ = ["read", "resolve_dataset", "sql"]
