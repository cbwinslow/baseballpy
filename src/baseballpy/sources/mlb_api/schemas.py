"""Canonical PyArrow schemas and Enums for MLB Stats API endpoints."""

from enum import IntEnum, StrEnum

import pyarrow as pa


class GameType(StrEnum):
    """Official MLB contest type classifications."""

    REGULAR = "R"
    POSTSEASON = "P"
    SPRING = "S"
    EXHIBITION = "E"
    ALLSTAR = "A"
    WILD_CARD = "F"
    DIVISION_SERIES = "D"
    LEAGUE_CHAMPIONSHIP = "L"
    WORLD_SERIES = "W"
    CHAMPIONSHIP = "C"
    INTRASQUAD = "I"


class SportId(IntEnum):
    """MLB sport / affiliate tier hierarchy."""

    MLB = 1
    AAA = 11
    AA = 12
    HIGH_A = 13
    SINGLE_A = 14
    ROOKIE = 16
    WINTER = 17


class GameState(StrEnum):
    """Game status lifecycle codes."""

    SCHEDULED = "S"
    PRE_GAME = "P"
    WARMUP = "PW"
    IN_PROGRESS = "I"
    DELAYED = "PR"
    FINAL = "F"
    COMPLETED_EARLY = "C"
    POSTPONED = "D"
    SUSPENDED = "U"


# 1. Schedule Schema
MLB_SCHEDULE_SCHEMA = pa.schema(
    [
        ("game_pk", pa.int32()),
        ("game_date", pa.date32()),
        ("game_type", pa.string()),
        ("season", pa.int16()),
        ("status_code", pa.string()),
        ("status_detailed", pa.string()),
        ("away_team_id", pa.int32()),
        ("away_team_name", pa.string()),
        ("away_score", pa.int16()),
        ("home_team_id", pa.int32()),
        ("home_team_name", pa.string()),
        ("home_score", pa.int16()),
        ("doubleheader", pa.string()),
        ("game_num", pa.int8()),
        ("venue_id", pa.int32()),
        ("venue_name", pa.string()),
    ]
)

# 2. Live Gameday Play Events Schema
MLB_LIVE_PLAYS_SCHEMA = pa.schema(
    [
        ("game_pk", pa.int32()),
        ("at_bat_index", pa.int16()),
        ("event_index", pa.int16()),
        ("is_pitch", pa.bool_()),
        ("pitch_type", pa.string()),
        ("start_speed", pa.float32()),
        ("end_speed", pa.float32()),
        ("sz_top", pa.float32()),
        ("sz_bottom", pa.float32()),
        ("px", pa.float32()),
        ("pz", pa.float32()),
        ("x", pa.float32()),
        ("y", pa.float32()),
        ("description", pa.string()),
        ("call_code", pa.string()),
        ("event", pa.string()),
        ("event_type", pa.string()),
        ("batter_id", pa.int32()),
        ("pitcher_id", pa.int32()),
        ("inning", pa.int8()),
        ("is_top_inning", pa.bool_()),
        ("outs", pa.int8()),
        ("balls", pa.int8()),
        ("strikes", pa.int8()),
        ("timestamp", pa.string()),
    ]
)

# 3. Batting Boxscore Schema
MLB_BOX_BATTING_SCHEMA = pa.schema(
    [
        ("game_pk", pa.int32()),
        ("team_id", pa.int32()),
        ("player_id", pa.int32()),
        ("player_name", pa.string()),
        ("position", pa.string()),
        ("batting_order", pa.int16()),
        ("ab", pa.int16()),
        ("r", pa.int16()),
        ("h", pa.int16()),
        ("d", pa.int16()),
        ("t", pa.int16()),
        ("hr", pa.int16()),
        ("rbi", pa.int16()),
        ("bb", pa.int16()),
        ("so", pa.int16()),
        ("sb", pa.int16()),
        ("cs", pa.int16()),
    ]
)

# 4. Pitching Boxscore Schema
MLB_BOX_PITCHING_SCHEMA = pa.schema(
    [
        ("game_pk", pa.int32()),
        ("team_id", pa.int32()),
        ("player_id", pa.int32()),
        ("player_name", pa.string()),
        ("ip", pa.float32()),
        ("h", pa.int16()),
        ("r", pa.int16()),
        ("er", pa.int16()),
        ("bb", pa.int16()),
        ("so", pa.int16()),
        ("hr", pa.int16()),
        ("pitches", pa.int16()),
        ("strikes", pa.int16()),
    ]
)

# 5. Standings Schema
MLB_STANDINGS_SCHEMA = pa.schema(
    [
        ("season", pa.int16()),
        ("division_id", pa.int32()),
        ("division_name", pa.string()),
        ("team_id", pa.int32()),
        ("team_name", pa.string()),
        ("wins", pa.int16()),
        ("losses", pa.int16()),
        ("win_pct", pa.float32()),
        ("games_back", pa.float32()),
        ("wild_card_gb", pa.float32()),
        ("run_differential", pa.int16()),
        ("streak", pa.string()),
        ("elim_num", pa.int16()),
    ]
)

# 6. Teams Schema
MLB_TEAMS_SCHEMA = pa.schema(
    [
        ("team_id", pa.int32()),
        ("team_name", pa.string()),
        ("abbreviation", pa.string()),
        ("league_id", pa.int32()),
        ("league_name", pa.string()),
        ("division_id", pa.int32()),
        ("division_name", pa.string()),
        ("venue_id", pa.int32()),
        ("venue_name", pa.string()),
        ("active", pa.bool_()),
    ]
)

# 7. Rosters Schema
MLB_ROSTERS_SCHEMA = pa.schema(
    [
        ("team_id", pa.int32()),
        ("player_id", pa.int32()),
        ("player_name", pa.string()),
        ("jersey_number", pa.string()),
        ("position_code", pa.string()),
        ("position_name", pa.string()),
        ("status", pa.string()),
    ]
)

# 8. Transactions Schema
MLB_TRANSACTIONS_SCHEMA = pa.schema(
    [
        ("transaction_id", pa.int32()),
        ("date", pa.string()),
        ("player_id", pa.int32()),
        ("player_name", pa.string()),
        ("from_team_id", pa.int32()),
        ("to_team_id", pa.int32()),
        ("type_code", pa.string()),
        ("type_desc", pa.string()),
        ("description", pa.string()),
    ]
)

# 9. Draft Schema
MLB_DRAFT_SCHEMA = pa.schema(
    [
        ("year", pa.int16()),
        ("round", pa.string()),
        ("pick_round", pa.int16()),
        ("pick_overall", pa.int16()),
        ("team_id", pa.int32()),
        ("player_id", pa.int32()),
        ("player_name", pa.string()),
        ("school_name", pa.string()),
        ("signing_bonus", pa.int64()),
    ]
)

# 10. Venues Schema
MLB_VENUES_SCHEMA = pa.schema(
    [
        ("venue_id", pa.int32()),
        ("venue_name", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("country", pa.string()),
        ("capacity", pa.int32()),
        ("turf_type", pa.string()),
        ("roof_type", pa.string()),
    ]
)
