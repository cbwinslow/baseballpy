# Statcast (Baseball Savant) Endpoint & Schema Catalog

Probed live on 2026-10-27 (`docs/savant_probe.json`, `scripts/gen_savant_schemas.py`); every claim below
is from that probe, not from memory.

## Upstream Overview
- **Provider:** Baseball Savant (MLBAM), `https://baseballsavant.mlb.com`, `GET`, UTF-8 CSV (BOM possible).
- **Rate limit:** 2.5 requests/second through the shared `HttpClient` (token bucket, retries, HTTP/2).
- **Server cap:** a pitch search returns at most 25,000 rows; `baseballpy` bisects any window that reaches it
  and raises `TruncatedResultError` if a single day still hits it (nothing is ever truncated silently).
- **Typing:** every dataset has a strict PyArrow schema generated from the live headers; columns that appear
  later land in a trailing `_extras` JSON column (and log `schema_drift` once); uncastable cells are quarantined.

---

## 1. Pitch-level search (`/statcast_search/csv`) - dataset `pitches`

| Item | Value |
|---|---|
| Request | `all=true&type=details&game_date_gt=<d>&game_date_lt=<d>` (+ optional filters below) |
| Seasons | 2008 - present: the export has **119 columns in every era** (2008 included); batted-ball and bat-tracking columns are simply empty before they existed (`launch_speed` is empty in 2008 and filled from 2015, `arm_angle` from 2020, `bat_speed` and the swing-path columns from 2024; checked on 2015-06-15, 2017-06-15, 2020-08-15, 2023-06-15, 2024-06-15, 2025-06-15) |
| Windows | 5-day chunks (`chunk_days`); spring training through the postseason, taken from the MLB calendar (`GET statsapi.mlb.com/api/v1/seasons?sportId=1&season=<Y>` -> `springStartDate`..`postSeasonEndDate`, cached in `cache/http/mlb-seasons`) |
| Partition / key | `season`; `(game_pk, at_bat_number, pitch_number)`; `ingest_season` reports surplus duplicate keys |
| Idempotency | one part per window (`part-<start>_<end>.parquet`), written atomically; a re-run only fetches missing windows, windows within 3 days of today, or when `refresh=True`; empty days are stored as empty parts |
| Spring training | `game_type` `S` rows are returned by the unfiltered search (3,692 pitches on 2024-03-10) |

**Filters (`StatcastQuery`)** - verified live: `hfGT=R|F|...` (game types `S R F D L W A`), `team=<abbr>`,
`player_type=batter|pitcher` (changes nothing: `all=true` returns every pitch). A filtered query returns rows but is
**never written to the lake** (it would duplicate pitches). `sportId`/`hfLevel` do not select minor leagues
(`sportId` is ignored, `hfLevel=11|` returned 0 rows), so minor-league Statcast is **unsupported** here.

**API:** `statcast_search(start, end, query=StatcastQuery(...))`, `ingest_season(year)`, `ingest_all(2008, end)`.

**Schema notes.** The old schema listed `pitcher_1` and `fielder_2_1`, which Savant never sends (always NULL);
they were removed. 26 columns that Savant does send were missing and had been stored with per-file inferred
types; they are now part of the schema (`age_pit`, `age_bat`, `home_win_exp`, `bat_win_exp`, `n_thruorder_pitcher`,
`attack_angle`, `swing_path_tilt`, `api_break_*`, ...). The full column dictionary is generated below.

## 1b. Game feed (`/gf?game_pk=<pk>`) - raw only

Responds 200 with a 2-3 MB JSON per game (`scoreboard`, pitch lists per team, `exit_velocity`, `boxscore`,
lineups). Stored on demand as `raw/statcast/game_feed/season=YYYY/<game_pk>.json` (`get_game_feed`); final games are
served from `raw/`. It is **not** bulk-ingested (about 7 GB per season) and no typed table is derived because the
pitch-level fields are already in `pitches`.

---

## 2. Leaderboards (`/leaderboard/<route>`)

Each *variant* is its own dataset (`statcast.leaderboard_<slug>`, view `statcast_leaderboard_<slug>`) with its own
schema. `min` is the widest qualifier the probe found (`0` = everyone; the default `q` returns qualified players
only). The season parameter differs per route (`year`, `season_start/season_end`, `seasonStart/seasonEnd`, `season`);
using the wrong one silently returns the current season for every year, which the probe detects by comparing
payload hashes across seasons. Requests that change `min` (or pass any other override) return a table but are not
persisted. `abs_challenges` ignores every season parameter, so it is a flat snapshot. `park_factors` has no CSV
download; its rows are the `var data = [...]` array embedded in the page (`lb_parse.html_json_to_csv`).

| Variant (`dataset`) | Route | Fixed params | Season param | `min` | First season | Granularity | Key |
|---|---|---|---|---|---|---|---|
| `leaderboard_expected_statistics_batter` | `/leaderboard/expected_statistics` | `type=batter` | `year` | `0` | 2015 | player-season | `player_id, year` |
| `leaderboard_expected_statistics_pitcher` | `/leaderboard/expected_statistics` | `type=pitcher` | `year` | `0` | 2015 | player-season | `player_id, year` |
| `leaderboard_exit_velocity_batter` | `/leaderboard/statcast` | `type=batter` | `year` | `0` | 2015 | player-season | `player_id` |
| `leaderboard_exit_velocity_pitcher` | `/leaderboard/statcast` | `type=pitcher` | `year` | `0` | 2015 | player-season | `player_id` |
| `leaderboard_exit_velocity_batter_team` | `/leaderboard/statcast` | `type=batter-team` | `year` | `0` | 2015 | team-season | `team_id` |
| `leaderboard_exit_velocity_pitcher_team` | `/leaderboard/statcast` | `type=pitcher-team` | `year` | `0` | 2015 | team-season | `team_id` |
| `leaderboard_sprint_speed` | `/leaderboard/sprint_speed` | - | `year` | `0` | 2015 | player-season | `player_id` |
| `leaderboard_running_splits` | `/leaderboard/running_splits` | - | `year` | `0` | 2015 | player-season-position | `player_id, team_id, position_name, bat_side` |
| `leaderboard_baserunning` | `/leaderboard/baserunning` | `type=Batter` | `season_snake` | `0` | 2016 | player-season | `entity_id, year` |
| `leaderboard_baserunning_run_value` | `/leaderboard/baserunning-run-value` | - | `season_snake` | `0` | 2016 | player-span | `player_id, start_year, end_year` |
| `leaderboard_basestealing_run_value` | `/leaderboard/basestealing-run-value` | - | `season_snake` | `0` | 2016 | player-span-base | `player_id, start_year, end_year, key_target_base` |
| `leaderboard_bat_tracking` | `/leaderboard/bat-tracking` | `type=batter` | `season_range` | `0` | 2023 | player-season | `id` |
| `leaderboard_swing_path_attack_angle` | `/leaderboard/bat-tracking/swing-path-attack-angle` | `type=batter` | `season_range` | `0` | 2023 | player-season-side | `id, side` |
| `leaderboard_outs_above_average` | `/leaderboard/outs_above_average` | `type=Fielder` | `year_span` | `0` | 2016 | player-position-season | `player_id, year, primary_pos_formatted` |
| `leaderboard_outfield_jump` | `/leaderboard/outfield_jump` | - | `year` | `0` | 2016 | player-season | `resp_fielder_id, year` |
| `leaderboard_arm_strength` | `/leaderboard/arm-strength` | `type=Fielder` | `year` | `0` | 2020 | player-season | `player_id` |
| `leaderboard_poptime` | `/leaderboard/poptime` | - | `year` | `0` | 2015 | player-season | `entity_id` |
| `leaderboard_catcher_framing` | `/leaderboard/catcher-framing` | - | `season_range` | `0` | 2008 | player-season | `id` |
| `leaderboard_catcher_blocking` | `/leaderboard/catcher-blocking` | - | `season_snake` | `0` | 2018 | player-span | `player_id, start_year` |
| `leaderboard_pitch_arsenals` | `/leaderboard/pitch-arsenals` | `type=avg_speed` | `year` | `0` | 2008 | player-season | `pitcher` |
| `leaderboard_pitch_arsenal_stats` | `/leaderboard/pitch-arsenal-stats` | `type=pitcher` | `year` | `0` | 2017 | player-season-pitch | `player_id, pitch_type` |
| `leaderboard_pitch_movement` | `/leaderboard/pitch-movement` | `pitch_type=ALL` | `year` | `0` | 2015 | player-season-pitch | `pitcher_id, pitch_type, pitch_hand` |
| `leaderboard_pitch_tempo` | `/leaderboard/pitch-tempo` | - | `season_snake` | `0` | 2012 | player-season | `entity_id` |
| `leaderboard_spin_direction_pitches` | `/leaderboard/spin-direction-pitches` | - | `year` | `0` | 2020 | player-season-pitch | `player_id, api_pitch_type` |
| `leaderboard_percentile_rankings_batter` | `/leaderboard/percentile-rankings` | `type=batter` | `year` | `None` | 2015 | player-season | `player_id, year` |
| `leaderboard_percentile_rankings_pitcher` | `/leaderboard/percentile-rankings` | `type=pitcher` | `year` | `None` | 2015 | player-season | `player_id, year` |
| `leaderboard_home_runs` | `/leaderboard/home-runs` | `type=batter` | `year` | `None` | 2016 | player-season-type | `player_id, year, type` |
| `leaderboard_batted_ball` | `/leaderboard/batted-ball` | `type=batter` | `year` | `1` | 2008 | player-season | `id, year` |
| `leaderboard_swing_take` | `/leaderboard/swing-take` | - | `year` | `0` | 2008 | player-season | `player_id, year` |
| `leaderboard_abs_challenges` | `/leaderboard/abs-challenges` | `type=batter` | `none` | `0` | snapshot (flat) | player-season-level | `entity_name, team_abbr, year, level` |
| `leaderboard_pitch_clock` | `/leaderboard/pitch-timer-infractions` | - | `season` | `None` | 2023 | player-season | `entity_id, year` |
| `leaderboard_park_factors` | `/leaderboard/statcast-park-factors` | `type=year`, `stat=index_wOBA`, `condition=All`, `rolling=3`, `parks=mlb` | `year` | `None` | 2008 | venue-season | `venue_id, key_year` |

### Routes probed and not ingested

| Route | Reason (probed 2026-10-27) |
|---|---|
| `/leaderboard/catch_probability` (`catch_probability`) | 2016-2020 return 30 anonymous rows (null player_id), empty from 2021 on |
| `/leaderboard/directional_outs_above_average` (`directional_outs_above_average`) | route answers 404 (probed 2026-10-27); directions are columns of outs_above_average |
| `/leaderboard/fielding-run-value` (`fielding_run_value`) | page answers 200 HTML and offers no CSV download or embedded data array |
| `/leaderboard/catcher_throwing` (`catcher_throwing`) | route answers 404; pop time/arm strength are in `poptime` |
| `/leaderboard/active-spin` (`active_spin`) | page answers HTML for csv=true; active spin is a column of spin_direction_pitches |
| `/leaderboard/year-to-year` (`year_to_year`) | route answers 404 (comparison tool, derivable from other leaderboards) |
| `/leaderboard/rolling` (`rolling`) | page is an interactive chart (1.3 MB HTML) with no CSV export |
| `/leaderboard/bat-speed` (`bat_speed`) | route answers 404; bat speed is a column of bat_tracking |


**API:** `get_leaderboard(slug_or_legacy_name, year, type=...)`, `StatcastLeaderboardExtractor.ingest_leaderboard(slug)`,
`ingest_all()`, `custom_leaderboard(year, selections=[...])` (ad hoc: `/leaderboard/custom`, types inferred, never persisted).
The `StatcastLeaderboard` enum has one member per supported slug (a test compares it with the registry).

## Storage Layout (lake v2)
- Raw: `raw/statcast/pitches/season=YYYY/<start>_<end>.csv`; `raw/statcast/leaderboard_<slug>/season=YYYY/<slug>_<year>.csv` (`.html` for `park_factors`); `raw/statcast/game_feed/season=YYYY/<pk>.json`. Each raw file records its sha256 and source URL in the dataset manifest.
- Typed: `processed/statcast/pitches/season=YYYY/part-<start>_<end>.parquet` (view `statcast_pitches`) and `processed/statcast/leaderboard_<slug>/season=YYYY/part-<slug>_<year>.parquet` (view `statcast_leaderboard_<slug>`). Leaderboards never share a directory with pitches.

## Dataset reference (generated)

<!-- BEGIN GENERATED:statcast.pitches -->
### Dataset: pitches

Pitch-level Statcast search results.

- **View:** `statcast_pitches`
- **Processed path:** `processed/statcast/pitches/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `at_bat_number`, `pitch_number`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `game_date` | date32[day] | yes | — |  |
| `game_year` | int16 | yes | — |  |
| `game_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `at_bat_number` | int16 | yes | — |  |
| `pitch_number` | int16 | yes | — |  |
| `pitcher` | int32 | yes | — |  |
| `batter` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `home_team` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `away_team` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `inning` | int8 | yes | — |  |
| `inning_topbot` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `balls` | int8 | yes | — |  |
| `strikes` | int8 | yes | — |  |
| `outs_when_up` | int8 | yes | — |  |
| `pitch_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `pitch_name` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `release_speed` | float | yes | — |  |
| `effective_speed` | float | yes | — |  |
| `release_spin_rate` | float | yes | — |  |
| `release_extension` | float | yes | — |  |
| `spin_axis` | float | yes | — |  |
| `release_pos_x` | float | yes | — |  |
| `release_pos_y` | float | yes | — |  |
| `release_pos_z` | float | yes | — |  |
| `arm_angle` | float | yes | — |  |
| `zone` | int8 | yes | — |  |
| `plate_x` | float | yes | — |  |
| `plate_z` | float | yes | — |  |
| `sz_top` | float | yes | — |  |
| `sz_bot` | float | yes | — |  |
| `pfx_x` | float | yes | — |  |
| `pfx_z` | float | yes | — |  |
| `vx0` | float | yes | — |  |
| `vy0` | float | yes | — |  |
| `vz0` | float | yes | — |  |
| `ax` | float | yes | — |  |
| `ay` | float | yes | — |  |
| `az` | float | yes | — |  |
| `stand` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `p_throws` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `type` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `events` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `description` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `des` | string | yes | — |  |
| `bb_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `hit_location` | int8 | yes | — |  |
| `launch_speed` | float | yes | — |  |
| `launch_angle` | float | yes | — |  |
| `launch_speed_angle` | int8 | yes | — |  |
| `hit_distance_sc` | float | yes | — |  |
| `hc_x` | float | yes | — |  |
| `hc_y` | float | yes | — |  |
| `bat_speed` | float | yes | — |  |
| `swing_length` | float | yes | — |  |
| `estimated_ba_using_speedangle` | float | yes | — |  |
| `estimated_woba_using_speedangle` | float | yes | — |  |
| `woba_value` | float | yes | — |  |
| `woba_denom` | float | yes | — |  |
| `babip_value` | float | yes | — |  |
| `iso_value` | float | yes | — |  |
| `delta_home_win_exp` | float | yes | — |  |
| `delta_run_exp` | float | yes | — |  |
| `on_1b` | int32 | yes | — |  |
| `on_2b` | int32 | yes | — |  |
| `on_3b` | int32 | yes | — |  |
| `home_score` | int16 | yes | — |  |
| `away_score` | int16 | yes | — |  |
| `bat_score` | int16 | yes | — |  |
| `fld_score` | int16 | yes | — |  |
| `post_home_score` | int16 | yes | — |  |
| `post_away_score` | int16 | yes | — |  |
| `post_bat_score` | int16 | yes | — |  |
| `post_fld_score` | int16 | yes | — |  |
| `fielder_2` | int32 | yes | — |  |
| `fielder_3` | int32 | yes | — |  |
| `fielder_4` | int32 | yes | — |  |
| `fielder_5` | int32 | yes | — |  |
| `fielder_6` | int32 | yes | — |  |
| `fielder_7` | int32 | yes | — |  |
| `fielder_8` | int32 | yes | — |  |
| `fielder_9` | int32 | yes | — |  |
| `if_fielding_alignment` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `of_fielding_alignment` | dictionary<values=string, indices=int8, ordered=0> | yes | — |  |
| `spin_dir` | string | yes | — |  |
| `spin_rate_deprecated` | string | yes | — |  |
| `break_angle_deprecated` | string | yes | — |  |
| `break_length_deprecated` | string | yes | — |  |
| `tfs_deprecated` | string | yes | — |  |
| `tfs_zulu_deprecated` | string | yes | — |  |
| `umpire` | string | yes | — |  |
| `sv_id` | string | yes | — |  |
| `miss_distance` | float | yes | — |  |
| `estimated_slg_using_speedangle` | float | yes | — |  |
| `delta_pitcher_run_exp` | float | yes | — |  |
| `hyper_speed` | float | yes | — |  |
| `home_score_diff` | int16 | yes | — |  |
| `bat_score_diff` | int16 | yes | — |  |
| `home_win_exp` | float | yes | — |  |
| `bat_win_exp` | float | yes | — |  |
| `age_pit_legacy` | int16 | yes | — |  |
| `age_bat_legacy` | int16 | yes | — |  |
| `age_pit` | int16 | yes | — |  |
| `age_bat` | int16 | yes | — |  |
| `n_thruorder_pitcher` | int16 | yes | — |  |
| `n_priorpa_thisgame_player_at_bat` | int16 | yes | — |  |
| `pitcher_days_since_prev_game` | int16 | yes | — |  |
| `batter_days_since_prev_game` | int16 | yes | — |  |
| `pitcher_days_until_next_game` | int16 | yes | — |  |
| `batter_days_until_next_game` | int16 | yes | — |  |
| `api_break_z_with_gravity` | float | yes | — |  |
| `api_break_x_arm` | float | yes | — |  |
| `api_break_x_batter_in` | float | yes | — |  |
| `attack_angle` | float | yes | — |  |
| `attack_direction` | float | yes | — |  |
| `swing_path_tilt` | float | yes | — |  |
| `intercept_ball_minus_batter_pos_x_inches` | float | yes | — |  |
| `intercept_ball_minus_batter_pos_y_inches` | float | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.pitches -->

<!-- BEGIN GENERATED:statcast.leaderboard_abs_challenges -->
### Dataset: leaderboard_abs_challenges

Automated ball-strike challenge system results per player (2025+; empty before).

- **View:** `statcast_leaderboard_abs_challenges`
- **Processed path:** `processed/statcast/leaderboard_abs_challenges/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `entity_name`, `team_abbr`, `year`, `level`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `entity_name` | string | yes | — |  |
| `team_abbr` | string | yes | — |  |
| `year` | int16 | yes | — |  |
| `level` | string | yes | — |  |
| `parent_org` | string | yes | — |  |
| `runs_above_average` | double | yes | — |  |
| `runs_gained` | double | yes | — |  |
| `runs_cost` | double | yes | — |  |
| `xruns_gained` | double | yes | — |  |
| `xruns_cost` | double | yes | — |  |
| `runs_gained_vs_exp` | double | yes | — |  |
| `runs_cost_vs_exp` | double | yes | — |  |
| `poss_runs` | double | yes | — |  |
| `runs_taken_percent` | double | yes | — |  |
| `runs_not_taken` | double | yes | — |  |
| `n_challenges` | int16 | yes | — |  |
| `n_overturns` | int16 | yes | — |  |
| `n_confirms` | int16 | yes | — |  |
| `rate_overturns` | double | yes | — |  |
| `exp_chal` | double | yes | — |  |
| `exp_chal_gained` | double | yes | — |  |
| `exp_chal_lost` | double | yes | — |  |
| `exp_rate_overturns` | double | yes | — |  |
| `net_chal_gained` | double | yes | — |  |
| `net_chal_lost` | double | yes | — |  |
| `poss_overturns` | int16 | yes | — |  |
| `overturns_taken_percent` | double | yes | — |  |
| `overturns_not_taken` | int16 | yes | — |  |
| `n_strikeouts_flip` | int16 | yes | — |  |
| `n_walks_flip` | int16 | yes | — |  |
| `runs_above_average_against` | double | yes | — |  |
| `runs_gained_against` | double | yes | — |  |
| `runs_cost_against` | double | yes | — |  |
| `xruns_gained_against` | double | yes | — |  |
| `xruns_cost_against` | double | yes | — |  |
| `runs_gained_vs_exp_against` | double | yes | — |  |
| `runs_cost_vs_exp_against` | double | yes | — |  |
| `poss_runs_against` | double | yes | — |  |
| `runs_taken_percent_against` | double | yes | — |  |
| `runs_not_taken_against` | double | yes | — |  |
| `n_challenges_against` | int16 | yes | — |  |
| `n_overturns_against` | int16 | yes | — |  |
| `n_confirms_against` | int16 | yes | — |  |
| `rate_overturns_against` | double | yes | — |  |
| `exp_chal_against` | double | yes | — |  |
| `exp_chal_gained_against` | double | yes | — |  |
| `exp_chal_lost_against` | double | yes | — |  |
| `exp_rate_overturns_against` | double | yes | — |  |
| `net_chal_gained_against` | double | yes | — |  |
| `net_chal_lost_against` | double | yes | — |  |
| `poss_overturns_against` | int16 | yes | — |  |
| `overturns_taken_percent_against` | double | yes | — |  |
| `overturns_not_taken_against` | int16 | yes | — |  |
| `n_strikeouts_flip_against` | int16 | yes | — |  |
| `n_walks_flip_against` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_abs_challenges -->

<!-- BEGIN GENERATED:statcast.leaderboard_arm_strength -->
### Dataset: leaderboard_arm_strength

Fielder arm strength (max and per-base average) per player-season.

- **View:** `statcast_leaderboard_arm_strength`
- **Processed path:** `processed/statcast/leaderboard_arm_strength/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `fielder_name` | string | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `team_name` | string | yes | — |  |
| `primary_position` | int16 | yes | — |  |
| `primary_position_name` | string | yes | — |  |
| `total_throws` | int16 | yes | — |  |
| `total_throws_1b` | int16 | yes | — |  |
| `total_throws_2b` | int16 | yes | — |  |
| `total_throws_3b` | int16 | yes | — |  |
| `total_throws_ss` | int16 | yes | — |  |
| `total_throws_lf` | int16 | yes | — |  |
| `total_throws_cf` | int16 | yes | — |  |
| `total_throws_rf` | int16 | yes | — |  |
| `total_throws_inf` | int16 | yes | — |  |
| `total_throws_of` | int16 | yes | — |  |
| `max_arm_strength` | double | yes | — |  |
| `arm_1b` | double | yes | — |  |
| `arm_2b` | double | yes | — |  |
| `arm_3b` | double | yes | — |  |
| `arm_ss` | double | yes | — |  |
| `arm_lf` | double | yes | — |  |
| `arm_cf` | double | yes | — |  |
| `arm_rf` | double | yes | — |  |
| `arm_inf` | double | yes | — |  |
| `arm_of` | double | yes | — |  |
| `arm_overall` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_arm_strength -->

<!-- BEGIN GENERATED:statcast.leaderboard_baserunning -->
### Dataset: leaderboard_baserunning

Extra-base-taken baserunning run value per runner-season.

- **View:** `statcast_leaderboard_baserunning`
- **Processed path:** `processed/statcast/leaderboard_baserunning/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `entity_name` | string | yes | — |  |
| `entity_id` | int32 | yes | — |  |
| `team_name` | string | yes | — |  |
| `year` | int16 | yes | — |  |
| `runner_runs` | double | yes | — |  |
| `fielder_runs` | double | yes | — |  |
| `runner_runs_advances` | double | yes | — |  |
| `runner_runs_thrown_out` | double | yes | — |  |
| `runner_runs_hold` | double | yes | — |  |
| `fielder_runs_advances` | double | yes | — |  |
| `fielder_runs_thrown_out` | double | yes | — |  |
| `fielder_runs_hold` | double | yes | — |  |
| `n_opp_xb` | int16 | yes | — |  |
| `n_att_xb` | int16 | yes | — |  |
| `rate_att_xb` | double | yes | — |  |
| `est_rate_att_generic_runner` | double | yes | — |  |
| `est_rate_att_generic_fielder` | double | yes | — |  |
| `n_out` | int16 | yes | — |  |
| `n_safe` | int16 | yes | — |  |
| `rate_safe` | double | yes | — |  |
| `rate_safe_per_attempt` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_baserunning -->

<!-- BEGIN GENERATED:statcast.leaderboard_baserunning_run_value -->
### Dataset: leaderboard_baserunning_run_value

Baserunning run value breakdown (extra bases, steal-of-base, swipe/snipe/freeze).

- **View:** `statcast_leaderboard_baserunning_run_value`
- **Processed path:** `processed/statcast/leaderboard_baserunning_run_value/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `start_year`, `end_year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | int32 | yes | — |  |
| `entity_name` | string | yes | — |  |
| `team_name` | string | yes | — |  |
| `start_year` | int16 | yes | — |  |
| `end_year` | int16 | yes | — |  |
| `runner_runs_tot` | double | yes | — |  |
| `runner_runs_xb` | double | yes | `runner_runs_XB` |  |
| `runner_runs_sbx` | double | yes | `runner_runs_SBX` |  |
| `n_runner_moved` | int16 | yes | `N_runner_moved` |  |
| `runner_runs_xb_swipe` | double | yes | `runner_runs_XB_swipe` |  |
| `runner_runs_xb_snipe` | double | yes | `runner_runs_XB_snipe` |  |
| `runner_runs_xb_freeze` | double | yes | `runner_runs_XB_freeze` |  |
| `n_runner_moved_xb` | int16 | yes | `N_runner_moved_XB` |  |
| `runner_runs_sb2` | double | yes | `runner_runs_SB2` |  |
| `runner_runs_sb3` | double | yes | `runner_runs_SB3` |  |
| `simple_stolen_on_running_act_sb2` | double | yes | `simple_stolen_on_running_act_SB2` |  |
| `simple_stolen_on_running_act_sb3` | double | yes | `simple_stolen_on_running_act_SB3` |  |
| `n_runner_moved_sbx` | int16 | yes | `N_runner_moved_SBX` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_baserunning_run_value -->

<!-- BEGIN GENERATED:statcast.leaderboard_basestealing_run_value -->
### Dataset: leaderboard_basestealing_run_value

Base-stealing run value and lead metrics by target base.

- **View:** `statcast_leaderboard_basestealing_run_value`
- **Processed path:** `processed/statcast/leaderboard_basestealing_run_value/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `start_year`, `end_year`, `key_target_base`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `team_name` | string | yes | — |  |
| `start_year` | int16 | yes | — |  |
| `end_year` | int16 | yes | — |  |
| `key_target_base` | string | yes | — |  |
| `runs_stolen_on_running_act` | double | yes | — |  |
| `n_init` | int16 | yes | — |  |
| `rate_sbx` | double | yes | — |  |
| `n_sb` | int16 | yes | — |  |
| `n_cs` | int16 | yes | — |  |
| `n_pk` | int16 | yes | — |  |
| `n_bk` | int16 | yes | — |  |
| `n_fb` | int16 | yes | — |  |
| `n_plus` | int16 | yes | — |  |
| `n_minus` | int16 | yes | — |  |
| `net_act_plus` | double | yes | — |  |
| `net_act_minus` | double | yes | — |  |
| `r_primary_lead` | double | yes | — |  |
| `r_secondary_lead` | double | yes | — |  |
| `r_sec_minus_prim_lead` | double | yes | — |  |
| `r_primary_lead_sbx` | double | yes | — |  |
| `r_secondary_lead_sbx` | double | yes | — |  |
| `r_sec_minus_prim_lead_sbx` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_basestealing_run_value -->

<!-- BEGIN GENERATED:statcast.leaderboard_bat_tracking -->
### Dataset: leaderboard_bat_tracking

Bat speed, swing length, squared-up and blast rates per batter-season (2023+).

- **View:** `statcast_leaderboard_bat_tracking`
- **Processed path:** `processed/statcast/leaderboard_bat_tracking/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `swings_competitive` | int16 | yes | — |  |
| `percent_swings_competitive` | double | yes | — |  |
| `contact` | int16 | yes | — |  |
| `avg_bat_speed` | double | yes | — |  |
| `hard_swing_rate` | double | yes | — |  |
| `squared_up_per_bat_contact` | double | yes | — |  |
| `squared_up_per_swing` | double | yes | — |  |
| `blast_per_bat_contact` | double | yes | — |  |
| `blast_per_swing` | double | yes | — |  |
| `swing_length` | double | yes | — |  |
| `swords` | int16 | yes | — |  |
| `batter_run_value` | double | yes | — |  |
| `whiffs` | int16 | yes | — |  |
| `whiff_per_swing` | double | yes | — |  |
| `batted_ball_events` | int16 | yes | — |  |
| `batted_ball_event_per_swing` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_bat_tracking -->

<!-- BEGIN GENERATED:statcast.leaderboard_batted_ball -->
### Dataset: leaderboard_batted_ball

Batted-ball profile (pull/straight/oppo, ground/line/fly rates) per batter-season.

- **View:** `statcast_leaderboard_batted_ball`
- **Processed path:** `processed/statcast/leaderboard_batted_ball/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `year` | int16 | yes | — |  |
| `bbe` | int16 | yes | — |  |
| `gb_rate` | double | yes | — |  |
| `air_rate` | double | yes | — |  |
| `fb_rate` | double | yes | — |  |
| `ld_rate` | double | yes | — |  |
| `pu_rate` | double | yes | — |  |
| `pull_rate` | double | yes | — |  |
| `straight_rate` | double | yes | — |  |
| `oppo_rate` | double | yes | — |  |
| `pull_gb_rate` | double | yes | — |  |
| `straight_gb_rate` | double | yes | — |  |
| `oppo_gb_rate` | double | yes | — |  |
| `pull_air_rate` | double | yes | — |  |
| `straight_air_rate` | double | yes | — |  |
| `oppo_air_rate` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_batted_ball -->

<!-- BEGIN GENERATED:statcast.leaderboard_catcher_blocking -->
### Dataset: leaderboard_catcher_blocking

Catcher blocking runs and blocks above average per catcher-span.

- **View:** `statcast_leaderboard_catcher_blocking`
- **Processed path:** `processed/statcast/leaderboard_catcher_blocking/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `start_year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `team_name` | string | yes | — |  |
| `start_year` | int16 | yes | — |  |
| `end_year` | string | yes | — |  |
| `pitches` | int16 | yes | — |  |
| `catcher_blocking_runs` | int16 | yes | — |  |
| `blocks_above_average` | int16 | yes | — |  |
| `n_pbwp` | int16 | yes | — |  |
| `x_pbwp` | double | yes | — |  |
| `blocks_above_average_per_game` | double | yes | — |  |
| `freq_pbwp_easy` | double | yes | — |  |
| `freq_pbwp_medium` | double | yes | — |  |
| `freq_pbwp_tough` | double | yes | — |  |
| `diff_pbwp_easy` | double | yes | — |  |
| `diff_pbwp_medium` | double | yes | — |  |
| `diff_pbwp_tough` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_catcher_blocking -->

<!-- BEGIN GENERATED:statcast.leaderboard_catcher_framing -->
### Dataset: leaderboard_catcher_framing

Catcher framing runs by zone per catcher-season.

- **View:** `statcast_leaderboard_catcher_framing`
- **Processed path:** `processed/statcast/leaderboard_catcher_framing/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `pitches` | int16 | yes | — |  |
| `rv_tot` | string | yes | — |  |
| `pct_tot` | double | yes | — |  |
| `rv_11` | int16 | yes | — |  |
| `pct_11` | double | yes | — |  |
| `rv_12` | int16 | yes | — |  |
| `pct_12` | double | yes | — |  |
| `rv_13` | int16 | yes | — |  |
| `pct_13` | double | yes | — |  |
| `rv_14` | int16 | yes | — |  |
| `pct_14` | double | yes | — |  |
| `rv_16` | int16 | yes | — |  |
| `pct_16` | double | yes | — |  |
| `rv_17` | int16 | yes | — |  |
| `pct_17` | double | yes | — |  |
| `rv_18` | int16 | yes | — |  |
| `pct_18` | double | yes | — |  |
| `rv_19` | int16 | yes | — |  |
| `pct_19` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_catcher_framing -->

<!-- BEGIN GENERATED:statcast.leaderboard_exit_velocity_batter -->
### Dataset: leaderboard_exit_velocity_batter

Exit velocity, launch angle and barrels per batter-season (batted-ball events).

- **View:** `statcast_leaderboard_exit_velocity_batter`
- **Processed path:** `processed/statcast/leaderboard_exit_velocity_batter/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `attempts` | int16 | yes | — |  |
| `avg_hit_angle` | double | yes | — |  |
| `anglesweetspotpercent` | double | yes | — |  |
| `max_hit_speed` | double | yes | — |  |
| `avg_hit_speed` | double | yes | — |  |
| `ev50` | double | yes | — |  |
| `fbld` | double | yes | — |  |
| `gb` | double | yes | — |  |
| `max_distance` | int16 | yes | — |  |
| `avg_distance` | int16 | yes | — |  |
| `avg_hr_distance` | int16 | yes | — |  |
| `ev95plus` | int16 | yes | — |  |
| `ev95percent` | double | yes | — |  |
| `barrels` | int16 | yes | — |  |
| `brl_percent` | double | yes | — |  |
| `brl_pa` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_exit_velocity_batter -->

<!-- BEGIN GENERATED:statcast.leaderboard_exit_velocity_batter_team -->
### Dataset: leaderboard_exit_velocity_batter_team

Exit velocity and barrels per batting team-season.

- **View:** `statcast_leaderboard_exit_velocity_batter_team`
- **Processed path:** `processed/statcast/leaderboard_exit_velocity_batter_team/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team` | string | yes | — |  |
| `team_id` | string | yes | — |  |
| `attempts` | int16 | yes | — |  |
| `avg_hit_angle` | double | yes | — |  |
| `anglesweetspotpercent` | double | yes | — |  |
| `max_hit_speed` | double | yes | — |  |
| `avg_hit_speed` | double | yes | — |  |
| `ev50` | double | yes | — |  |
| `fbld` | double | yes | — |  |
| `gb` | double | yes | — |  |
| `max_distance` | int16 | yes | — |  |
| `avg_distance` | int16 | yes | — |  |
| `avg_hr_distance` | int16 | yes | — |  |
| `ev95plus` | int16 | yes | — |  |
| `ev95percent` | double | yes | — |  |
| `barrels` | int16 | yes | — |  |
| `brl_percent` | double | yes | — |  |
| `brl_pa` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_exit_velocity_batter_team -->

<!-- BEGIN GENERATED:statcast.leaderboard_exit_velocity_pitcher -->
### Dataset: leaderboard_exit_velocity_pitcher

Exit velocity, launch angle and barrels allowed per pitcher-season.

- **View:** `statcast_leaderboard_exit_velocity_pitcher`
- **Processed path:** `processed/statcast/leaderboard_exit_velocity_pitcher/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `attempts` | int16 | yes | — |  |
| `avg_hit_angle` | double | yes | — |  |
| `anglesweetspotpercent` | double | yes | — |  |
| `max_hit_speed` | double | yes | — |  |
| `avg_hit_speed` | double | yes | — |  |
| `ev50` | double | yes | — |  |
| `fbld` | double | yes | — |  |
| `gb` | double | yes | — |  |
| `max_distance` | int16 | yes | — |  |
| `avg_distance` | int16 | yes | — |  |
| `avg_hr_distance` | int16 | yes | — |  |
| `ev95plus` | int16 | yes | — |  |
| `ev95percent` | double | yes | — |  |
| `barrels` | int16 | yes | — |  |
| `brl_percent` | double | yes | — |  |
| `brl_pa` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_exit_velocity_pitcher -->

<!-- BEGIN GENERATED:statcast.leaderboard_exit_velocity_pitcher_team -->
### Dataset: leaderboard_exit_velocity_pitcher_team

Exit velocity and barrels allowed per pitching team-season.

- **View:** `statcast_leaderboard_exit_velocity_pitcher_team`
- **Processed path:** `processed/statcast/leaderboard_exit_velocity_pitcher_team/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team` | string | yes | — |  |
| `team_id` | string | yes | — |  |
| `attempts` | int16 | yes | — |  |
| `avg_hit_angle` | double | yes | — |  |
| `anglesweetspotpercent` | double | yes | — |  |
| `max_hit_speed` | double | yes | — |  |
| `avg_hit_speed` | double | yes | — |  |
| `ev50` | double | yes | — |  |
| `fbld` | double | yes | — |  |
| `gb` | double | yes | — |  |
| `max_distance` | int16 | yes | — |  |
| `avg_distance` | int16 | yes | — |  |
| `avg_hr_distance` | int16 | yes | — |  |
| `ev95plus` | int16 | yes | — |  |
| `ev95percent` | double | yes | — |  |
| `barrels` | int16 | yes | — |  |
| `brl_percent` | double | yes | — |  |
| `brl_pa` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_exit_velocity_pitcher_team -->

<!-- BEGIN GENERATED:statcast.leaderboard_expected_statistics_batter -->
### Dataset: leaderboard_expected_statistics_batter

Expected stats (xBA, xSLG, xwOBA) per batter-season.

- **View:** `statcast_leaderboard_expected_statistics_batter`
- **Processed path:** `processed/statcast/leaderboard_expected_statistics_batter/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `year` | int16 | yes | — |  |
| `pa` | int16 | yes | — |  |
| `bip` | int16 | yes | — |  |
| `ba` | double | yes | — |  |
| `est_ba` | double | yes | — |  |
| `est_ba_minus_ba_diff` | double | yes | — |  |
| `slg` | double | yes | — |  |
| `est_slg` | double | yes | — |  |
| `est_slg_minus_slg_diff` | double | yes | — |  |
| `woba` | double | yes | — |  |
| `est_woba` | double | yes | — |  |
| `est_woba_minus_woba_diff` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_expected_statistics_batter -->

<!-- BEGIN GENERATED:statcast.leaderboard_expected_statistics_pitcher -->
### Dataset: leaderboard_expected_statistics_pitcher

Expected stats (xBA, xSLG, xwOBA, xERA) per pitcher-season.

- **View:** `statcast_leaderboard_expected_statistics_pitcher`
- **Processed path:** `processed/statcast/leaderboard_expected_statistics_pitcher/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `year` | int16 | yes | — |  |
| `pa` | int16 | yes | — |  |
| `bip` | int16 | yes | — |  |
| `ba` | double | yes | — |  |
| `est_ba` | double | yes | — |  |
| `est_ba_minus_ba_diff` | double | yes | — |  |
| `slg` | double | yes | — |  |
| `est_slg` | double | yes | — |  |
| `est_slg_minus_slg_diff` | double | yes | — |  |
| `woba` | double | yes | — |  |
| `est_woba` | double | yes | — |  |
| `est_woba_minus_woba_diff` | double | yes | — |  |
| `era` | double | yes | — |  |
| `xera` | double | yes | — |  |
| `era_minus_xera_diff` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_expected_statistics_pitcher -->

<!-- BEGIN GENERATED:statcast.leaderboard_home_runs -->
### Dataset: leaderboard_home_runs

Home run tracking (no-doubters, expected home runs) per player-season.

- **View:** `statcast_leaderboard_home_runs`
- **Processed path:** `processed/statcast/leaderboard_home_runs/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`, `type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player` | string | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `team_abbrev` | string | yes | — |  |
| `year` | int16 | yes | — |  |
| `type` | string | yes | — |  |
| `avg_hr_trot` | double | yes | — |  |
| `doubters` | int16 | yes | — |  |
| `mostly_gone` | int16 | yes | — |  |
| `no_doubters` | int16 | yes | — |  |
| `no_doubter_per` | double | yes | — |  |
| `hr_total` | int16 | yes | — |  |
| `xhr` | double | yes | — |  |
| `xhr_diff` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_home_runs -->

<!-- BEGIN GENERATED:statcast.leaderboard_outfield_jump -->
### Dataset: leaderboard_outfield_jump

Outfielder jump (reaction, burst and routing distance) per fielder-season.

- **View:** `statcast_leaderboard_outfield_jump`
- **Processed path:** `processed/statcast/leaderboard_outfield_jump/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `resp_fielder_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `resp_fielder_id` | int32 | yes | — |  |
| `year` | int16 | yes | — |  |
| `outs_above_average` | int16 | yes | — |  |
| `outs_per_play` | double | yes | — |  |
| `rel_league_burst_distance` | double | yes | — |  |
| `rel_league_reaction_distance` | double | yes | — |  |
| `rel_league_routing_distance` | double | yes | — |  |
| `rel_league_bootup_distance` | double | yes | — |  |
| `f_bootup_distance` | double | yes | — |  |
| `n` | int16 | yes | — |  |
| `n_outs` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_outfield_jump -->

<!-- BEGIN GENERATED:statcast.leaderboard_outs_above_average -->
### Dataset: leaderboard_outs_above_average

Outs Above Average (OAA) and fielding runs prevented per fielder-position-season.

- **View:** `statcast_leaderboard_outs_above_average`
- **Processed path:** `processed/statcast/leaderboard_outs_above_average/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`, `primary_pos_formatted`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `display_team_name` | string | yes | — |  |
| `year` | int16 | yes | — |  |
| `primary_pos_formatted` | string | yes | — |  |
| `fielding_runs_prevented` | int16 | yes | — |  |
| `outs_above_average` | int16 | yes | — |  |
| `outs_above_average_infront` | int16 | yes | — |  |
| `outs_above_average_lateral_toward3bline` | int16 | yes | — |  |
| `outs_above_average_lateral_toward1bline` | int16 | yes | — |  |
| `outs_above_average_behind` | int16 | yes | — |  |
| `outs_above_average_rhh` | int16 | yes | — |  |
| `outs_above_average_lhh` | int16 | yes | — |  |
| `actual_success_rate_formatted` | string | yes | — |  |
| `adj_estimated_success_rate_formatted` | string | yes | — |  |
| `diff_success_rate_formatted` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_outs_above_average -->

<!-- BEGIN GENERATED:statcast.leaderboard_park_factors -->
### Dataset: leaderboard_park_factors

Statcast park factor indices per venue and 3-year span (embedded JSON on the page).

- **View:** `statcast_leaderboard_park_factors`
- **Processed path:** `processed/statcast/leaderboard_park_factors/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `venue_id`, `key_year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `grouping_venue_conditions` | string | yes | — |  |
| `key_is_year_rolling` | int16 | yes | — |  |
| `key_num_years_rolling` | int16 | yes | — |  |
| `key_year` | int16 | yes | — |  |
| `is_sport_mlb` | int16 | yes | — |  |
| `is_sport_milb` | int16 | yes | — |  |
| `sport_id` | int16 | yes | — |  |
| `key_bat_side` | string | yes | — |  |
| `venue_id` | int16 | yes | — |  |
| `venue_name` | string | yes | — |  |
| `main_team_id` | int16 | yes | — |  |
| `name_display_club` | string | yes | — |  |
| `n_pa` | int32 | yes | — |  |
| `index_runs` | int16 | yes | — |  |
| `index_hardhit` | string | yes | — |  |
| `index_woba` | int16 | yes | — |  |
| `index_wobatto` | int16 | yes | — |  |
| `index_wobacon` | int16 | yes | — |  |
| `index_xwobacon` | string | yes | — |  |
| `index_xbacon` | string | yes | — |  |
| `index_obp` | int16 | yes | — |  |
| `index_so` | int16 | yes | — |  |
| `index_bb` | int16 | yes | — |  |
| `index_bacon` | int16 | yes | — |  |
| `index_hits` | int16 | yes | — |  |
| `index_1b` | int16 | yes | — |  |
| `index_2b` | int16 | yes | — |  |
| `index_3b` | int16 | yes | — |  |
| `index_hr` | int16 | yes | — |  |
| `year_range` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_park_factors -->

<!-- BEGIN GENERATED:statcast.leaderboard_percentile_rankings_batter -->
### Dataset: leaderboard_percentile_rankings_batter

Statcast percentile inputs per batter-season.

- **View:** `statcast_leaderboard_percentile_rankings_batter`
- **Processed path:** `processed/statcast/leaderboard_percentile_rankings_batter/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_name` | string | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `year` | int16 | yes | — |  |
| `xwoba` | int16 | yes | — |  |
| `xba` | int16 | yes | — |  |
| `xslg` | int16 | yes | — |  |
| `xiso` | int16 | yes | — |  |
| `xobp` | int16 | yes | — |  |
| `brl` | int16 | yes | — |  |
| `brl_percent` | int16 | yes | — |  |
| `exit_velocity` | int16 | yes | — |  |
| `max_ev` | int16 | yes | — |  |
| `hard_hit_percent` | int16 | yes | — |  |
| `k_percent` | int16 | yes | — |  |
| `bb_percent` | int16 | yes | — |  |
| `whiff_percent` | int16 | yes | — |  |
| `chase_percent` | int16 | yes | — |  |
| `arm_strength` | string | yes | — |  |
| `sprint_speed` | int16 | yes | — |  |
| `oaa` | string | yes | — |  |
| `bat_speed` | string | yes | — |  |
| `squared_up_rate` | string | yes | — |  |
| `swing_length` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_percentile_rankings_batter -->

<!-- BEGIN GENERATED:statcast.leaderboard_percentile_rankings_pitcher -->
### Dataset: leaderboard_percentile_rankings_pitcher

Statcast percentile inputs per pitcher-season.

- **View:** `statcast_leaderboard_percentile_rankings_pitcher`
- **Processed path:** `processed/statcast/leaderboard_percentile_rankings_pitcher/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_name` | string | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `year` | int16 | yes | — |  |
| `xwoba` | int16 | yes | — |  |
| `xba` | int16 | yes | — |  |
| `xslg` | int16 | yes | — |  |
| `xiso` | int16 | yes | — |  |
| `xobp` | int16 | yes | — |  |
| `brl` | int16 | yes | — |  |
| `brl_percent` | int16 | yes | — |  |
| `exit_velocity` | int16 | yes | — |  |
| `max_ev` | int16 | yes | — |  |
| `hard_hit_percent` | int16 | yes | — |  |
| `k_percent` | int16 | yes | — |  |
| `bb_percent` | int16 | yes | — |  |
| `whiff_percent` | int16 | yes | — |  |
| `chase_percent` | int16 | yes | — |  |
| `arm_strength` | string | yes | — |  |
| `xera` | int16 | yes | — |  |
| `fb_velocity` | int16 | yes | — |  |
| `fb_spin` | int16 | yes | — |  |
| `curve_spin` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_percentile_rankings_pitcher -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitch_arsenal_stats -->
### Dataset: leaderboard_pitch_arsenal_stats

Results (run value, BA, SLG, wOBA, whiff%) per pitcher and pitch type.

- **View:** `statcast_leaderboard_pitch_arsenal_stats`
- **Processed path:** `processed/statcast/leaderboard_pitch_arsenal_stats/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `pitch_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `team_name_alt` | string | yes | — |  |
| `pitch_type` | string | yes | — |  |
| `pitch_name` | string | yes | — |  |
| `run_value_per_100` | double | yes | — |  |
| `run_value` | int16 | yes | — |  |
| `pitches` | int16 | yes | — |  |
| `pitch_usage` | double | yes | — |  |
| `pa` | int16 | yes | — |  |
| `ba` | double | yes | — |  |
| `slg` | double | yes | — |  |
| `woba` | double | yes | — |  |
| `whiff_percent` | double | yes | — |  |
| `k_percent` | double | yes | — |  |
| `put_away` | double | yes | — |  |
| `est_ba` | double | yes | — |  |
| `est_slg` | double | yes | — |  |
| `est_woba` | double | yes | — |  |
| `hard_hit_percent` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_pitch_arsenal_stats -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitch_arsenals -->
### Dataset: leaderboard_pitch_arsenals

Average velocity per pitch type per pitcher-season (switch pitchers have one row per arm).

- **View:** `statcast_leaderboard_pitch_arsenals`
- **Processed path:** `processed/statcast/leaderboard_pitch_arsenals/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `pitcher`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `pitcher` | int32 | yes | — |  |
| `ff_avg_speed` | double | yes | — |  |
| `si_avg_speed` | double | yes | — |  |
| `fc_avg_speed` | double | yes | — |  |
| `sl_avg_speed` | double | yes | — |  |
| `ch_avg_speed` | double | yes | — |  |
| `cu_avg_speed` | double | yes | — |  |
| `fs_avg_speed` | double | yes | — |  |
| `kn_avg_speed` | double | yes | — |  |
| `st_avg_speed` | string | yes | — |  |
| `sv_avg_speed` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_pitch_arsenals -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitch_clock -->
### Dataset: leaderboard_pitch_clock

Pitch-timer violations by kind per player-season (2023+).

- **View:** `statcast_leaderboard_pitch_clock`
- **Processed path:** `processed/statcast/leaderboard_pitch_clock/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `entity_id` | int16 | yes | — |  |
| `entity_name` | string | yes | — |  |
| `year` | int16 | yes | — |  |
| `pitches` | int32 | yes | — |  |
| `all_violations` | int16 | yes | — |  |
| `pitcher_timer` | int16 | yes | — |  |
| `batter_timer` | int16 | yes | — |  |
| `batter_timeout` | int16 | yes | — |  |
| `catcher_timer` | int16 | yes | — |  |
| `defensive_shift` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_pitch_clock -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitch_movement -->
### Dataset: leaderboard_pitch_movement

Pitch movement (induced vertical and horizontal break) per pitcher and pitch type.

- **View:** `statcast_leaderboard_pitch_movement`
- **Processed path:** `processed/statcast/leaderboard_pitch_movement/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `pitcher_id`, `pitch_type`, `pitch_hand`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `year` | int16 | yes | — |  |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `pitcher_id` | int32 | yes | — |  |
| `team_name` | string | yes | — |  |
| `team_name_abbrev` | string | yes | — |  |
| `pitch_hand` | string | yes | — |  |
| `avg_speed` | double | yes | — |  |
| `pitches_thrown` | int16 | yes | — |  |
| `total_pitches` | int16 | yes | — |  |
| `pitches_per_game` | double | yes | — |  |
| `pitch_per` | double | yes | — |  |
| `pitch_type` | string | yes | — |  |
| `pitch_type_name` | string | yes | — |  |
| `pitcher_break_z` | double | yes | — |  |
| `league_break_z` | double | yes | — |  |
| `diff_z` | double | yes | — |  |
| `rise` | int16 | yes | — |  |
| `pitcher_break_z_induced` | double | yes | — |  |
| `pitcher_break_x` | double | yes | — |  |
| `league_break_x` | double | yes | — |  |
| `diff_x` | double | yes | — |  |
| `tail` | int32 | yes | — |  |
| `percent_rank_diff_z` | double | yes | — |  |
| `percent_rank_diff_x` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_pitch_movement -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitch_tempo -->
### Dataset: leaderboard_pitch_tempo

Time between pitches (median seconds by situation) per pitcher-season.

- **View:** `statcast_leaderboard_pitch_tempo`
- **Processed path:** `processed/statcast/leaderboard_pitch_tempo/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `entity_id` | int32 | yes | — |  |
| `entity_name` | string | yes | — |  |
| `entity_code` | string | yes | — |  |
| `team_id` | int16 | yes | — |  |
| `total_pitches` | int16 | yes | — |  |
| `total_pitches_2` | int16 | yes | `total_pitches__2` |  |
| `total_pitches_empty` | int16 | yes | — |  |
| `median_seconds_empty` | double | yes | — |  |
| `total_pitches_onbase` | int16 | yes | — |  |
| `median_seconds_empty_2` | double | yes | `median_seconds_empty__2` |  |
| `freq_hot` | double | yes | — |  |
| `freq_warm` | double | yes | — |  |
| `freq_cold` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_pitch_tempo -->

<!-- BEGIN GENERATED:statcast.leaderboard_poptime -->
### Dataset: leaderboard_poptime

Catcher pop time and arm strength on steal attempts per catcher-season.

- **View:** `statcast_leaderboard_poptime`
- **Processed path:** `processed/statcast/leaderboard_poptime/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `entity_name` | string | yes | — |  |
| `entity_id` | int32 | yes | — |  |
| `team_id` | int16 | yes | — |  |
| `age` | int16 | yes | — |  |
| `maxeff_arm_2b_3b_sba` | double | yes | — |  |
| `exchange_2b_3b_sba` | double | yes | — |  |
| `pop_2b_sba_count` | int16 | yes | — |  |
| `pop_2b_sba` | double | yes | — |  |
| `pop_2b_cs` | double | yes | — |  |
| `pop_2b_sb` | double | yes | — |  |
| `pop_3b_sba_count` | int16 | yes | — |  |
| `pop_3b_sba` | double | yes | — |  |
| `pop_3b_cs` | double | yes | — |  |
| `pop_3b_sb` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_poptime -->

<!-- BEGIN GENERATED:statcast.leaderboard_running_splits -->
### Dataset: leaderboard_running_splits

90-foot running splits (time since contact at each 5-foot mark) per player-season.

- **View:** `statcast_leaderboard_running_splits`
- **Processed path:** `processed/statcast/leaderboard_running_splits/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `position_name`, `bat_side`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `name_abbrev` | string | yes | — |  |
| `team_id` | int16 | yes | — |  |
| `position_name` | string | yes | — |  |
| `age` | int16 | yes | — |  |
| `bat_side` | string | yes | — |  |
| `seconds_since_hit_000` | double | yes | — |  |
| `seconds_since_hit_005` | double | yes | — |  |
| `seconds_since_hit_010` | double | yes | — |  |
| `seconds_since_hit_015` | double | yes | — |  |
| `seconds_since_hit_020` | double | yes | — |  |
| `seconds_since_hit_025` | double | yes | — |  |
| `seconds_since_hit_030` | double | yes | — |  |
| `seconds_since_hit_035` | double | yes | — |  |
| `seconds_since_hit_040` | double | yes | — |  |
| `seconds_since_hit_045` | double | yes | — |  |
| `seconds_since_hit_050` | double | yes | — |  |
| `seconds_since_hit_055` | double | yes | — |  |
| `seconds_since_hit_060` | double | yes | — |  |
| `seconds_since_hit_065` | double | yes | — |  |
| `seconds_since_hit_070` | double | yes | — |  |
| `seconds_since_hit_075` | double | yes | — |  |
| `seconds_since_hit_080` | double | yes | — |  |
| `seconds_since_hit_085` | double | yes | — |  |
| `seconds_since_hit_090` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_running_splits -->

<!-- BEGIN GENERATED:statcast.leaderboard_spin_direction_pitches -->
### Dataset: leaderboard_spin_direction_pitches

Measured vs inferred spin direction and active spin per pitcher and pitch type.

- **View:** `statcast_leaderboard_spin_direction_pitches`
- **Processed path:** `processed/statcast/leaderboard_spin_direction_pitches/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `api_pitch_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `year` | int16 | yes | — |  |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `pitch_hand` | string | yes | — |  |
| `api_pitch_type` | string | yes | — |  |
| `n_pitches` | int16 | yes | — |  |
| `release_speed` | double | yes | — |  |
| `spin_rate` | int16 | yes | — |  |
| `movement_inches` | double | yes | — |  |
| `alan_active_spin_pct` | double | yes | — |  |
| `active_spin` | double | yes | — |  |
| `hawkeye_measured` | double | yes | — |  |
| `movement_inferred` | double | yes | — |  |
| `api_pitch_name` | string | yes | — |  |
| `active_spin_formatted` | int16 | yes | — |  |
| `hawkeye_measured_clock_minutes` | int16 | yes | — |  |
| `movement_inferred_clock_minutes` | int16 | yes | — |  |
| `diff_measured_inferred` | double | yes | — |  |
| `diff2` | double | yes | — |  |
| `diff_measured_inferred_minutes` | int16 | yes | — |  |
| `hawkeye_measured_clock_hh` | int16 | yes | — |  |
| `hawkeye_measured_clock_mm` | int16 | yes | — |  |
| `movement_inferred_clock_hh` | int16 | yes | — |  |
| `movement_inferred_clock_mm` | int16 | yes | — |  |
| `diff_clock_hh` | int16 | yes | — |  |
| `diff_clock_mm` | int16 | yes | — |  |
| `hawkeye_measured_clock_label` | string | yes | — |  |
| `movement_inferred_clock_label` | string | yes | — |  |
| `diff_clock_label` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_spin_direction_pitches -->

<!-- BEGIN GENERATED:statcast.leaderboard_sprint_speed -->
### Dataset: leaderboard_sprint_speed

Sprint speed (ft/s on competitive runs) per player-season.

- **View:** `statcast_leaderboard_sprint_speed`
- **Processed path:** `processed/statcast/leaderboard_sprint_speed/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `team_id` | int16 | yes | — |  |
| `team` | string | yes | — |  |
| `position` | string | yes | — |  |
| `age` | int16 | yes | — |  |
| `competitive_runs` | int16 | yes | — |  |
| `bolts` | int16 | yes | — |  |
| `hp_to_1b` | double | yes | — |  |
| `sprint_speed` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_sprint_speed -->

<!-- BEGIN GENERATED:statcast.leaderboard_swing_path_attack_angle -->
### Dataset: leaderboard_swing_path_attack_angle

Swing path: attack angle, attack direction and swing tilt per batter-season (2023+).

- **View:** `statcast_leaderboard_swing_path_attack_angle`
- **Processed path:** `processed/statcast/leaderboard_swing_path_attack_angle/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `side`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `side` | string | yes | — |  |
| `avg_bat_speed` | double | yes | — |  |
| `swing_tilt` | double | yes | — |  |
| `attack_angle` | double | yes | — |  |
| `attack_direction` | double | yes | — |  |
| `ideal_attack_angle_rate` | double | yes | — |  |
| `avg_intercept_y_vs_plate` | double | yes | — |  |
| `avg_intercept_y_vs_batter` | double | yes | — |  |
| `avg_batter_y_position` | double | yes | — |  |
| `avg_batter_x_position` | double | yes | — |  |
| `competitive_swings` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_swing_path_attack_angle -->

<!-- BEGIN GENERATED:statcast.leaderboard_swing_take -->
### Dataset: leaderboard_swing_take

Swing/take run value by zone region per batter-season.

- **View:** `statcast_leaderboard_swing_take`
- **Processed path:** `processed/statcast/leaderboard_swing_take/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `year` | int16 | yes | — |  |
| `last_name_first_name` | string | yes | `last_name, first_name` |  |
| `player_id` | int32 | yes | — |  |
| `team_id` | int16 | yes | — |  |
| `pa` | int16 | yes | — |  |
| `pitches` | int16 | yes | — |  |
| `runs_all` | double | yes | — |  |
| `runs_heart` | double | yes | — |  |
| `runs_shadow` | double | yes | — |  |
| `runs_chase` | double | yes | — |  |
| `runs_waste` | double | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:statcast.leaderboard_swing_take -->
