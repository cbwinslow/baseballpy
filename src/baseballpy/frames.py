"""DataFrame-library helpers: backend-agnostic conversion (narwhals) and lazy Parquet scans."""

from pathlib import Path
from typing import Any, Literal

import narwhals as nw
import polars as pl
import pyarrow as pa

from baseballpy.core.datasets import DatasetSpec, with_lineage

#: ``arrow`` is accepted as another name for ``pyarrow``
Backend = Literal["polars", "pandas", "pyarrow", "arrow"]


def to_dataframe(table: pa.Table, backend: Backend = "polars") -> Any:
    """Convert an Arrow table to a native DataFrame of the requested backend.

    ``pandas`` is an optional dependency and is only imported when requested.
    """
    backend = "pyarrow" if backend == "arrow" else backend
    if backend not in ("polars", "pandas", "pyarrow"):
        raise ValueError(f"unsupported backend {backend!r}; use polars, pandas or pyarrow (arrow)")
    try:
        return nw.from_arrow(table, backend=backend).to_native()
    except ModuleNotFoundError as exc:
        raise ImportError(
            f"backend {backend!r} needs the {exc.name!r} package: pip install {exc.name}"
        ) from exc


def scan(path: str | Path, *, hive_partitioning: bool = True) -> pl.LazyFrame:
    """Lazily scan a Parquet file, directory or glob (Hive ``season=YYYY`` partitions supported)."""
    target = Path(path)
    pattern = str(target / "**" / "*.parquet") if target.is_dir() else str(target)
    return pl.scan_parquet(pattern, hive_partitioning=hive_partitioning)


def scan_dataset(spec: DatasetSpec, root: Path) -> pl.LazyFrame:
    """Lazily scan every part of a registered dataset under the registered columns (ADR 87).

    Files written before the schema gained columns lack them: the cells come back empty instead of
    the scan failing on the first file that differs. A column the schema does not have is still an
    error, never dropped. Types of columns a file already holds are the file's own; only the
    missing columns take the registered type.

    Segment files (``seg-*.parquet``, ADR 95) carry one more column, ``_raw_sha256``: the sha256 of the
    response each row was made from. When a dataset holds segment files the scan has that column, empty
    for the rows of older files; a dataset without segment files comes back exactly as registered.
    """
    has_segments = next(root.rglob("seg-*.parquet"), None) is not None
    schema_to_scan = with_lineage(spec.schema) if has_segments else spec.schema
    registered = pl.from_arrow(schema_to_scan.empty_table())
    if not isinstance(registered, pl.DataFrame):
        raise TypeError("a schema must convert to a DataFrame")
    first = next(iter(root.rglob("*.parquet")), None)
    held = pl.read_parquet_schema(first) if first is not None else {}
    schema = {name: held.get(name, dtype) for name, dtype in registered.schema.items()}
    return pl.scan_parquet(
        str(root / "**" / "*.parquet"),
        hive_partitioning=spec.partition == "season",
        schema=schema,
        missing_columns="insert",
        extra_columns="raise",
    )
