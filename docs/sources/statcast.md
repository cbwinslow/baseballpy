# Statcast (Baseball Savant) Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** Major League Baseball Advanced Media (MLBAM) / Baseball Savant
- **Base Endpoint URL:** `https://baseballsavant.mlb.com`
- **Method:** `GET`
- **Response Format:** CSV (Comma-Separated Values, UTF-8 with optional BOM)
- **Rate Limit Policy:** Max 2.5 requests/second (token bucket enforced via `aiolimiter`)
- **Server Caps:** Upstream truncates pitch queries at ~25,000 rows. Queries spanning > 5–7 days frequently fail with HTTP 504 Gateway Timeout.
- **baseballpy Solution:** Automatic weekly date chunking (`split_date_range`), token bucket rate limiting, persistent HTTP/2 connection pooling, atomic `.part` writing, and manifest checkpointing.

---

## 1. Granular Pitch-Level Search Endpoint (`/statcast_search/csv`)

### Query Parameters
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

### Pitch-Level Schema Dictionary (94 Columns)
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
| `pitch_type` | `dictionary(int8, string)` | Yes | `FF` | Pitch classification (FF, SL, CH, CU, SI, FC, ST, SV, KN, FS) |
| `release_speed` | `float32()` | Yes | `97.4` | Pitch release speed in MPH |
| `release_pos_x` | `float32()` | Yes | `-1.82` | Horizontal release coordinate in feet |
| `release_pos_z` | `float32()` | Yes | `5.91` | Vertical release coordinate in feet |
| `events` | `dictionary(int8, string)` | Yes | `strikeout` | Outcome event if final pitch of plate appearance |
| `description` | `dictionary(int8, string)` | No | `swinging_strike` | Pitch result description |
| `spin_rate` | `float32()` | Yes | `2412.0` | Release spin rate in RPM |
| `launch_speed` | `float32()` | Yes | `104.2` | Batted ball exit velocity in MPH |
| `launch_angle` | `float32()` | Yes | `28.0` | Batted ball launch angle in degrees |
| `bat_speed` | `float32()` | Yes | `76.3` | Bat tracking: speed of sweet spot at impact (MPH) |
| `swing_length` | `float32()` | Yes | `7.1` | Bat tracking: distance traveled by sweet spot in swing (feet) |

---

## 2. Dedicated Analytical Leaderboards (`/leaderboard/*`)

All leaderboards export CSV when passed `&csv=true`.

### 1. Expected Statistics (`/leaderboard/expected_statistics`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/expected_statistics?type={batter|pitcher}&year={year}&min={min}&csv=true`
- **Columns:**
  - `player_id`: `int32()` — MLBAM player ID
  - `player_name`: `string()` — Player name
  - `year`: `int16()` — Season
  - `pa`: `int16()` — Plate appearances
  - `bip`: `int16()` — Balls in play
  - `ba`: `float32()` — Batting average
  - `est_ba`: `float32()` — Expected batting average (xBA)
  - `est_ba_diff`: `float32()` — BA vs xBA differential
  - `slg`: `float32()` — Slugging percentage
  - `est_slg`: `float32()` — Expected slugging percentage (xSLG)
  - `est_slg_diff`: `float32()` — SLG vs xSLG differential
  - `woba`: `float32()` — Weighted On-Base Average (wOBA)
  - `est_woba`: `float32()` — Expected wOBA (xwOBA)
  - `est_woba_diff`: `float32()` — wOBA vs xwOBA differential

### 2. Exit Velocity & Barrels (`/leaderboard/statcast`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/statcast?type={batter|pitcher}&year={year}&min={min}&csv=true`
- **Columns:**
  - `player_id`: `int32()`
  - `player_name`: `string()`
  - `attempts`: `int16()` — Batted ball events
  - `avg_hit_angle`: `float32()` — Average launch angle
  - `anglesweetspotpercent`: `float32()` — Sweet spot % (8°–32°)
  - `max_hit_speed`: `float32()` — Maximum exit velocity
  - `avg_hit_speed`: `float32()` — Average exit velocity
  - `ev50`: `float32()` — 50th percentile exit velocity
  - `fbld`: `float32()` — Fly ball / line drive EV
  - `gb`: `float32()` — Ground ball EV
  - `max_distance`: `int16()` — Maximum projected distance (ft)
  - `avg_distance`: `int16()` — Average projected distance (ft)
  - `avg_hr_distance`: `int16()` — Average home run distance (ft)
  - `ev95plus`: `int16()` — Hard hit balls (95+ MPH)
  - `ev95percent`: `float32()` — Hard hit percentage
  - `barrels`: `int16()` — Total barrels
  - `brl_percent`: `float32()` — Barrels per BBE %
  - `brl_pa`: `float32()` — Barrels per PA %

### 3. Sprint Speed & Running Splits (`/leaderboard/sprint_speed`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/sprint_speed?year={year}&min={min}&csv=true`
- **Columns:**
  - `player_id`: `int32()`
  - `player_name`: `string()`
  - `team_id`: `int32()`
  - `team`: `string()`
  - `position`: `string()`
  - `age`: `int8()`
  - `competitive_runs`: `int16()`
  - `bolts`: `int16()` — Runs >= 30 ft/sec
  - `hp_to_1b`: `float32()` — Home-to-first time (seconds)
  - `sprint_speed`: `float32()` — Top sprint speed (ft/sec)

### 4. Bat Tracking (`/leaderboard/bat-tracking`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/bat-tracking?year={year}&type=batter&min={min}&csv=true`
- **Columns:**
  - `id`: `int32()` — MLBAM player ID
  - `name`: `string()` — Player name
  - `swings_competitive`: `int16()`
  - `percent_swings_competitive`: `float32()`
  - `contact`: `int16()`
  - `avg_bat_speed`: `float32()` — Average bat speed (MPH)
  - `hard_swing_rate`: `float32()` — % of swings >= 75 MPH
  - `squared_up_per_bat_contact`: `float32()`
  - `squared_up_per_swing`: `float32()`
  - `blast_per_bat_contact`: `float32()`
  - `blast_per_swing`: `float32()`
  - `swing_length`: `float32()` — Swing length (ft)
  - `swords`: `int16()`
  - `batter_run_value`: `float32()`
  - `whiffs`: `int16()`
  - `whiff_per_swing`: `float32()`
  - `batted_ball_events`: `int16()`

### 5. Outs Above Average (`/leaderboard/outs_above_average`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/outs_above_average?type={type}&startYear={year}&endYear={year}&min={min}&csv=true`
- **Columns:**
  - `player_id`: `int32()`
  - `player_name`: `string()`
  - `display_team_name`: `string()`
  - `year`: `int16()`
  - `primary_pos_formatted`: `string()`
  - `fielding_runs_prevented`: `float32()`
  - `outs_above_average`: `float32()`
  - `outs_above_average_infront`: `float32()`
  - `outs_above_average_lateral_toward3bline`: `float32()`
  - `outs_above_average_lateral_toward1bline`: `float32()`
  - `outs_above_average_behind`: `float32()`
  - `outs_above_average_rhh`: `float32()`
  - `outs_above_average_lhh`: `float32()`
  - `actual_success_rate`: `float32()`
  - `adj_estimated_success_rate`: `float32()`
  - `diff_success_rate`: `float32()`

### 6. Arm Strength (`/leaderboard/arm-strength`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/arm-strength?year={year}&min={min}&csv=true`
- **Columns:**
  - `player_id`: `int32()`
  - `fielder_name`: `string()`
  - `team_name`: `string()`
  - `primary_position`: `int8()`
  - `total_throws`: `int16()`
  - `max_arm_strength`: `float32()` — Maximum throw velocity in MPH
  - `arm_overall`: `float32()` — Average top throw velocity

### 7. Catcher Pop Time (`/leaderboard/poptime`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/poptime?year={year}&min2b={min}&csv=true`
- **Columns:**
  - `entity_id`: `int32()`
  - `entity_name`: `string()`
  - `team_id`: `int32()`
  - `age`: `int8()`
  - `maxeff_arm_2b_3b_sba`: `float32()` — Arm strength on stolen base attempts
  - `exchange_2b_3b_sba`: `float32()` — Exchange time in seconds
  - `pop_2b_sba`: `float32()` — 2B pop time in seconds

### 8. Catcher Framing (`/leaderboard/catcher-framing`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/catcher-framing?year={year}&min={min}&csv=true`
- **Columns:**
  - `id`: `int32()`
  - `name`: `string()`
  - `pitches`: `int32()`
  - `rv_tot`: `float32()` — Runs Extra Strikes (framing run value)
  - `pct_tot`: `float32()` — Strike rate on called pitches in shadow zone

### 9. Pitch Arsenals (`/leaderboard/pitch-arsenals`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/pitch-arsenals?year={year}&min={min}&type=avg_speed&csv=true`
- **Columns:**
  - `pitcher`: `int32()` — MLBAM ID
  - `player_name`: `string()`
  - `ff_avg_speed`: `float32()` (Four-seam)
  - `si_avg_speed`: `float32()` (Sinker)
  - `fc_avg_speed`: `float32()` (Cutter)
  - `sl_avg_speed`: `float32()` (Slider)
  - `ch_avg_speed`: `float32()` (Changeup)
  - `cu_avg_speed`: `float32()` (Curveball)
  - `fs_avg_speed`: `float32()` (Splitter)
  - `kn_avg_speed`: `float32()` (Knuckleball)
  - `st_avg_speed`: `float32()` (Sweeper)
  - `sv_avg_speed`: `float32()` (Slurve)

### 10. Automated Ball-Strike (ABS) Challenges (`/leaderboard/abs-challenges`)
- **URL:** `https://baseballsavant.mlb.com/leaderboard/abs-challenges?challengeType={challengeType}&level=mlb&year={year}&csv=true`
- **Columns:**
  - `entity_name`: `string()`
  - `team_abbr`: `string()`
  - `year`: `int16()`
  - `n_challenges`: `int16()`
  - `n_overturns`: `int16()`
  - `n_confirms`: `int16()`
  - `rate_overturns`: `float32()`
  - `runs_above_average`: `float32()`

## Storage Layout (lake v2)
- Raw Savant CSV responses: `raw/statcast/pitches/season=YYYY/<start>_<end>[_filters].csv` (a window that hit the 25,000-row cap is bisected and only the complete sub-windows are stored).
- Typed pitches: `processed/statcast/pitches/season=YYYY/part-<start>_<end>[_filters].parquet` (DuckDB view `statcast_pitches`).
- Leaderboards: `raw/statcast/leaderboard_<name>/season=YYYY/<chunk>.csv` and `processed/statcast/leaderboard_<name>/season=YYYY/part-<chunk>.parquet` (view `statcast_leaderboard_<name>`); they never share a directory with pitches.
