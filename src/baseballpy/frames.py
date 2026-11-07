"""DataFrame-library helpers: backend-agnostic conversion (narwhals) and lazy Parquet scans."""

from pathlib import Path
from typing import Any, Literal

import narwhals as nw
import polars as pl
import pyarrow as pa

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
