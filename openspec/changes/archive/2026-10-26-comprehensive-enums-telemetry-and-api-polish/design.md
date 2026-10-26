# Design: Comprehensive Enums, Structured Telemetry Audit, and Top-Level API Polish

## 1. Domain Enums Design

All enums inherit from `enum.StrEnum` (for string-based identifiers) or `enum.IntEnum` (for integer codes) to ensure complete backward compatibility with raw strings and integers while granting strict typing and IDE auto-complete:

### Statcast Enums (`baseballpy.sources.statcast.schema` & `leaderboards`):
- `StatcastLeaderboard`: All 11 leaderboards (`BAT_TRACKING`, `EXIT_VELOCITY`, `EXPECTED_STATISTICS`, `SPRINT_SPEED`, `RUNNING_SPLITS`, `OUTS_ABOVE_AVERAGE`, `ARM_STRENGTH`, `POPTIME`, `CATCHER_FRAMING`, `PITCH_ARSENALS`, `ABS_CHALLENGES`).
- `PitchType`: MLBAM pitch classifications (`FOUR_SEAM = "FF"`, `SLIDER = "SL"`, `CHANGEUP = "CH"`, `CURVEBALL = "CU"`, `SINKER = "SI"`, `CUTTER = "FC"`, `SWEEPER = "ST"`, `SPLITTER = "FS"`, `SLURVE = "SV"`, `KNUCKLEBALL = "KN"`).
- `PlayerType`: Search perspective (`BATTER = "batter"`, `PITCHER = "pitcher"`).

### Retrosheet Enums (`baseballpy.sources.retrosheet.schema`):
- `RetrosheetReferenceTable`: Reference datasets (`BALLPARKS = "ballparks"`, `TEAMS = "teams"`, `EJECTIONS = "ejections"`, `COACHES = "coaches"`, `RELATIVES = "relatives"`, `BIOFILE = "biofile"`).
- `GameLogType`: Game log collections (`REGULAR = "regular"`, `ALLSTAR = "allstar"`, `WILDCARD = "wildcard"`, `DIVISION = "division"`, `LCS = "lcs"`, `WORLD_SERIES = "world_series"`).
- `EventCode`: Official Chadwick event codes (`SINGLE = 20`, `DOUBLE = 21`, `TRIPLE = 22`, `HOME_RUN = 23`, `WALK = 14`, `STRIKEOUT = 3`, etc.).

### MLB Stats API Enums (`baseballpy.sources.mlb_api.schema`):
- `GameType`: Official contest classification (`REGULAR = "R"`, `POSTSEASON = "P"`, `SPRING = "S"`, `EXHIBITION = "E"`, `ALLSTAR = "A"`).
- `SportId`: League and affiliate hierarchy (`MLB = 1`, `AAA = 11`, `AA = 12`, `HIGH_A = 13`, `SINGLE_A = 14`).
- `GameState`: Official contest lifecycle (`SCHEDULED = "S"`, `PRE_GAME = "P"`, `IN_PROGRESS = "I"`, `FINAL = "F"`, `POSTPONED = "D"`, `SUSPENDED = "U"`).

### Sinks Enums (`baseballpy.sinks`):
- `WriteMode`: Database table insertion strategy (`APPEND = "append"`, `REPLACE = "replace"`).
- `CompressionCodec`: Parquet compression algorithm (`SNAPPY = "snappy"`, `GZIP = "gzip"`, `ZSTD = "zstd"`, `NONE = "none"`).

## 2. Telemetry and Audit Integration

All `LahmanSource` methods (`get_table` and `import_archive`) are instrumented with `default_audit_logger.track(...)`:
- `operation="lahman_get_table"`, `endpoint=table_name`, `destination=target_parquet`.
- Records count, cache hit boolean, and start/completed timestamps recorded atomically in `~/.baseballpy/logs/audit.jsonl`.

## 3. Top-Level Package Namespace

Expose all core functions and classes directly at `baseballpy`:
```python
import baseballpy as bb

# Statcast
bb.statcast_search("2024-04-01", "2024-04-05")
bb.get_leaderboard(bb.StatcastLeaderboard.BAT_TRACKING, 2024)

# Chadwick
bb.crosswalk(660271, bb.PlayerIdType.MLBAM, bb.PlayerIdType.RETRO)
bb.get_register().search_name("Pete Alonso")

# Lahman
bb.batting()
bb.pitching()
bb.people()
bb.teams()
bb.import_archive("~/Downloads/lahman-2025-csv.zip")

# Retrosheet & MLB API
retro = bb.RetrosheetSource()
mlb = bb.MlbApiSource()
```
