"""Storage and analytical sink implementations."""

from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink

__all__ = [
    "DuckDBSink",
    "ParquetSink",
]
