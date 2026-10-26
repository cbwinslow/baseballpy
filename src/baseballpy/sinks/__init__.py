"""Storage sinks for baseballpy ingestion pipelines."""

from baseballpy.sinks.dlt import DltSink
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sinks.polars import PolarsSink

__all__ = [
    "DuckDBSink",
    "ParquetSink",
    "PolarsSink",
    "DltSink",
]
