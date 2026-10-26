"""Canonical PyArrow schemas and Enums for Retrosheet datasets."""

from enum import IntEnum, StrEnum

import pyarrow as pa
from chadwickpy.tools.daily import COLUMNS as DAILY_COLUMNS
from chadwickpy.tools.sub import COLUMNS as SUB_COLUMNS


class RetrosheetReferenceTable(StrEnum):
    """Reference datasets provided by Retrosheet."""

    BALLPARKS = "ballparks"
    TEAMS = "teams"
    EJECTIONS = "ejections"
    COACHES = "coaches"
    RELATIVES = "relatives"
    BIOFILE = "biofile"


class GameLogType(StrEnum):
    """Retrosheet historical game log categories."""

    REGULAR = "regular"
    ALLSTAR = "allstar"
    WILDCARD = "wildcard"
    DIVISION = "division"
    LCS = "lcs"
    WORLD_SERIES = "world_series"


class EventCode(IntEnum):
    """Official Chadwick play outcome event codes."""

    UNKNOWN = 0
    GENERIC_OUT = 2
    STRIKEOUT = 3
    STOLEN_BASE = 4
    DEFENSIVE_INDIFFERENCE = 5
    CAUGHT_STEALING = 6
    PICKOFF_ERROR = 8
    WILD_PITCH = 9
    PASSED_BALL = 10
    BALK = 11
    OTHER_ADVANCE = 12
    FOUL_ERROR = 13
    WALK = 14
    INTENTIONAL_WALK = 15
    HIT_BY_PITCH = 16
    INTERFERENCE = 17
    ERROR = 18
    FIELDERS_CHOICE = 19
    SINGLE = 20
    DOUBLE = 21
    TRIPLE = 22
    HOME_RUN = 23


# 1. Retrosheet Play-by-Play Event Schema (Chadwick cwevent 97 standard fields)
RETROSHEET_EVENT_FIELDS = [
    ("GAME_ID", pa.string()),
    ("AWAY_TEAM_ID", pa.string()),
    ("INN_CT", pa.int16()),
    ("BAT_HOME_ID", pa.int8()),
    ("OUTS_CT", pa.int8()),
    ("BALLS_CT", pa.int8()),
    ("STRIKES_CT", pa.int8()),
    ("PITCH_SEQ_TX", pa.string()),
    ("AWAY_SCORE_CT", pa.int16()),
    ("HOME_SCORE_CT", pa.int16()),
    ("BAT_ID", pa.string()),
    ("BAT_HAND_CD", pa.string()),
    ("RESP_BAT_ID", pa.string()),
    ("RESP_BAT_HAND_CD", pa.string()),
    ("PIT_ID", pa.string()),
    ("PIT_HAND_CD", pa.string()),
    ("RESP_PIT_ID", pa.string()),
    ("RESP_PIT_HAND_CD", pa.string()),
    ("POS2_FLD_ID", pa.string()),
    ("POS3_FLD_ID", pa.string()),
    ("POS4_FLD_ID", pa.string()),
    ("POS5_FLD_ID", pa.string()),
    ("POS6_FLD_ID", pa.string()),
    ("POS7_FLD_ID", pa.string()),
    ("POS8_FLD_ID", pa.string()),
    ("POS9_FLD_ID", pa.string()),
    ("BASE1_RUN_ID", pa.string()),
    ("BASE2_RUN_ID", pa.string()),
    ("BASE3_RUN_ID", pa.string()),
    ("EVENT_TX", pa.string()),
    ("LEADOFF_FL", pa.bool_()),
    ("PH_FL", pa.bool_()),
    ("BAT_FLD_CD", pa.int8()),
    ("BAT_LINEUP_ID", pa.int8()),
    ("EVENT_CD", pa.int16()),
    ("BAT_EVENT_FL", pa.bool_()),
    ("AB_FL", pa.bool_()),
    ("H_CD", pa.int8()),
    ("SH_FL", pa.bool_()),
    ("SF_FL", pa.bool_()),
    ("EVENT_OUTS_CT", pa.int8()),
    ("DP_FL", pa.bool_()),
    ("TP_FL", pa.bool_()),
    ("RBI_CT", pa.int8()),
    ("WP_FL", pa.bool_()),
    ("PB_FL", pa.bool_()),
    ("FLD_CD", pa.int8()),
    ("BATTEDBALL_CD", pa.string()),
    ("BUNT_FL", pa.bool_()),
    ("FOUL_FL", pa.bool_()),
    ("BATTEDBALL_LOC_TX", pa.string()),
    ("ERR_CT", pa.int8()),
    ("ERR1_FLD_CD", pa.int8()),
    ("ERR1_CD", pa.string()),
    ("ERR2_FLD_CD", pa.int8()),
    ("ERR2_CD", pa.string()),
    ("ERR3_FLD_CD", pa.int8()),
    ("ERR3_CD", pa.string()),
    ("BAT_DEST_ID", pa.int8()),
    ("RUN1_DEST_ID", pa.int8()),
    ("RUN2_DEST_ID", pa.int8()),
    ("RUN3_DEST_ID", pa.int8()),
    ("BAT_PLAY_TX", pa.string()),
    ("RUN1_PLAY_TX", pa.string()),
    ("RUN2_PLAY_TX", pa.string()),
    ("RUN3_PLAY_TX", pa.string()),
    ("RUN1_SB_FL", pa.bool_()),
    ("RUN2_SB_FL", pa.bool_()),
    ("RUN3_SB_FL", pa.bool_()),
    ("RUN1_CS_FL", pa.bool_()),
    ("RUN2_CS_FL", pa.bool_()),
    ("RUN3_CS_FL", pa.bool_()),
    ("RUN1_PK_FL", pa.bool_()),
    ("RUN2_PK_FL", pa.bool_()),
    ("RUN3_PK_FL", pa.bool_()),
    ("RUN1_RESP_PIT_ID", pa.string()),
    ("RUN2_RESP_PIT_ID", pa.string()),
    ("RUN3_RESP_PIT_ID", pa.string()),
    ("GAME_NEW_FL", pa.bool_()),
    ("GAME_END_FL", pa.bool_()),
    ("PR_RUN1_FL", pa.bool_()),
    ("PR_RUN2_FL", pa.bool_()),
    ("PR_RUN3_FL", pa.bool_()),
    ("REMOVED_FOR_PR_RUN1_ID", pa.string()),
    ("REMOVED_FOR_PR_RUN2_ID", pa.string()),
    ("REMOVED_FOR_PR_RUN3_ID", pa.string()),
    ("REMOVED_FOR_PH_BAT_ID", pa.string()),
    ("REMOVED_FOR_PH_BAT_FLD_CD", pa.int8()),
    ("PO1_FLD_CD", pa.int8()),
    ("PO2_FLD_CD", pa.int8()),
    ("PO3_FLD_CD", pa.int8()),
    ("ASS1_FLD_CD", pa.int8()),
    ("ASS2_FLD_CD", pa.int8()),
    ("ASS3_FLD_CD", pa.int8()),
    ("ERR1_FLD_CD_NEW", pa.int8()),
    ("ERR2_FLD_CD_NEW", pa.int8()),
    ("ERR3_FLD_CD_NEW", pa.int8()),
    ("BAT_LAST_ID", pa.int8()),
]

RETROSHEET_EVENT_SCHEMA = pa.schema(RETROSHEET_EVENT_FIELDS)

# 2. Retrosheet Historical Game Log Schema (161 standard fields)
RETROSHEET_GAMELOG_SCHEMA = pa.schema(
    [
        ("date", pa.date32()),
        ("game_num", pa.int8()),
        ("day_of_week", pa.string()),
        ("visiting_team", pa.string()),
        ("visiting_league", pa.string()),
        ("visiting_game_num", pa.int16()),
        ("home_team", pa.string()),
        ("home_league", pa.string()),
        ("home_game_num", pa.int16()),
        ("visiting_score", pa.int16()),
        ("home_score", pa.int16()),
        ("outs_total", pa.int16()),
        ("day_night", pa.string()),
        ("completion", pa.string()),
        ("forfeit", pa.string()),
        ("protest", pa.string()),
        ("park_id", pa.string()),
        ("attendance", pa.int32()),
        ("time_of_game", pa.int16()),
        ("visiting_line_score", pa.string()),
        ("home_line_score", pa.string()),
        # Visiting offense
        ("v_ab", pa.int16()),
        ("v_h", pa.int16()),
        ("v_2b", pa.int16()),
        ("v_3b", pa.int16()),
        ("v_hr", pa.int16()),
        ("v_rbi", pa.int16()),
        ("v_sh", pa.int16()),
        ("v_sf", pa.int16()),
        ("v_hbp", pa.int16()),
        ("v_bb", pa.int16()),
        ("v_ibb", pa.int16()),
        ("v_so", pa.int16()),
        ("v_sb", pa.int16()),
        ("v_cs", pa.int16()),
        ("v_gidp", pa.int16()),
        ("v_ci", pa.int16()),
        ("v_lob", pa.int16()),
        # Visiting pitching
        ("v_pitchers_used", pa.int16()),
        ("v_ind_er", pa.int16()),
        ("v_team_er", pa.int16()),
        ("v_wp", pa.int16()),
        ("v_balks", pa.int16()),
        # Visiting defense
        ("v_putouts", pa.int16()),
        ("v_assists", pa.int16()),
        ("v_errors", pa.int16()),
        ("v_passed_balls", pa.int16()),
        ("v_double_plays", pa.int16()),
        ("v_triple_plays", pa.int16()),
        # Home offense
        ("h_ab", pa.int16()),
        ("h_h", pa.int16()),
        ("h_2b", pa.int16()),
        ("h_3b", pa.int16()),
        ("h_hr", pa.int16()),
        ("h_rbi", pa.int16()),
        ("h_sh", pa.int16()),
        ("h_sf", pa.int16()),
        ("h_hbp", pa.int16()),
        ("h_bb", pa.int16()),
        ("h_ibb", pa.int16()),
        ("h_so", pa.int16()),
        ("h_sb", pa.int16()),
        ("h_cs", pa.int16()),
        ("h_gidp", pa.int16()),
        ("h_ci", pa.int16()),
        ("h_lob", pa.int16()),
        # Home pitching
        ("h_pitchers_used", pa.int16()),
        ("h_ind_er", pa.int16()),
        ("h_team_er", pa.int16()),
        ("h_wp", pa.int16()),
        ("h_balks", pa.int16()),
        # Home defense
        ("h_putouts", pa.int16()),
        ("h_assists", pa.int16()),
        ("h_errors", pa.int16()),
        ("h_passed_balls", pa.int16()),
        ("h_double_plays", pa.int16()),
        ("h_triple_plays", pa.int16()),
        # Umpires
        ("hp_ump_id", pa.string()),
        ("hp_ump_name", pa.string()),
        ("1b_ump_id", pa.string()),
        ("1b_ump_name", pa.string()),
        ("2b_ump_id", pa.string()),
        ("2b_ump_name", pa.string()),
        ("3b_ump_id", pa.string()),
        ("3b_ump_name", pa.string()),
        ("lf_ump_id", pa.string()),
        ("lf_ump_name", pa.string()),
        ("rf_ump_id", pa.string()),
        ("rf_ump_name", pa.string()),
        # Managers
        ("v_manager_id", pa.string()),
        ("v_manager_name", pa.string()),
        ("h_manager_id", pa.string()),
        ("h_manager_name", pa.string()),
        # Pitchers of record
        ("win_pitcher_id", pa.string()),
        ("win_pitcher_name", pa.string()),
        ("lose_pitcher_id", pa.string()),
        ("lose_pitcher_name", pa.string()),
        ("save_pitcher_id", pa.string()),
        ("save_pitcher_name", pa.string()),
        ("gwrbi_id", pa.string()),
        ("gwrbi_name", pa.string()),
        # Starting pitchers
        ("v_start_pitcher_id", pa.string()),
        ("v_start_pitcher_name", pa.string()),
        ("h_start_pitcher_id", pa.string()),
        ("h_start_pitcher_name", pa.string()),
        # Lineups (Visiting starters 1-9: id, name, pos)
        ("v_b1_id", pa.string()),
        ("v_b1_name", pa.string()),
        ("v_b1_pos", pa.int8()),
        ("v_b2_id", pa.string()),
        ("v_b2_name", pa.string()),
        ("v_b2_pos", pa.int8()),
        ("v_b3_id", pa.string()),
        ("v_b3_name", pa.string()),
        ("v_b3_pos", pa.int8()),
        ("v_b4_id", pa.string()),
        ("v_b4_name", pa.string()),
        ("v_b4_pos", pa.int8()),
        ("v_b5_id", pa.string()),
        ("v_b5_name", pa.string()),
        ("v_b5_pos", pa.int8()),
        ("v_b6_id", pa.string()),
        ("v_b6_name", pa.string()),
        ("v_b6_pos", pa.int8()),
        ("v_b7_id", pa.string()),
        ("v_b7_name", pa.string()),
        ("v_b7_pos", pa.int8()),
        ("v_b8_id", pa.string()),
        ("v_b8_name", pa.string()),
        ("v_b8_pos", pa.int8()),
        ("v_b9_id", pa.string()),
        ("v_b9_name", pa.string()),
        ("v_b9_pos", pa.int8()),
        # Lineups (Home starters 1-9: id, name, pos)
        ("h_b1_id", pa.string()),
        ("h_b1_name", pa.string()),
        ("h_b1_pos", pa.int8()),
        ("h_b2_id", pa.string()),
        ("h_b2_name", pa.string()),
        ("h_b2_pos", pa.int8()),
        ("h_b3_id", pa.string()),
        ("h_b3_name", pa.string()),
        ("h_b3_pos", pa.int8()),
        ("h_b4_id", pa.string()),
        ("h_b4_name", pa.string()),
        ("h_b4_pos", pa.int8()),
        ("h_b5_id", pa.string()),
        ("h_b5_name", pa.string()),
        ("h_b5_pos", pa.int8()),
        ("h_b6_id", pa.string()),
        ("h_b6_name", pa.string()),
        ("h_b6_pos", pa.int8()),
        ("h_b7_id", pa.string()),
        ("h_b7_name", pa.string()),
        ("h_b7_pos", pa.int8()),
        ("h_b8_id", pa.string()),
        ("h_b8_name", pa.string()),
        ("h_b8_pos", pa.int8()),
        ("h_b9_id", pa.string()),
        ("h_b9_name", pa.string()),
        ("h_b9_pos", pa.int8()),
        ("additional_info", pa.string()),
        ("acquisition_info", pa.string()),
    ]
)

# 3. Retrosheet Roster Schema (.ROS)
RETROSHEET_ROSTER_SCHEMA = pa.schema(
    [
        ("player_id", pa.string()),
        ("last_name", pa.string()),
        ("first_name", pa.string()),
        ("bats", pa.string()),
        ("throws", pa.string()),
        ("team", pa.string()),
        ("position", pa.string()),
        ("year", pa.int16()),
    ]
)

# 4. Boxscore Batting Schema
RETROSHEET_BOX_BATTING_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("team_id", pa.string()),
        ("player_id", pa.string()),
        ("player_name", pa.string()),
        ("slot", pa.int8()),
        ("pos", pa.int8()),
        ("ab", pa.int16()),
        ("r", pa.int16()),
        ("h", pa.int16()),
        ("d", pa.int16()),
        ("t", pa.int16()),
        ("hr", pa.int16()),
        ("rbi", pa.int16()),
        ("bb", pa.int16()),
        ("ibb", pa.int16()),
        ("so", pa.int16()),
        ("hbp", pa.int16()),
        ("sh", pa.int16()),
        ("sf", pa.int16()),
        ("sb", pa.int16()),
        ("cs", pa.int16()),
        ("gidp", pa.int16()),
        ("pa", pa.int16()),
    ]
)

# 5. Boxscore Pitching Schema
RETROSHEET_BOX_PITCHING_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("team_id", pa.string()),
        ("pitcher_id", pa.string()),
        ("pitcher_name", pa.string()),
        ("starter_fl", pa.bool_()),
        ("seq", pa.int8()),
        ("outs_recorded", pa.int16()),
        ("bf", pa.int16()),
        ("h", pa.int16()),
        ("r", pa.int16()),
        ("er", pa.int16()),
        ("bb", pa.int16()),
        ("ibb", pa.int16()),
        ("so", pa.int16()),
        ("hr", pa.int16()),
        ("hbp", pa.int16()),
        ("wp", pa.int16()),
        ("bk", pa.int16()),
        ("pitches", pa.int16()),
        ("strikes", pa.int16()),
        ("w", pa.bool_()),
        ("l", pa.bool_()),
        ("sv", pa.bool_()),
        ("cg", pa.bool_()),
        ("sho", pa.bool_()),
        ("gf", pa.bool_()),
    ]
)

# 6. Daily Player Splits Schema (154 columns generated by daily.COLUMNS)
RETROSHEET_DAILY_SPLITS_FIELDS = []
for col in DAILY_COLUMNS:
    if col in (
        "GAME_ID",
        "TEAM_ID",
        "PLAYER_ID",
        "OPPONENT_ID",
        "PARK_ID",
        "GAME_DT",
        "APPEAR_DT",
    ):
        RETROSHEET_DAILY_SPLITS_FIELDS.append((col, pa.string()))
    elif col in ("HOME_FL", "B_G_DH", "B_G_PH", "B_G_PR"):
        RETROSHEET_DAILY_SPLITS_FIELDS.append((col, pa.int8()))
    else:
        RETROSHEET_DAILY_SPLITS_FIELDS.append((col, pa.int16()))

RETROSHEET_DAILY_SPLITS_SCHEMA = pa.schema(RETROSHEET_DAILY_SPLITS_FIELDS)

# 7. Substitutions Schema (26 columns generated by sub.COLUMNS)
RETROSHEET_SUBSTITUTIONS_FIELDS = []
for col in SUB_COLUMNS:
    if col in ("GAME_ID", "SUB_ID", "REMOVED_ID", "PITCH_SEQ_TX", "COUNT_TX"):
        RETROSHEET_SUBSTITUTIONS_FIELDS.append((col, pa.string()))
    else:
        RETROSHEET_SUBSTITUTIONS_FIELDS.append((col, pa.int16()))

RETROSHEET_SUBSTITUTIONS_SCHEMA = pa.schema(RETROSHEET_SUBSTITUTIONS_FIELDS)

# 8. Reference Tables Schemas
RETROSHEET_BALLPARKS_SCHEMA = pa.schema(
    [
        ("park_id", pa.string()),
        ("name", pa.string()),
        ("aka", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
        ("league", pa.string()),
        ("notes", pa.string()),
    ]
)

RETROSHEET_TEAMS_SCHEMA = pa.schema(
    [
        ("team_id", pa.string()),
        ("league", pa.string()),
        ("city", pa.string()),
        ("nickname", pa.string()),
        ("first_year", pa.int16()),
        ("last_year", pa.int16()),
    ]
)

RETROSHEET_EJECTIONS_SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("date", pa.string()),
        ("dh", pa.int8()),
        ("ejectee_id", pa.string()),
        ("ejectee_name", pa.string()),
        ("team_id", pa.string()),
        ("job", pa.string()),
        ("umpire_id", pa.string()),
        ("umpire_name", pa.string()),
        ("inning", pa.int8()),
        ("reason", pa.string()),
    ]
)

RETROSHEET_COACHES_SCHEMA = pa.schema(
    [
        ("coach_id", pa.string()),
        ("year", pa.int16()),
        ("team_id", pa.string()),
        ("role", pa.string()),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
    ]
)

RETROSHEET_RELATIVES_SCHEMA = pa.schema(
    [
        ("id1", pa.string()),
        ("relation", pa.string()),
        ("id2", pa.string()),
    ]
)

RETROSHEET_BIOFILE_SCHEMA = pa.schema(
    [
        ("player_id", pa.string()),
        ("name_last", pa.string()),
        ("name_first", pa.string()),
        ("nickname", pa.string()),
        ("birth_date", pa.string()),
        ("birth_city", pa.string()),
        ("birth_state", pa.string()),
        ("birth_country", pa.string()),
        ("play_debut", pa.string()),
        ("play_lastgame", pa.string()),
        ("mgr_debut", pa.string()),
        ("mgr_lastgame", pa.string()),
        ("coach_debut", pa.string()),
        ("coach_lastgame", pa.string()),
        ("ump_debut", pa.string()),
        ("ump_lastgame", pa.string()),
        ("death_date", pa.string()),
        ("death_city", pa.string()),
        ("death_state", pa.string()),
        ("death_country", pa.string()),
        ("bats", pa.string()),
        ("throws", pa.string()),
        ("height", pa.string()),
        ("weight", pa.string()),
        ("cemetery", pa.string()),
        ("ceme_city", pa.string()),
        ("ceme_state", pa.string()),
        ("ceme_country", pa.string()),
        ("ceme_note", pa.string()),
        ("birth_name", pa.string()),
        ("name_chg", pa.string()),
        ("bat_chg", pa.string()),
        ("hof", pa.string()),
    ]
)
