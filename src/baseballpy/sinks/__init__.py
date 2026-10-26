"""Storage sinks and options for baseballpy ingestion pipelines."""

from enum import StrEnum

from baseballpy.sinks.dlt import DltSink
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sinks.polars import PolarsSink


class WriteMode(StrEnum):
    """Storage write disposition."""

    APPEND = "append"
    REPLACE = "replace"


class CompressionCodec(StrEnum):
    """Parquet compression codecs."""

    SNAPPY = "snappy"
    GZIP = "gzip"
    ZSTD = "zstd"
    NONE = "none"


__all__ = [
    "CompressionCodec",
    "DltSink",
    "DuckDBSink",
    "ParquetSink",
    "PolarsSink",
    "WriteMode",
]
