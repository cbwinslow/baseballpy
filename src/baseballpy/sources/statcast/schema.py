"""Canonical PyArrow schema for Statcast (Baseball Savant) pitch tracking data.

Preserves ALL upstream fields per ADR 15, strongly-typed with optimized physical types.
"""

import pyarrow as pa

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
        ("release_speed", pa.float32()),
        ("effective_speed", pa.float32()),
        ("release_spin_rate", pa.float32()),
        ("release_extension", pa.float32()),
        ("spin_axis", pa.float32()),
        ("release_pos_x", pa.float32()),
        ("release_pos_y", pa.float32()),
        ("release_pos_z", pa.float32()),
        ("arm_angle", pa.float32()),
        # Plate Coordinates & Strike Zone
        ("zone", pa.int8()),
        ("plate_x", pa.float32()),
        ("plate_z", pa.float32()),
        ("sz_top", pa.float32()),
        ("sz_bot", pa.float32()),
        ("pfx_x", pa.float32()),
        ("pfx_z", pa.float32()),
        # Trajectory Physics
        ("vx0", pa.float32()),
        ("vy0", pa.float32()),
        ("vz0", pa.float32()),
        ("ax", pa.float32()),
        ("ay", pa.float32()),
        ("az", pa.float32()),
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
        ("launch_speed", pa.float32()),
        ("launch_angle", pa.float32()),
        ("launch_speed_angle", pa.int8()),
        ("hit_distance_sc", pa.float32()),
        ("hc_x", pa.float32()),
        ("hc_y", pa.float32()),
        # Bat Tracking (2024+)
        ("bat_speed", pa.float32()),
        ("swing_length", pa.float32()),
        # Expected & Value Metrics
        ("estimated_ba_using_speedangle", pa.float32()),
        ("estimated_woba_using_speedangle", pa.float32()),
        ("woba_value", pa.float32()),
        ("woba_denom", pa.float32()),
        ("babip_value", pa.float32()),
        ("iso_value", pa.float32()),
        ("delta_home_win_exp", pa.float32()),
        ("delta_run_exp", pa.float32()),
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
        ("pitcher_1", pa.int32()),
        ("fielder_2_1", pa.int32()),
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
    ]
)
