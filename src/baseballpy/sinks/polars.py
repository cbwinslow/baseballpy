"""Polars sink implementation for zero-copy in-memory analytics."""

from typing import Any

import polars as pl
import pyarrow as pa


class PolarsSink:
    """Sink that converts PyArrow tables into Polars DataFrames or LazyFrames with zero memory copy."""

    def to_dataframe(self, table: pa.Table) -> pl.DataFrame:
        """Convert PyArrow Table to eager Polars DataFrame."""
        df = pl.from_arrow(table)
        assert isinstance(df, pl.DataFrame)
        return df

    def to_lazyframe(self, table: pa.Table) -> pl.LazyFrame:
        """Convert PyArrow Table to Polars LazyFrame."""
        return self.to_dataframe(table).lazy()

    def write(self, data: pa.Table, destination: str, **kwargs: Any) -> pl.DataFrame:
        """Write method implementing SinkProtocol."""
        return self.to_dataframe(data)
