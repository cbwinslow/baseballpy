"""Canonical PyArrow schema for Statcast (Baseball Savant) pitch tracking data.

Preserves ALL upstream fields per ADR 15, strongly-typed with optimized physical types.
"""

from enum import StrEnum

import pyarrow as pa


class StatcastLeaderboard(StrEnum):
    """Supported Savant leaderboard variants (one member per registry slug; test-enforced)."""

    EXPECTED_STATISTICS_BATTER = "expected_statistics_batter"
    EXPECTED_STATISTICS_PITCHER = "expected_statistics_pitcher"
    EXIT_VELOCITY_BATTER = "exit_velocity_batter"
    EXIT_VELOCITY_PITCHER = "exit_velocity_pitcher"
    EXIT_VELOCITY_BATTER_TEAM = "exit_velocity_batter_team"
    EXIT_VELOCITY_PITCHER_TEAM = "exit_velocity_pitcher_team"
    SPRINT_SPEED = "sprint_speed"
    RUNNING_SPLITS = "running_splits"
    BASERUNNING = "baserunning"
    BASERUNNING_RUN_VALUE = "baserunning_run_value"
    BASESTEALING_RUN_VALUE = "basestealing_run_value"
    BAT_TRACKING = "bat_tracking"
    SWING_PATH_ATTACK_ANGLE = "swing_path_attack_angle"
    OUTS_ABOVE_AVERAGE = "outs_above_average"
    OUTFIELD_JUMP = "outfield_jump"
    ARM_STRENGTH = "arm_strength"
    POPTIME = "poptime"
    SWING_TIMING_MISS_DISTANCE_BATTER = "swing_timing_miss_distance_batter"
    SWING_TIMING_MISS_DISTANCE_PITCHER = "swing_timing_miss_distance_pitcher"
    YEAR_TO_YEAR_BATTER = "year_to_year_batter"
    YEAR_TO_YEAR_PITCHER = "year_to_year_pitcher"
    PITCHER_ARM_ANGLES = "pitcher_arm_angles"
    PITCHER_RUNNING_GAME = "pitcher_running_game"
    FIRST_BASE_RECEIVING = "first_base_receiving"
    OUTFIELD_DIRECTIONAL_OAA = "outfield_directional_oaa"
    CATCHER_STANCE = "catcher_stance"
    CATCHER_THROWING = "catcher_throwing"
    HOT_STOVE_BATTER = "hot_stove_batter"
    HOT_STOVE_PITCHER = "hot_stove_pitcher"
    CATCHER_FRAMING = "catcher_framing"
    CATCHER_BLOCKING = "catcher_blocking"
    PITCH_ARSENALS = "pitch_arsenals"
    PITCH_ARSENAL_STATS = "pitch_arsenal_stats"
    PITCH_MOVEMENT = "pitch_movement"
    PITCH_TEMPO = "pitch_tempo"
    SPIN_DIRECTION_PITCHES = "spin_direction_pitches"
    PERCENTILE_RANKINGS_BATTER = "percentile_rankings_batter"
    PERCENTILE_RANKINGS_PITCHER = "percentile_rankings_pitcher"
    HOME_RUNS = "home_runs"
    BATTED_BALL = "batted_ball"
    SWING_TAKE = "swing_take"
    ABS_CHALLENGES = "abs_challenges"
    PITCH_CLOCK = "pitch_clock"
    ACTIVE_SPIN = "active_spin"
    CATCH_PROBABILITY = "catch_probability"
    FIELDING_RUN_VALUE = "fielding_run_value"
    ROLLING = "rolling"
    PARK_FACTORS = "park_factors"


class PitchType(StrEnum):
    """Official MLBAM pitch type codes."""

    FOUR_SEAM = "FF"
    SLIDER = "SL"
    CHANGEUP = "CH"
    CURVEBALL = "CU"
    SINKER = "SI"
    CUTTER = "FC"
    SWEEPER = "ST"
    SPLITTER = "FS"
    SLURVE = "SV"
    KNUCKLEBALL = "KN"
    SLOW_CURVE = "CS"
    FORK = "FO"
    PITCH_OUT = "PO"
    INTENTIONAL_BALL = "IN"


class PlayerType(StrEnum):
    """Perspective filter for pitch-level searches."""

    BATTER = "batter"
    PITCHER = "pitcher"


# Dictionary-encoded types for high-frequency repeated categoricals
D_STRING = pa.dictionary(pa.int8(), pa.string())

STATCAST_SCHEMA = pa.schema(
    [
        # Identifiers
        ("game_pk", pa.int32()),
        ("game_date", pa.date32()),
        ("game_year", pa.int16()),
        ("game_type", D_STRING),
        ("at_bat_number", pa.int16()),
        ("pitch_number", pa.int16()),
        ("pitcher", pa.int32()),
        ("batter", pa.int32()),
        ("player_name", pa.string()),
        # Teams & Inning Context
        ("home_team", D_STRING),
        ("away_team", D_STRING),
        ("inning", pa.int8()),
        ("inning_topbot", D_STRING),
        ("balls", pa.int8()),
        ("strikes", pa.int8()),
        ("outs_when_up", pa.int8()),
        # Pitch Tracking & Velocity
        ("pitch_type", D_STRING),
        ("pitch_name", D_STRING),
        ("release_speed", pa.float64()),
        ("effective_speed", pa.float64()),
        ("release_spin_rate", pa.float64()),
        ("release_extension", pa.float64()),
        ("spin_axis", pa.float64()),
        ("release_pos_x", pa.float64()),
        ("release_pos_y", pa.float64()),
        ("release_pos_z", pa.float64()),
        ("arm_angle", pa.float64()),
        # Plate Coordinates & Strike Zone
        ("zone", pa.int8()),
        ("plate_x", pa.float64()),
        ("plate_z", pa.float64()),
        ("sz_top", pa.float64()),
        ("sz_bot", pa.float64()),
        ("pfx_x", pa.float64()),
        ("pfx_z", pa.float64()),
        # Trajectory Physics
        ("vx0", pa.float64()),
        ("vy0", pa.float64()),
        ("vz0", pa.float64()),
        ("ax", pa.float64()),
        ("ay", pa.float64()),
        ("az", pa.float64()),
        # Stance & Throws
        ("stand", D_STRING),
        ("p_throws", D_STRING),
        ("type", D_STRING),  # Pitch result code: 'S' (strike), 'B' (ball), 'X' (in play)
        # Play Outcomes & Batted Ball
        ("events", D_STRING),
        ("description", D_STRING),
        ("des", pa.string()),
        ("bb_type", D_STRING),
        ("hit_location", pa.int8()),
        ("launch_speed", pa.float64()),
        ("launch_angle", pa.float64()),
        ("launch_speed_angle", pa.int8()),
        ("hit_distance_sc", pa.float64()),
        ("hc_x", pa.float64()),
        ("hc_y", pa.float64()),
        # Bat Tracking (2024+)
        ("bat_speed", pa.float64()),
        ("swing_length", pa.float64()),
        # Expected & Value Metrics
        ("estimated_ba_using_speedangle", pa.float64()),
        ("estimated_woba_using_speedangle", pa.float64()),
        ("woba_value", pa.float64()),
        ("woba_denom", pa.float64()),
        ("babip_value", pa.float64()),
        ("iso_value", pa.float64()),
        ("delta_home_win_exp", pa.float64()),
        ("delta_run_exp", pa.float64()),
        # Base Runners
        ("on_1b", pa.int32()),
        ("on_2b", pa.int32()),
        ("on_3b", pa.int32()),
        # Scores
        ("home_score", pa.int16()),
        ("away_score", pa.int16()),
        ("bat_score", pa.int16()),
        ("fld_score", pa.int16()),
        ("post_home_score", pa.int16()),
        ("post_away_score", pa.int16()),
        ("post_bat_score", pa.int16()),
        ("post_fld_score", pa.int16()),
        # Defense & Fielders
        ("fielder_2", pa.int32()),
        ("fielder_3", pa.int32()),
        ("fielder_4", pa.int32()),
        ("fielder_5", pa.int32()),
        ("fielder_6", pa.int32()),
        ("fielder_7", pa.int32()),
        ("fielder_8", pa.int32()),
        ("fielder_9", pa.int32()),
        ("if_fielding_alignment", D_STRING),
        ("of_fielding_alignment", D_STRING),
        # Deprecated / Rare Metadata Fields (preserved per ADR 15)
        ("spin_dir", pa.string()),
        ("spin_rate_deprecated", pa.string()),
        ("break_angle_deprecated", pa.string()),
        ("break_length_deprecated", pa.string()),
        ("tfs_deprecated", pa.string()),
        ("tfs_zulu_deprecated", pa.string()),
        ("umpire", pa.string()),
        ("sv_id", pa.string()),
        # Win-probability, age and workload context (present in every era's export; live-verified)
        ("miss_distance", pa.float64()),
        ("estimated_slg_using_speedangle", pa.float64()),
        ("delta_pitcher_run_exp", pa.float64()),
        ("hyper_speed", pa.float64()),
        ("home_score_diff", pa.int16()),
        ("bat_score_diff", pa.int16()),
        ("home_win_exp", pa.float64()),
        ("bat_win_exp", pa.float64()),
        ("age_pit_legacy", pa.int16()),
        ("age_bat_legacy", pa.int16()),
        ("age_pit", pa.int16()),
        ("age_bat", pa.int16()),
        ("n_thruorder_pitcher", pa.int16()),
        ("n_priorpa_thisgame_player_at_bat", pa.int16()),
        ("pitcher_days_since_prev_game", pa.int16()),
        ("batter_days_since_prev_game", pa.int16()),
        ("pitcher_days_until_next_game", pa.int16()),
        ("batter_days_until_next_game", pa.int16()),
        ("api_break_z_with_gravity", pa.float64()),
        ("api_break_x_arm", pa.float64()),
        ("api_break_x_batter_in", pa.float64()),
        # Swing path (bat tracking, 2024+; NULL earlier)
        ("attack_angle", pa.float64()),
        ("attack_direction", pa.float64()),
        ("swing_path_tilt", pa.float64()),
        ("intercept_ball_minus_batter_pos_x_inches", pa.float64()),
        ("intercept_ball_minus_batter_pos_y_inches", pa.float64()),
        # Upstream columns added after this schema was written, as JSON (schema drift)
        ("_extras", pa.string()),
    ]
)
