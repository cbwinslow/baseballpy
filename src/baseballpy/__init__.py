"""baseballpy: Fast, modular, and strongly-typed baseball data ingestion layer.

Unified extraction, normalization, and ingestion for Statcast, MLB API, Lahman,
Chadwick Registers, and Retrosheet into DuckDB, Polars, PyArrow, and dlt.
"""

from datetime import date
from typing import Any

import polars as pl
import pyarrow as pa

from baseballpy.core.protocols import (
    ExtractorProtocol,
    LiveEventConsumerProtocol,
    NormalizerProtocol,
    SinkProtocol,
    StreamExtractorProtocol,
)
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sources.chadwick.register import ChadwickRegister, PlayerRecord
from baseballpy.sources.statcast.extractor import StatcastExtractor
from baseballpy.sources.statcast.normalizer import StatcastNormalizer

__version__ = "0.1.0"


def resolve_player(
    *,
    mlbam: int | None = None,
    retro: str | None = None,
    bbref: str | None = None,
    fangraphs: int | None = None,
    person: str | None = None,
    name: str | None = None,
) -> PlayerRecord | list[PlayerRecord] | None:
    """Resolve a player across identifier systems (MLBAM, Retrosheet, BBRef, FanGraphs)."""
    reg = ChadwickRegister.load()
    if name is not None:
        return reg.search_name(name)
    return reg.resolve(
        mlbam=mlbam,
        retro=retro,
        bbref=bbref,
        fangraphs=fangraphs,
        person=person,
    )


def statcast(
    start_dt: str | date,
    end_dt: str | date,
    refresh: bool = False,
    **filters: Any,
) -> pa.Table:
    """Extract Statcast pitch tracking data for a date range with automatic weekly chunking."""
    extractor = StatcastExtractor()
    return extractor.extract(start_date=start_dt, end_date=end_dt, refresh=refresh, **filters)


def to_duckdb(
    table: pa.Table,
    destination: str = "baseball.duckdb",
    table_name: str = "pitches",
    mode: str = "append",
) -> int:
    """Sink an Arrow table directly into DuckDB without pandas conversion."""
    sink = DuckDBSink()
    return sink.write(table, destination=destination, table_name=table_name, mode=mode)


def to_parquet(
    table: pa.Table,
    destination: str,
    compression: str = "snappy",
) -> int:
    """Sink an Arrow table to a compressed Parquet file."""
    sink = ParquetSink()
    return sink.write(table, destination=destination, compression=compression)


def to_polars(table: pa.Table) -> pl.DataFrame:
    """Zero-copy handoff from Arrow Table to Polars DataFrame."""
    df = pl.from_arrow(table)
    assert isinstance(df, pl.DataFrame)
    return df


__all__ = [
    "ChadwickRegister",
    "DuckDBSink",
    "ExtractorProtocol",
    "LiveEventConsumerProtocol",
    "NormalizerProtocol",
    "ParquetSink",
    "PlayerRecord",
    "SinkProtocol",
    "StatcastExtractor",
    "StatcastNormalizer",
    "StreamExtractorProtocol",
    "__version__",
    "resolve_player",
    "statcast",
    "to_duckdb",
    "to_parquet",
    "to_polars",
]
