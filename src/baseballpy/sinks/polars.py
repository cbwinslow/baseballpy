"""Polars sink implementation for zero-copy in-memory analytics."""

from typing import Any

import polars as pl
import pyarrow as pa


class PolarsSink:
    """Sink that converts PyArrow tables into Polars DataFrames or LazyFrames (zero copy)."""

    def __init__(self) -> None:
        self.last: pl.DataFrame | None = None

    def to_dataframe(self, table: pa.Table) -> pl.DataFrame:
        """Convert PyArrow Table to eager Polars DataFrame."""
        df = pl.from_arrow(table)
        if not isinstance(df, pl.DataFrame):
            raise TypeError(f"expected DataFrame from Arrow table, got {type(df).__name__}")
        return df

    def to_lazyframe(self, table: pa.Table) -> pl.LazyFrame:
        """Convert PyArrow Table to Polars LazyFrame."""
        return self.to_dataframe(table).lazy()

    def write(self, table: pa.Table, destination: str, **kwargs: Any) -> int:
        """SinkProtocol write: keeps the DataFrame in ``self.last`` and returns the row count."""
        self.last = self.to_dataframe(table)
        return len(self.last)

    def write_stream(self, reader: pa.RecordBatchReader, destination: str, **kwargs: Any) -> int:
        """SinkProtocol stream write: materializes the stream into ``self.last``."""
        return self.write(reader.read_all(), destination, **kwargs)
