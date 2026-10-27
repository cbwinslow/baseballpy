"""baseballpy: Fast, modular, and strongly-typed baseball data ingestion layer.

Unified extraction, normalization, and ingestion for Statcast, MLB API, Lahman,
Chadwick Registers, and Retrosheet into DuckDB, Polars, PyArrow, and dlt.
"""

from datetime import date
from pathlib import Path
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
from baseballpy.database import BaseballDatabase, connect_db, sync_database
from baseballpy.frames import scan, to_dataframe
from baseballpy.sinks import (
    CompressionCodec,
    DltSink,
    DuckDBSink,
    ParquetSink,
    PolarsSink,
    WriteMode,
)
from baseballpy.sources import chadwick, lahman, mlb_api, retrosheet
from baseballpy.sources import mlb_api as mlb
from baseballpy.sources import statcast as statcast_module
from baseballpy.sources.chadwick import (
    ChadwickExtractor,
    ChadwickNormalizer,
    ChadwickRegister,
    PlayerIdType,
    PlayerRecord,
    crosswalk,
    get_register,
)
from baseballpy.sources.lahman import (
    LahmanExtractor,
    LahmanNormalizer,
    LahmanSource,
    LahmanTable,
    allstar,
    batting,
    fielding,
    hall_of_fame,
    import_archive,
    people,
    pitching,
    salaries,
    teams,
)
from baseballpy.sources.mlb_api import (
    GamedayLiveStreamer,
    GameState,
    GameType,
    MlbApiExtractor,
    MlbApiNormalizer,
    MlbApiSource,
    SportId,
    get_boxscore,
    get_draft,
    get_roster,
    get_schedule,
    get_standings,
    get_teams,
    get_transactions,
    get_venues,
    stream_game,
)
from baseballpy.sources.retrosheet import (
    EventCode,
    GameLogType,
    RetrosheetDownloader,
    RetrosheetReferenceTable,
    RetrosheetSource,
    boxscores,
    daily_splits,
    events,
    game_logs,
    postseason_game_logs,
    reference,
    rosters,
    substitutions,
)
from baseballpy.sources.statcast import (
    PitchType,
    PlayerType,
    StatcastExtractor,
    StatcastLeaderboard,
    StatcastLeaderboardExtractor,
    StatcastLeaderboardNormalizer,
    StatcastNormalizer,
    get_leaderboard,
    statcast_search,
)

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
    mode: str | WriteMode = WriteMode.APPEND,
) -> int:
    """Sink an Arrow table directly into DuckDB without pandas conversion."""
    sink = DuckDBSink()
    mode_str = mode.value if isinstance(mode, WriteMode) else mode
    return sink.write(table, destination=destination, table_name=table_name, mode=mode_str)


def to_parquet(
    table: pa.Table,
    destination: str | Path,
    compression: str | CompressionCodec = CompressionCodec.SNAPPY,
) -> int:
    """Sink an Arrow table to a compressed Parquet file."""
    sink = ParquetSink()
    comp_str = compression.value if isinstance(compression, CompressionCodec) else compression
    return sink.write(table, destination=str(destination), compression=comp_str)


def to_polars(table: pa.Table) -> pl.DataFrame:
    """Zero-copy handoff from Arrow Table to Polars DataFrame."""
    sink = PolarsSink()
    return sink.to_dataframe(table)


__all__ = [
    # Version
    "__version__",
    # Submodules
    "chadwick",
    "lahman",
    "mlb",
    "mlb_api",
    "retrosheet",
    "statcast_module",
    # Enums
    "CompressionCodec",
    "EventCode",
    "GameLogType",
    "GameState",
    "GameType",
    "LahmanTable",
    "PitchType",
    "PlayerIdType",
    "PlayerType",
    "RetrosheetReferenceTable",
    "SportId",
    "StatcastLeaderboard",
    "WriteMode",
    # Protocols
    "ExtractorProtocol",
    "LiveEventConsumerProtocol",
    "NormalizerProtocol",
    "SinkProtocol",
    "StreamExtractorProtocol",
    # Classes / Sources
    "BaseballDatabase",
    "ChadwickExtractor",
    "ChadwickNormalizer",
    "ChadwickRegister",
    "DltSink",
    "DuckDBSink",
    "GamedayLiveStreamer",
    "LahmanExtractor",
    "LahmanNormalizer",
    "LahmanSource",
    "MlbApiExtractor",
    "MlbApiNormalizer",
    "MlbApiSource",
    "ParquetSink",
    "PlayerRecord",
    "PolarsSink",
    "RetrosheetDownloader",
    "RetrosheetSource",
    "StatcastExtractor",
    "StatcastLeaderboardExtractor",
    "StatcastLeaderboardNormalizer",
    "StatcastNormalizer",
    # Convenience Functions - Sinks & Database
    "connect_db",
    "sync_database",
    "scan",
    "to_dataframe",
    "to_duckdb",
    "to_parquet",
    "to_polars",
    # Convenience Functions - Statcast
    "get_leaderboard",
    "statcast",
    "statcast_search",
    # Convenience Functions - Chadwick
    "crosswalk",
    "get_register",
    "resolve_player",
    # Convenience Functions - Lahman
    "allstar",
    "batting",
    "fielding",
    "hall_of_fame",
    "import_archive",
    "people",
    "pitching",
    "salaries",
    "teams",
    # Convenience Functions - MLB API
    "get_boxscore",
    "get_draft",
    "get_roster",
    "get_schedule",
    "get_standings",
    "get_teams",
    "get_transactions",
    "get_venues",
    "stream_game",
    # Convenience Functions - Retrosheet
    "boxscores",
    "daily_splits",
    "events",
    "game_logs",
    "postseason_game_logs",
    "reference",
    "rosters",
    "substitutions",
]
