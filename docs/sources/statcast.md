# Statcast (Baseball Savant) Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** Major League Baseball Advanced Media (MLBAM) / Baseball Savant
- **Base Endpoint URL:** `https://baseballsavant.mlb.com/statcast_search/csv`
- **Method:** `GET`
- **Response Format:** CSV (Comma-Separated Values)
- **Rate Limit Policy:** Max 2.5 requests/second (enforced via `aiolimiter`)
- **Server Caps:** Upstream truncates results at ~25,000 rows. Queries spanning > 5–7 days frequently fail with HTTP 504 Gateway Timeout.
- **baseballpy Solution:** Automatic weekly date chunking (`split_date_range`), token bucket rate limiting, and persistent HTTP/2 connection pooling.

---

## Query Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `all` | `string` | `"true"` | Enables returning all pitches matching criteria |
| `type` | `string` | `"details"` | Detailed pitch-level tracking records |
| `game_date_gt` | `string` | Required | Start date in `YYYY-MM-DD` format |
| `game_date_lt` | `string` | Required | End date in `YYYY-MM-DD` format |
| `player_type` | `string` | `"pitcher"` | Perspective: `"pitcher"` or `"batter"` |
| `pitchers_lookup[]` | `int` | Optional | MLBAM player ID filter for pitchers |
| `batters_lookup[]` | `int` | Optional | MLBAM player ID filter for batters |
| `team` | `string` | Optional | 3-letter team abbreviation filter |

---

## Exhaustive Column & Schema Dictionary

Every column below is captured, parsed, and ingested without arbitrary truncation per ADR 15.

| Column Name | PyArrow Physical Type | Nullable | Example Raw Value | Description |
| :--- | :--- | :---: | :--- | :--- |
| `game_pk` | `int32()` | No | `745789` | MLBAM official numeric Game ID (primary key) |
| `game_date` | `date32()` | No | `2024-04-05` | Official contest date |
| `game_year` | `int16()` | No | `2024` | Championship season year |
| `game_type` | `dictionary(int8, string)` | No | `R` | Game classification (`R` regular, `P` postseason, `S` spring) |
| `at_bat_number` | `int16()` | No | `1` | Sequential plate appearance index within game |
| `pitch_number` | `int16()` | No | `3` | Sequential pitch index within plate appearance |
| `pitcher` | `int32()` | No | `543037` | MLBAM ID of the pitcher |
| `batter` | `int32()` | No | `660271` | MLBAM ID of the batter |
| `player_name` | `string()` | No | `"Cole, Gerrit"` | Formatted name of pitcher (Last, First) |
| `home_team` | `dictionary(int8, string)` | No | `NYY` | Home team 3-letter abbreviation |
| `away_team` | `dictionary(int8, string)` | No | `LAD` | Away team 3-letter abbreviation |
| `inning` | `int8()` | No | `1` | Game inning number |
| `inning_topbot` | `dictionary(int8, string)` | No | `Top` | Half-inning indicator (`Top` or `Bot`) |
| `balls` | `int8()` | No | `1` | Ball count prior to pitch |
| `strikes` | `int8()` | No | `1` | Strike count prior to pitch |
| `outs_when_up` | `int8()` | No | `0` | Out count prior to pitch (0, 1, or 2) |
| `pitch_type` | `dictionary(int8, string)` | Yes | `FF` | 2-letter pitch classification code (`FF`, `SL`, `CH`, `CU`, `SI`, `ST`, `FC`, `FS`) |
| `pitch_name` | `dictionary(int8, string)` | Yes | `4-Seam Fastball` | Full descriptive pitch classification name |
| `release_speed` | `float32()` | Yes | `98.2` | Pitch velocity at release point (mph) |
| `effective_speed` | `float32()` | Yes | `97.9` | Perceived velocity adjusted for release extension (mph) |
| `release_spin_rate`| `float32()` | Yes | `2450.0` | Total pitch revolutions per minute (rpm) |
| `release_extension`| `float32()` | Yes | `6.7` | Distance from pitching rubber toward plate at release (ft) |
| `spin_axis` | `float32()` | Yes | `210.0` | 2D spin direction angle in degrees (0–360°) |
| `release_pos_x` | `float32()` | Yes | `-1.85` | Horizontal release position coordinate (ft, catcher perspective) |
| `release_pos_y` | `float32()` | Yes | `53.8` | Distance from home plate at release coordinate (ft) |
| `release_pos_z` | `float32()` | Yes | `6.12` | Vertical release position coordinate (ft above ground) |
| `arm_angle` | `float32()` | Yes | `38.5` | Pitcher arm slot angle at release in degrees |
| `zone` | `int8()` | Yes | `5` | 13-zone strike zone coordinate (1–9 in-zone, 11–14 chase) |
| `plate_x` | `float32()` | Yes | `0.12` | Horizontal location crossing front of plate (ft) |
| `plate_z` | `float32()` | Yes | `2.45` | Vertical location crossing front of plate (ft) |
| `sz_top` | `float32()` | Yes | `3.41` | Top of batter's individualized strike zone (ft) |
| `sz_bot` | `float32()` | Yes | `1.55` | Bottom of batter's individualized strike zone (ft) |
| `pfx_x` | `float32()` | Yes | `-0.65` | Horizontal pitch break induced by spin/movement (inches/ft) |
| `pfx_z` | `float32()` | Yes | `1.42` | Vertical pitch break induced by spin/movement (inches/ft) |
| `vx0` | `float32()` | Yes | `5.82` | Velocity vector X-component at y=50ft (ft/s) |
| `vy0` | `float32()` | Yes | `-142.6` | Velocity vector Y-component at y=50ft (ft/s) |
| `vz0` | `float32()` | Yes | `-5.12` | Velocity vector Z-component at y=50ft (ft/s) |
| `ax` | `float32()` | Yes | `-9.2` | Acceleration vector X-component (ft/s²) |
| `ay` | `float32()` | Yes | `31.4` | Acceleration vector Y-component (ft/s²) |
| `az` | `float32()` | Yes | `-15.8` | Acceleration vector Z-component (ft/s²) |
| `stand` | `dictionary(int8, string)` | No | `L` | Batter stance handedness (`L` or `R`) |
| `p_throws` | `dictionary(int8, string)` | No | `R` | Pitcher throwing handedness (`L` or `R`) |
| `type` | `dictionary(int8, string)` | No | `X` | Pitch outcome code: `S` (strike), `B` (ball), `X` (in play) |
| `events` | `dictionary(int8, string)` | Yes | `single` | Final plate appearance outcome event (null on non-terminal pitches) |
| `description` | `dictionary(int8, string)` | No | `hit_into_play`| Pitch result descriptor (`called_strike`, `swinging_strike`, `ball`, etc.) |
| `des` | `string()` | Yes | `"Shohei Ohtani singles..."` | Plain English narrative play description |
| `bb_type` | `dictionary(int8, string)` | Yes | `line_drive` | Batted ball trajectory: `ground_ball`, `line_drive`, `fly_ball`, `popup` |
| `hit_location` | `int8()` | Yes | `9` | Official scoring position of primary defensive fielder (1–9) |
| `launch_speed` | `float32()` | Yes | `105.4` | Exit velocity off bat (mph) |
| `launch_angle` | `float32()` | Yes | `14.0` | Vertical launch angle off bat (degrees) |
| `launch_speed_angle`| `int8()` | Yes | `4` | Batted ball classification bucket (1=Weak, 2=Topped, 3=Under, 4=Flare/Burner, 5=Solid, 6=Barrel) |
| `hit_distance_sc` | `float32()` | Yes | `340.0` | Projected or actual batted ball distance (ft) |
| `hc_x` | `float32()` | Yes | `165.2` | Hit chart landing coordinate X |
| `hc_y` | `float32()` | Yes | `120.5` | Hit chart landing coordinate Y |
| `bat_speed` | `float32()` | Yes | `76.5` | Bat sweet-spot velocity at contact (mph, 2024+) |
| `swing_length` | `float32()` | Yes | `7.1` | Total trajectory distance of bat head during swing (ft, 2024+) |
| `estimated_ba_using_speedangle` | `float32()` | Yes | `0.720` | Expected Batting Average (xBA) based on launch metrics |
| `estimated_woba_using_speedangle` | `float32()` | Yes | `0.850` | Expected wOBA (xwOBA) based on launch metrics |
| `woba_value` | `float32()` | Yes | `0.900` | Linear weight value assigned to plate appearance outcome |
| `woba_denom` | `float32()` | Yes | `1.0` | Denominator indicator for wOBA calculations |
| `babip_value` | `float32()` | Yes | `1.0` | BABIP indicator |
| `iso_value` | `float32()` | Yes | `0.0` | Isolated power value |
| `delta_home_win_exp`| `float32()` | Yes | `0.012` | Change in home team win probability resulting from pitch |
| `delta_run_exp` | `float32()` | Yes | `0.420` | Change in run expectancy resulting from pitch (RE24 delta) |
| `on_1b` | `int32()` | Yes | `660271` | MLBAM player ID of runner on 1st base (null if empty) |
| `on_2b` | `int32()` | Yes | `null` | MLBAM player ID of runner on 2nd base (null if empty) |
| `on_3b` | `int32()` | Yes | `null` | MLBAM player ID of runner on 3rd base (null if empty) |
| `home_score` | `int16()` | No | `0` | Home team score prior to pitch |
| `away_score` | `int16()` | No | `0` | Away team score prior to pitch |
| `bat_score` | `int16()` | No | `0` | Batting team score prior to pitch |
| `fld_score` | `int16()` | No | `0` | Fielding team score prior to pitch |
| `post_home_score` | `int16()` | No | `0` | Home team score after pitch conclusion |
| `post_away_score` | `int16()` | No | `0` | Away team score after pitch conclusion |
| `post_bat_score` | `int16()` | No | `0` | Batting team score after pitch conclusion |
| `post_fld_score` | `int16()` | No | `0` | Fielding team score after pitch conclusion |
| `fielder_2` | `int32()` | Yes | `663728` | MLBAM ID of Catcher |
| `fielder_3` | `int32()` | Yes | `518934` | MLBAM ID of First Baseman |
| `fielder_4` | `int32()` | Yes | `543760` | MLBAM ID of Second Baseman |
| `fielder_5` | `int32()` | Yes | `518692` | MLBAM ID of Third Baseman |
| `fielder_6` | `int32()` | Yes | `624413` | MLBAM ID of Shortstop |
| `fielder_7` | `int32()` | Yes | `642715` | MLBAM ID of Left Fielder |
| `fielder_8` | `int32()` | Yes | `592450` | MLBAM ID of Center Fielder |
| `fielder_9` | `int32()` | Yes | `650402` | MLBAM ID of Right Fielder |
| `pitcher_1` | `int32()` | Yes | `543037` | MLBAM ID of Pitcher (redundant field preserved) |
| `fielder_2_1` | `int32()` | Yes | `663728` | MLBAM ID of Catcher (redundant field preserved) |
| `if_fielding_alignment` | `dictionary(int8, string)` | Yes | `Standard` | Infield defensive shift alignment |
| `of_fielding_alignment` | `dictionary(int8, string)` | Yes | `Standard` | Outfield defensive shift alignment |
| `spin_dir` | `string()` | Yes | `null` | Deprecated spin direction text |
| `spin_rate_deprecated` | `string()` | Yes | `null` | Deprecated spin rate column |
| `break_angle_deprecated` | `string()` | Yes | `null` | Deprecated PITCHf/x break angle |
| `break_length_deprecated`| `string()` | Yes | `null` | Deprecated PITCHf/x break length |
| `tfs_deprecated` | `string()` | Yes | `null` | Deprecated time field |
| `tfs_zulu_deprecated` | `string()` | Yes | `null` | Deprecated UTC timestamp text |
| `umpire` | `string()` | Yes | `null` | Umpire metadata |
| `sv_id` | `string()` | Yes | `null` | Video/PITCHf/x clip identifier |
