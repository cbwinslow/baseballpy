"""Unit tests for domain Enums and top-level package exports."""

from enum import IntEnum, StrEnum

import baseballpy as bp


def test_top_level_exports() -> None:
    """Verify all major sources, enums, and helpers are exported at top level."""
    # Enums
    assert issubclass(bp.PlayerIdType, StrEnum)
    assert issubclass(bp.LahmanTable, StrEnum)
    assert issubclass(bp.StatcastLeaderboard, StrEnum)
    assert issubclass(bp.PitchType, StrEnum)
    assert issubclass(bp.PlayerType, StrEnum)
    assert issubclass(bp.RetrosheetReferenceTable, StrEnum)
    assert issubclass(bp.GameLogType, StrEnum)
    assert issubclass(bp.EventCode, IntEnum)
    assert issubclass(bp.GameType, StrEnum)
    assert issubclass(bp.SportId, IntEnum)
    assert issubclass(bp.GameState, StrEnum)
    assert issubclass(bp.WriteMode, StrEnum)
    assert issubclass(bp.CompressionCodec, StrEnum)

    # Core Sources / Classes
    assert bp.ChadwickRegister is not None
    assert bp.LahmanSource is not None
    assert bp.StatcastExtractor is not None
    assert bp.RetrosheetSource is not None
    assert bp.MlbApiSource is not None
    assert bp.DuckDBSink is not None
    assert bp.ParquetSink is not None
    assert bp.PolarsSink is not None
    assert bp.BaseballDatabase is not None

    # Convenience Functions
    assert callable(bp.resolve_player)
    assert callable(bp.crosswalk)
    assert callable(bp.get_register)
    assert callable(bp.connect_db)
    assert callable(bp.sync_database)
    assert callable(bp.statcast)
    assert callable(bp.statcast_search)
    assert callable(bp.get_leaderboard)
    assert callable(bp.batting)
    assert callable(bp.pitching)
    assert callable(bp.people)
    assert callable(bp.teams)
    assert callable(bp.get_boxscore)
    assert callable(bp.get_schedule)
    assert callable(bp.events)
    assert callable(bp.game_logs)
    assert callable(bp.to_duckdb)
    assert callable(bp.to_parquet)
    assert callable(bp.to_polars)


def test_player_id_type_enum() -> None:
    """Test PlayerIdType enum values and StrEnum equality."""
    assert bp.PlayerIdType.MLBAM == "key_mlbam"
    assert bp.PlayerIdType.RETRO == "key_retro"
    assert bp.PlayerIdType.BBREF == "key_bbref"
    assert bp.PlayerIdType.FANGRAPHS == "key_fangraphs"
    assert bp.PlayerIdType.PERSON == "key_person"
    assert bp.PlayerIdType.UUID == "key_uuid"
    assert bp.PlayerIdType.MLBAM == "key_mlbam"


def test_lahman_table_enum() -> None:
    """Test LahmanTable enum values for all 27 canonical tables."""
    assert bp.LahmanTable.BATTING == "Batting"
    assert bp.LahmanTable.PITCHING == "Pitching"
    assert bp.LahmanTable.PEOPLE == "People"
    assert bp.LahmanTable.TEAMS == "Teams"
    assert bp.LahmanTable.FIELDING == "Fielding"
    assert bp.LahmanTable.SALARIES == "Salaries"
    assert bp.LahmanTable.HALL_OF_FAME == "HallOfFame"
    assert bp.LahmanTable.ALLSTAR_FULL == "AllstarFull"
    assert len(bp.LahmanTable) == 27


def test_statcast_enums() -> None:
    """Test Statcast leaderboard and pitch type enums."""
    assert bp.StatcastLeaderboard.BAT_TRACKING == "bat_tracking"
    assert bp.StatcastLeaderboard.EXIT_VELOCITY_BATTER == "exit_velocity_batter"
    assert bp.StatcastLeaderboard.EXPECTED_STATISTICS_PITCHER == "expected_statistics_pitcher"
    assert bp.StatcastLeaderboard.PITCH_ARSENALS == "pitch_arsenals"

    assert bp.PitchType.FOUR_SEAM == "FF"
    assert bp.PitchType.SINKER == "SI"
    assert bp.PitchType.SLIDER == "SL"
    assert bp.PitchType.SWEEPER == "ST"
    assert bp.PitchType.CHANGEUP == "CH"
    assert bp.PitchType.CURVEBALL == "CU"

    assert bp.PlayerType.BATTER == "batter"
    assert bp.PlayerType.PITCHER == "pitcher"


def test_retrosheet_enums() -> None:
    """Test Retrosheet table and game log enums."""
    assert bp.RetrosheetReferenceTable.BALLPARKS == "ballparks"
    assert bp.RetrosheetReferenceTable.TEAMS == "teams"
    assert bp.RetrosheetReferenceTable.BIOFILE == "biofile"

    assert bp.GameLogType.REGULAR == "regular"
    assert bp.GameLogType.ALLSTAR == "allstar"
    assert bp.GameLogType.WORLD_SERIES == "world_series"

    assert bp.EventCode.GENERIC_OUT == 2
    assert bp.EventCode.STRIKEOUT == 3
    assert bp.EventCode.WALK == 14
    assert bp.EventCode.SINGLE == 20
    assert bp.EventCode.HOME_RUN == 23


def test_mlb_api_enums() -> None:
    """Test MLB API game type, sport id, and game state enums."""
    assert bp.GameType.REGULAR == "R"
    assert bp.GameType.POSTSEASON == "P"
    assert bp.GameType.SPRING == "S"
    assert bp.GameType.EXHIBITION == "E"
    assert bp.GameType.ALLSTAR == "A"

    assert bp.SportId.MLB == 1
    assert bp.SportId.AAA == 11
    assert bp.SportId.AA == 12

    assert bp.GameState.FINAL == "F"
    assert bp.GameState.IN_PROGRESS == "I"
    assert bp.GameState.SCHEDULED == "S"


def test_sinks_enums() -> None:
    """Test Sinks WriteMode and CompressionCodec enums."""
    assert bp.WriteMode.APPEND == "append"
    assert bp.WriteMode.REPLACE == "replace"

    assert bp.CompressionCodec.SNAPPY == "snappy"
    assert bp.CompressionCodec.ZSTD == "zstd"
    assert bp.CompressionCodec.GZIP == "gzip"
    assert bp.CompressionCodec.NONE == "none"
