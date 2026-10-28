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
| Windows | 5-day chunks (`chunk_days`) on a **fixed per-year grid** (block k = January 1 + 5k days, the last block of a year is clipped at December 31, `grid_windows`), so overlapping, nested or adjacent requests never store a pitch twice; `extract` fetches whole grid windows and returns exactly the requested `game_date` range. Season windows (spring training through the postseason) come from the MLB calendar (`GET statsapi.mlb.com/api/v1/seasons?sportId=1&season=<Y>` -> `springStartDate`..`postSeasonEndDate`, cached in `cache/http/mlb-seasons`) |
| Partition / key | `season`; `(game_pk, at_bat_number, pitch_number)`; `ingest_season` reports surplus duplicate keys |
| Idempotency | one part per window (`part-<start>_<end>.parquet`), written atomically; a re-run only fetches missing windows, windows within 3 days of today, or when `refresh=True`; empty days are stored as empty parts |
| Spring training | `game_type` `S` rows are returned by the unfiltered search (3,692 pitches on 2024-03-10) |

**Filters (`StatcastQuery`)** - verified live: `hfGT=R|F|...` (game types `S R F D L W A`), `team=<abbr>`,
`player_type=batter|pitcher` (changes nothing: `all=true` returns every pitch). A filtered query returns rows but is
**never written to the lake** (it would duplicate pitches).

**Minor leagues (`pitches_minors`).** `minors=true` returns the minor-league population with the same 119 columns (probed 2026-10-27: 6,042 pitches on 2024-06-15, home teams `ABQ, BUF, LOU, ...`); `hfLevel=<L>|` filters it only together with `minors=true` (`AAA|` 4,594 and `A|` 1,448 rows that day; `AA|`, `A+|`, `A-|`, `R|` returned 0). Data exists from 2021 (nothing in 2014-2020), so `ingest_all(minors=True)` starts there. `sportId`, `sport_id`, `level` and `hfMilb` are ignored and `hfLevel` without `minors=true` returns 0 rows (an earlier version of this page wrongly called minor-league pitches unreachable). The season window is the union of the MLB calendars of sports 11-14. Minor-league and MLB pitches are separate datasets (`statcast_pitches_minors`, `statcast_pitches`); a level-filtered query is returned but not persisted.

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
| `leaderboard_fielding_run_value` | `/leaderboard/fielding-run-value` | `gameType=Regular`, `type=fielder` | `season_range` | `None` | 2008 | player-season | `id, team_id` |
| `leaderboard_rolling` | `/leaderboard/rolling` | - | `none` | `None` | snapshot (flat) | player-window | `player_id, cat, cat_bin` |
| `leaderboard_active_spin` | `/leaderboard/active-spin` | - | `year` | `None` | 2020 | player-season | `entity_id, pitch_hand` |
| `leaderboard_catch_probability` | `/leaderboard/catch_probability` | - | `year` | `0` | 2016 | player-season | `player_id` |
| `leaderboard_park_factors` | `/leaderboard/statcast-park-factors` | `type=year`, `stat=index_wOBA`, `condition=All`, `rolling=3`, `parks=mlb` | `year` | `None` | 2008 | venue-season | `venue_id, key_year` |

### Routes probed and not ingested

| Route | Reason (probed 2026-10-27) |
|---|---|
| `/leaderboard/directional_outs_above_average` (`directional_outs_above_average`) | route answers 404 (probed 2026-10-27); directions are columns of outs_above_average |
| `/leaderboard/catcher_throwing` (`catcher_throwing`) | route answers 404; pop time/arm strength are in `poptime` |
| `/leaderboard/year-to-year` (`year_to_year`) | route answers 404 (comparison tool, derivable from other leaderboards) |
| `/leaderboard/bat-speed` (`bat_speed`) | route answers 404; bat speed is a column of bat_tracking |

**API:** `get_leaderboard(slug_or_legacy_name, year, type=...)`, `StatcastLeaderboardExtractor.ingest_leaderboard(slug)`,
`ingest_all()`, `custom_leaderboard(year, selections=[...])` (ad hoc: `/leaderboard/custom`, types inferred, never persisted).
The `StatcastLeaderboard` enum has one member per supported slug (a test compares it with the registry).

## Storage Layout (lake v2)
- Raw: `raw/statcast/pitches/season=YYYY/<start>_<end>.csv`; `raw/statcast/leaderboard_<slug>/season=YYYY/<slug>_<year>.csv` (`.html` for `park_factors`); `raw/statcast/game_feed/season=YYYY/<pk>.json`. Each raw file records its sha256 and source URL in the dataset manifest.
- Typed: `processed/statcast/pitches/season=YYYY/part-<start>_<end>.parquet` (view `statcast_pitches`) and `processed/statcast/leaderboard_<slug>/season=YYYY/part-<slug>_<year>.parquet` (view `statcast_leaderboard_<slug>`). Leaderboards never share a directory with pitches.

## Dataset reference (generated)

<!-- BEGIN GENERATED:statcast.description_sources -->
### Description sources

- `mlb_glossary_arm_strength`: https://www.mlb.com/glossary/statcast/arm-strength
- `mlb_glossary_attack_angle`: https://www.mlb.com/glossary/statcast/attack-angle
- `mlb_glossary_attack_direction`: https://www.mlb.com/glossary/statcast/attack-direction
- `mlb_glossary_barrel`: https://www.mlb.com/glossary/statcast/barrel
- `mlb_glossary_bolt`: https://www.mlb.com/glossary/statcast/bolt
- `mlb_glossary_expected_batting_average`: https://www.mlb.com/glossary/statcast/expected-batting-average
- `mlb_glossary_expected_era`: https://www.mlb.com/glossary/statcast/expected-era
- `mlb_glossary_expected_slugging_percentage`: https://www.mlb.com/glossary/statcast/expected-slugging-percentage
- `mlb_glossary_expected_woba`: https://www.mlb.com/glossary/statcast/expected-woba
- `mlb_glossary_hard_hit_rate`: https://www.mlb.com/glossary/statcast/hard-hit-rate
- `mlb_glossary_outs_above_average`: https://www.mlb.com/glossary/statcast/outs-above-average
- `mlb_glossary_spin_rate`: https://www.mlb.com/glossary/statcast/spin-rate
- `mlb_glossary_sprint_speed`: https://www.mlb.com/glossary/statcast/sprint-speed
- `mlb_glossary_squared_up`: https://www.mlb.com/glossary/statcast/squared-up
- `mlb_glossary_sweet_spot`: https://www.mlb.com/glossary/statcast/sweet-spot
- `mlb_glossary_swing_length`: https://www.mlb.com/glossary/statcast/swing-length
- `mlb_glossary_swing_path_tilt`: https://www.mlb.com/glossary/statcast/swing-path-tilt
- `savant_csv_docs`: https://baseballsavant.mlb.com/csv-docs

<!-- END GENERATED:statcast.description_sources -->

<!-- BEGIN GENERATED:statcast.pitches -->
### Dataset: pitches

Pitch-level Statcast search results.

- **View:** `statcast_pitches`
- **Processed path:** `processed/statcast/pitches/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `at_bat_number`, `pitch_number`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — | Unique Id for Game. (src: savant_csv_docs) |
| `game_date` | date32[day] | yes | — | Date of the Game. (src: savant_csv_docs) |
| `game_year` | int16 | yes | — | Year game took place. (src: savant_csv_docs) |
| `game_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Type of Game. E = Exhibition, S = Spring Training, R = Regular Season, F = Wild Card, D = Divisional Series, L = League Championship Series, W = World Series (src: savant_csv_docs) |
| `at_bat_number` | int16 | yes | — | Plate appearance number of the game. (src: savant_csv_docs) |
| `pitch_number` | int16 | yes | — | Total pitch number of the plate appearance. (src: savant_csv_docs) |
| `pitcher` | int32 | yes | — | MLB Player Id tied to the play event. (src: savant_csv_docs) |
| `batter` | int32 | yes | — | MLB Player Id tied to the play event. (src: savant_csv_docs) |
| `player_name` | string | yes | — | Player's name tied to the event of the search. (src: savant_csv_docs) |
| `home_team` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Abbreviation of home team. (src: savant_csv_docs) |
| `away_team` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Abbreviation of away team. (src: savant_csv_docs) |
| `inning` | int8 | yes | — | Pre-pitch inning number. (src: savant_csv_docs) |
| `inning_topbot` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Pre-pitch top or bottom of inning. (src: savant_csv_docs) |
| `balls` | int8 | yes | — | Pre-pitch number of balls in count. (src: savant_csv_docs) |
| `strikes` | int8 | yes | — | Pre-pitch number of strikes in count. (src: savant_csv_docs) |
| `outs_when_up` | int8 | yes | — | Pre-pitch number of outs. (src: savant_csv_docs) |
| `pitch_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | The type of pitch derived from Statcast. (src: savant_csv_docs) |
| `pitch_name` | dictionary<values=string, indices=int8, ordered=0> | yes | — | The name of the pitch derived from the Statcast Data. (src: savant_csv_docs) |
| `release_speed` | float | yes | — | Pitch velocity in MPH. Values from 2008-16 are via PitchFX, and adjusted to roughly out-of-hand release point. All velocities from 2017 and beyond are Statcast, which are reported out-of-hand. All velocities are thus on the same scale. (src: savant_csv_docs) |
| `effective_speed` | float | yes | — | Derived speed based on the the extension of the pitcher's release. (src: savant_csv_docs) |
| `release_spin_rate` | float | yes | — | TODO |
| `release_extension` | float | yes | — | Release extension of pitch in feet as tracked by Statcast. (src: savant_csv_docs) |
| `spin_axis` | float | yes | — | The Spin Axis in the 2D X-Z plane in degrees from 0 to 360, such that 180 represents a pure backspin fastball and 0 degrees represents a pure topspin (12-6) curveball (src: savant_csv_docs) |
| `release_pos_x` | float | yes | — | Horizontal Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_y` | float | yes | — | Release position of pitch measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_z` | float | yes | — | Vertical Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `arm_angle` | float | yes | — | The angle between a line parallel to the ground and a l line extending from the location of the pitcher's throwing shoulder and the location of the ball at the time of the pitch. (src: savant_csv_docs) |
| `zone` | int8 | yes | — | Zone location of the ball when it crosses the plate from the catcher's perspective. (src: savant_csv_docs) |
| `plate_x` | float | yes | — | Horizontal position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `plate_z` | float | yes | — | Vertical position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `sz_top` | float | yes | — | Top of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, top of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the top of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `sz_bot` | float | yes | — | Bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the bottom of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `pfx_x` | float | yes | — | Horizontal movement in feet from the catcher's perspective. (src: savant_csv_docs) |
| `pfx_z` | float | yes | — | Vertical movement in feet from the catcher's perpsective. (src: savant_csv_docs) |
| `vx0` | float | yes | — | The velocity of the pitch, in feet per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vy0` | float | yes | — | The velocity of the pitch, in feet per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vz0` | float | yes | — | TODO |
| `ax` | float | yes | — | The acceleration of the pitch, in feet per second per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `ay` | float | yes | — | The acceleration of the pitch, in feet per second per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `az` | float | yes | — | The acceleration of the pitch, in feet per second per second, in z-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `stand` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Side of the plate batter is standing. (src: savant_csv_docs) |
| `p_throws` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Hand pitcher throws with. (src: savant_csv_docs) |
| `type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Short hand of pitch result. B = ball, S = strike, X = in play. (src: savant_csv_docs) |
| `events` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Event of the resulting Plate Appearance. (src: savant_csv_docs) |
| `description` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Description of the resulting pitch. (src: savant_csv_docs) |
| `des` | string | yes | — | Plate appearance description from game day. (src: savant_csv_docs) |
| `bb_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Batted ball type, ground_ball, line_drive, fly_ball, popup. (src: savant_csv_docs) |
| `hit_location` | int8 | yes | — | Position of first fielder to touch the ball. (src: savant_csv_docs) |
| `launch_speed` | float | yes | — | Exit velocity of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_angle` | float | yes | — | Launch angle of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_speed_angle` | int8 | yes | — | Launch speed/angle zone based on launch angle and exit velocity. Weak Topped Under Flare/Burner Solid Contact Barrel (src: savant_csv_docs) |
| `hit_distance_sc` | float | yes | — | TODO |
| `hc_x` | float | yes | — | Hit coordinate X of batted ball. (src: savant_csv_docs) |
| `hc_y` | float | yes | — | Hit coordinate Y of batted ball. (src: savant_csv_docs) |
| `bat_speed` | float | yes | — | TODO |
| `swing_length` | float | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `estimated_ba_using_speedangle` | float | yes | — | Estimated Batting Avg based on launch angle and exit velocity. (src: savant_csv_docs) |
| `estimated_woba_using_speedangle` | float | yes | — | Estimated wOBA based on launch angle and exit velocity. (src: savant_csv_docs) |
| `woba_value` | float | yes | — | wOBA value based on result of play. (src: savant_csv_docs) |
| `woba_denom` | float | yes | — | wOBA denominator based on result of play. (src: savant_csv_docs) |
| `babip_value` | float | yes | — | BABIP value based on result of play. (src: savant_csv_docs) |
| `iso_value` | float | yes | — | ISO value based on result of play. (src: savant_csv_docs) |
| `delta_home_win_exp` | float | yes | — | The change in Win Expectancy before the Plate Appearance and after the Plate Appearance (src: savant_csv_docs) |
| `delta_run_exp` | float | yes | — | The change in Run Expectancy before the Pitch and after the Pitch (src: savant_csv_docs) |
| `on_1b` | int32 | yes | — | Pre-pitch MLB Player Id of Runner on 1B. (src: savant_csv_docs) |
| `on_2b` | int32 | yes | — | Pre-pitch MLB Player Id of Runner on 2B. (src: savant_csv_docs) |
| `on_3b` | int32 | yes | — | Pre-pitch MLB Player Id of Runner on 3B. (src: savant_csv_docs) |
| `home_score` | int16 | yes | — | Pre-pitch home score (src: savant_csv_docs) |
| `away_score` | int16 | yes | — | Pre-pitch away score (src: savant_csv_docs) |
| `bat_score` | int16 | yes | — | Pre-pitch bat team score (src: savant_csv_docs) |
| `fld_score` | int16 | yes | — | Pre-pitch field team score (src: savant_csv_docs) |
| `post_home_score` | int16 | yes | — | Post-pitch home score (src: savant_csv_docs) |
| `post_away_score` | int16 | yes | — | Post-pitch away score (src: savant_csv_docs) |
| `post_bat_score` | int16 | yes | — | Post-pitch bat team score (src: savant_csv_docs) |
| `post_fld_score` | int16 | yes | — | TODO |
| `fielder_2` | int32 | yes | — | Pre-pitch MLB Player Id of Catcher. (src: savant_csv_docs) |
| `fielder_3` | int32 | yes | — | MLB Player Id for 1B. (src: savant_csv_docs) |
| `fielder_4` | int32 | yes | — | MLB Player Id for 2B. (src: savant_csv_docs) |
| `fielder_5` | int32 | yes | — | MLB Player Id for 3B. (src: savant_csv_docs) |
| `fielder_6` | int32 | yes | — | MLB Player Id for SS. (src: savant_csv_docs) |
| `fielder_7` | int32 | yes | — | MLB Player Id for LF. (src: savant_csv_docs) |
| `fielder_8` | int32 | yes | — | MLB Player Id for CF. (src: savant_csv_docs) |
| `fielder_9` | int32 | yes | — | MLB Player Id for RF. (src: savant_csv_docs) |
| `if_fielding_alignment` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Infield fielding alignment at the time of the pitch. (src: savant_csv_docs) |
| `of_fielding_alignment` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Outfield fielding alignment at the time of the pitch. (src: savant_csv_docs) |
| `spin_dir` | string | yes | — | * Deprecated field from the old tracking system. (src: savant_csv_docs) |
| `spin_rate_deprecated` | string | yes | — | * Deprecated field from the old tracking system. Replaced by release_spin (src: savant_csv_docs) |
| `break_angle_deprecated` | string | yes | — | * Deprecated field from the old tracking system. (src: savant_csv_docs) |
| `break_length_deprecated` | string | yes | — | * Deprecated field from the old tracking system. (src: savant_csv_docs) |
| `tfs_deprecated` | string | yes | — | * Deprecated field from old tracking system. (src: savant_csv_docs) |
| `tfs_zulu_deprecated` | string | yes | — | * Deprecated field from old tracking system. (src: savant_csv_docs) |
| `umpire` | string | yes | — | * Deprecated field from old tracking system. (src: savant_csv_docs) |
| `sv_id` | string | yes | — | Non-unique Id of play event per game. (src: savant_csv_docs) |
| `miss_distance` | float | yes | — | TODO |
| `estimated_slg_using_speedangle` | float | yes | — | TODO |
| `delta_pitcher_run_exp` | float | yes | — | TODO |
| `hyper_speed` | float | yes | — | Savant display name: Adjusted EV. Adjusted Exit Velocity sets every batted ball hit below 88 mph as 88 mph, otherwise it uses the actual Exit Velocity (src: savant_csv_docs) |
| `home_score_diff` | int16 | yes | — | Home score minus Away score (src: savant_csv_docs) |
| `bat_score_diff` | int16 | yes | — | Batting team score less Pitching team score (src: savant_csv_docs) |
| `home_win_exp` | float | yes | — | Home team win expectancy (src: savant_csv_docs) |
| `bat_win_exp` | float | yes | — | Bat team win expectancy (src: savant_csv_docs) |
| `age_pit_legacy` | int16 | yes | — | pitcher age on 6/30 (src: savant_csv_docs) |
| `age_bat_legacy` | int16 | yes | — | batter age on 6/30 (src: savant_csv_docs) |
| `age_pit` | int16 | yes | — | pitcher age on 12/31 (src: savant_csv_docs) |
| `age_bat` | int16 | yes | — | batter age on 12/31 (src: savant_csv_docs) |
| `n_thruorder_pitcher` | int16 | yes | — | pitcher times through the order (src: savant_csv_docs) |
| `n_priorpa_thisgame_player_at_bat` | int16 | yes | — | number of prior PAs in this game for this batter (src: savant_csv_docs) |
| `pitcher_days_since_prev_game` | int16 | yes | — | number of days since pitcher's last game (src: savant_csv_docs) |
| `batter_days_since_prev_game` | int16 | yes | — | number of days since batter's last game (src: savant_csv_docs) |
| `pitcher_days_until_next_game` | int16 | yes | — | number of days until the pitcher's next game (src: savant_csv_docs) |
| `batter_days_until_next_game` | int16 | yes | — | number of days until the batter's next game (src: savant_csv_docs) |
| `api_break_z_with_gravity` | float | yes | — | Vertical break with gravity included (src: savant_csv_docs) |
| `api_break_x_arm` | float | yes | — | Break, in inches, of a pitch to the pitcher's arm side. (src: savant_csv_docs) |
| `api_break_x_batter_in` | float | yes | — | Break, in inches, of a pitch toward the batter's side of plate. (src: savant_csv_docs) |
| `attack_angle` | float | yes | — | Attack Angle measures the vertical angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to the ground. (src: savant_csv_docs) |
| `attack_direction` | float | yes | — | Attack Direction measures the horizontal angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to a line from home plate to straightaway center field. (src: savant_csv_docs) |
| `swing_path_tilt` | float | yes | — | The vertical angular orientation of the "plane" of the swing, as compared to the ground, defined by the path of the bat in the 40 ms prior to contact, which approximates a slice of a flat disc in shape. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_x_inches` | float | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the X (horizontal) direction. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_y_inches` | float | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the Y (mound-to-plate) direction. (src: savant_csv_docs) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `entity_name` | string | yes | — | TODO |
| `team_abbr` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `level` | string | yes | — | TODO |
| `parent_org` | string | yes | — | TODO |
| `runs_above_average` | double | yes | — | TODO |
| `runs_gained` | double | yes | — | TODO |
| `runs_cost` | double | yes | — | TODO |
| `xruns_gained` | double | yes | — | TODO |
| `xruns_cost` | double | yes | — | TODO |
| `runs_gained_vs_exp` | double | yes | — | TODO |
| `runs_cost_vs_exp` | double | yes | — | TODO |
| `poss_runs` | double | yes | — | TODO |
| `runs_taken_percent` | double | yes | — | TODO |
| `runs_not_taken` | double | yes | — | TODO |
| `n_challenges` | int16 | yes | — | TODO |
| `n_overturns` | int16 | yes | — | TODO |
| `n_confirms` | int16 | yes | — | TODO |
| `rate_overturns` | double | yes | — | TODO |
| `exp_chal` | double | yes | — | TODO |
| `exp_chal_gained` | double | yes | — | TODO |
| `exp_chal_lost` | double | yes | — | TODO |
| `exp_rate_overturns` | double | yes | — | TODO |
| `net_chal_gained` | double | yes | — | TODO |
| `net_chal_lost` | double | yes | — | TODO |
| `poss_overturns` | int16 | yes | — | TODO |
| `overturns_taken_percent` | double | yes | — | TODO |
| `overturns_not_taken` | int16 | yes | — | TODO |
| `n_strikeouts_flip` | int16 | yes | — | TODO |
| `n_walks_flip` | int16 | yes | — | TODO |
| `runs_above_average_against` | double | yes | — | TODO |
| `runs_gained_against` | double | yes | — | TODO |
| `runs_cost_against` | double | yes | — | TODO |
| `xruns_gained_against` | double | yes | — | TODO |
| `xruns_cost_against` | double | yes | — | TODO |
| `runs_gained_vs_exp_against` | double | yes | — | TODO |
| `runs_cost_vs_exp_against` | double | yes | — | TODO |
| `poss_runs_against` | double | yes | — | TODO |
| `runs_taken_percent_against` | double | yes | — | TODO |
| `runs_not_taken_against` | double | yes | — | TODO |
| `n_challenges_against` | int16 | yes | — | TODO |
| `n_overturns_against` | int16 | yes | — | TODO |
| `n_confirms_against` | int16 | yes | — | TODO |
| `rate_overturns_against` | double | yes | — | TODO |
| `exp_chal_against` | double | yes | — | TODO |
| `exp_chal_gained_against` | double | yes | — | TODO |
| `exp_chal_lost_against` | double | yes | — | TODO |
| `exp_rate_overturns_against` | double | yes | — | TODO |
| `net_chal_gained_against` | double | yes | — | TODO |
| `net_chal_lost_against` | double | yes | — | TODO |
| `poss_overturns_against` | int16 | yes | — | TODO |
| `overturns_taken_percent_against` | double | yes | — | TODO |
| `overturns_not_taken_against` | int16 | yes | — | TODO |
| `n_strikeouts_flip_against` | int16 | yes | — | TODO |
| `n_walks_flip_against` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `fielder_name` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `primary_position` | int16 | yes | — | TODO |
| `primary_position_name` | string | yes | — | TODO |
| `total_throws` | int16 | yes | — | TODO |
| `total_throws_1b` | int16 | yes | — | TODO |
| `total_throws_2b` | int16 | yes | — | TODO |
| `total_throws_3b` | int16 | yes | — | TODO |
| `total_throws_ss` | int16 | yes | — | TODO |
| `total_throws_lf` | int16 | yes | — | TODO |
| `total_throws_cf` | int16 | yes | — | TODO |
| `total_throws_rf` | int16 | yes | — | TODO |
| `total_throws_inf` | int16 | yes | — | TODO |
| `total_throws_of` | int16 | yes | — | TODO |
| `max_arm_strength` | double | yes | — | TODO |
| `arm_1b` | double | yes | — | TODO |
| `arm_2b` | double | yes | — | TODO |
| `arm_3b` | double | yes | — | TODO |
| `arm_ss` | double | yes | — | TODO |
| `arm_lf` | double | yes | — | TODO |
| `arm_cf` | double | yes | — | TODO |
| `arm_rf` | double | yes | — | TODO |
| `arm_inf` | double | yes | — | TODO |
| `arm_of` | double | yes | — | TODO |
| `arm_overall` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `entity_name` | string | yes | — | TODO |
| `entity_id` | int32 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `runner_runs` | double | yes | — | TODO |
| `fielder_runs` | double | yes | — | TODO |
| `runner_runs_advances` | double | yes | — | TODO |
| `runner_runs_thrown_out` | double | yes | — | TODO |
| `runner_runs_hold` | double | yes | — | TODO |
| `fielder_runs_advances` | double | yes | — | TODO |
| `fielder_runs_thrown_out` | double | yes | — | TODO |
| `fielder_runs_hold` | double | yes | — | TODO |
| `n_opp_xb` | int16 | yes | — | TODO |
| `n_att_xb` | int16 | yes | — | TODO |
| `rate_att_xb` | double | yes | — | TODO |
| `est_rate_att_generic_runner` | double | yes | — | TODO |
| `est_rate_att_generic_fielder` | double | yes | — | TODO |
| `n_out` | int16 | yes | — | TODO |
| `n_safe` | int16 | yes | — | TODO |
| `rate_safe` | double | yes | — | TODO |
| `rate_safe_per_attempt` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `player_id` | int32 | yes | — | TODO |
| `entity_name` | string | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `start_year` | int16 | yes | — | TODO |
| `end_year` | int16 | yes | — | TODO |
| `runner_runs_tot` | double | yes | — | TODO |
| `runner_runs_xb` | double | yes | `runner_runs_XB` | TODO |
| `runner_runs_sbx` | double | yes | `runner_runs_SBX` | TODO |
| `n_runner_moved` | int16 | yes | `N_runner_moved` | TODO |
| `runner_runs_xb_swipe` | double | yes | `runner_runs_XB_swipe` | TODO |
| `runner_runs_xb_snipe` | double | yes | `runner_runs_XB_snipe` | TODO |
| `runner_runs_xb_freeze` | double | yes | `runner_runs_XB_freeze` | TODO |
| `n_runner_moved_xb` | int16 | yes | `N_runner_moved_XB` | TODO |
| `runner_runs_sb2` | double | yes | `runner_runs_SB2` | TODO |
| `runner_runs_sb3` | double | yes | `runner_runs_SB3` | TODO |
| `simple_stolen_on_running_act_sb2` | double | yes | `simple_stolen_on_running_act_SB2` | TODO |
| `simple_stolen_on_running_act_sb3` | double | yes | `simple_stolen_on_running_act_SB3` | TODO |
| `n_runner_moved_sbx` | int16 | yes | `N_runner_moved_SBX` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `player_id` | int32 | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `start_year` | int16 | yes | — | TODO |
| `end_year` | int16 | yes | — | TODO |
| `key_target_base` | string | yes | — | TODO |
| `runs_stolen_on_running_act` | double | yes | — | TODO |
| `n_init` | int16 | yes | — | TODO |
| `rate_sbx` | double | yes | — | TODO |
| `n_sb` | int16 | yes | — | TODO |
| `n_cs` | int16 | yes | — | TODO |
| `n_pk` | int16 | yes | — | TODO |
| `n_bk` | int16 | yes | — | TODO |
| `n_fb` | int16 | yes | — | TODO |
| `n_plus` | int16 | yes | — | TODO |
| `n_minus` | int16 | yes | — | TODO |
| `net_act_plus` | double | yes | — | TODO |
| `net_act_minus` | double | yes | — | TODO |
| `r_primary_lead` | double | yes | — | TODO |
| `r_secondary_lead` | double | yes | — | TODO |
| `r_sec_minus_prim_lead` | double | yes | — | TODO |
| `r_primary_lead_sbx` | double | yes | — | TODO |
| `r_secondary_lead_sbx` | double | yes | — | TODO |
| `r_sec_minus_prim_lead_sbx` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `swings_competitive` | int16 | yes | — | TODO |
| `percent_swings_competitive` | double | yes | — | TODO |
| `contact` | int16 | yes | — | TODO |
| `avg_bat_speed` | double | yes | — | TODO |
| `hard_swing_rate` | double | yes | — | TODO |
| `squared_up_per_bat_contact` | double | yes | — | TODO |
| `squared_up_per_swing` | double | yes | — | TODO |
| `blast_per_bat_contact` | double | yes | — | TODO |
| `blast_per_swing` | double | yes | — | TODO |
| `swing_length` | double | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `swords` | int16 | yes | — | TODO |
| `batter_run_value` | double | yes | — | TODO |
| `whiffs` | int16 | yes | — | TODO |
| `whiff_per_swing` | double | yes | — | TODO |
| `batted_ball_events` | int16 | yes | — | TODO |
| `batted_ball_event_per_swing` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `bbe` | int16 | yes | — | TODO |
| `gb_rate` | double | yes | — | TODO |
| `air_rate` | double | yes | — | TODO |
| `fb_rate` | double | yes | — | TODO |
| `ld_rate` | double | yes | — | TODO |
| `pu_rate` | double | yes | — | TODO |
| `pull_rate` | double | yes | — | TODO |
| `straight_rate` | double | yes | — | TODO |
| `oppo_rate` | double | yes | — | TODO |
| `pull_gb_rate` | double | yes | — | TODO |
| `straight_gb_rate` | double | yes | — | TODO |
| `oppo_gb_rate` | double | yes | — | TODO |
| `pull_air_rate` | double | yes | — | TODO |
| `straight_air_rate` | double | yes | — | TODO |
| `oppo_air_rate` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `player_id` | int32 | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `start_year` | int16 | yes | — | TODO |
| `end_year` | string | yes | — | TODO |
| `pitches` | int16 | yes | — | TODO |
| `catcher_blocking_runs` | int16 | yes | — | TODO |
| `blocks_above_average` | int16 | yes | — | TODO |
| `n_pbwp` | int16 | yes | — | TODO |
| `x_pbwp` | double | yes | — | TODO |
| `blocks_above_average_per_game` | double | yes | — | TODO |
| `freq_pbwp_easy` | double | yes | — | TODO |
| `freq_pbwp_medium` | double | yes | — | TODO |
| `freq_pbwp_tough` | double | yes | — | TODO |
| `diff_pbwp_easy` | double | yes | — | TODO |
| `diff_pbwp_medium` | double | yes | — | TODO |
| `diff_pbwp_tough` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `pitches` | int16 | yes | — | TODO |
| `rv_tot` | string | yes | — | TODO |
| `pct_tot` | double | yes | — | TODO |
| `rv_11` | int16 | yes | — | TODO |
| `pct_11` | double | yes | — | TODO |
| `rv_12` | int16 | yes | — | TODO |
| `pct_12` | double | yes | — | TODO |
| `rv_13` | int16 | yes | — | TODO |
| `pct_13` | double | yes | — | TODO |
| `rv_14` | int16 | yes | — | TODO |
| `pct_14` | double | yes | — | TODO |
| `rv_16` | int16 | yes | — | TODO |
| `pct_16` | double | yes | — | TODO |
| `rv_17` | int16 | yes | — | TODO |
| `pct_17` | double | yes | — | TODO |
| `rv_18` | int16 | yes | — | TODO |
| `pct_18` | double | yes | — | TODO |
| `rv_19` | int16 | yes | — | TODO |
| `pct_19` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `attempts` | int16 | yes | — | TODO |
| `avg_hit_angle` | double | yes | — | TODO |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | TODO |
| `ev50` | double | yes | — | TODO |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | TODO |
| `ev95percent` | double | yes | — | TODO |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | TODO |
| `brl_pa` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `team` | string | yes | — | TODO |
| `team_id` | string | yes | — | TODO |
| `attempts` | int16 | yes | — | TODO |
| `avg_hit_angle` | double | yes | — | TODO |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | TODO |
| `ev50` | double | yes | — | TODO |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | TODO |
| `ev95percent` | double | yes | — | TODO |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | TODO |
| `brl_pa` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `attempts` | int16 | yes | — | TODO |
| `avg_hit_angle` | double | yes | — | TODO |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | TODO |
| `ev50` | double | yes | — | TODO |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | TODO |
| `ev95percent` | double | yes | — | TODO |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | TODO |
| `brl_pa` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `team` | string | yes | — | TODO |
| `team_id` | string | yes | — | TODO |
| `attempts` | int16 | yes | — | TODO |
| `avg_hit_angle` | double | yes | — | TODO |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | TODO |
| `ev50` | double | yes | — | TODO |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | TODO |
| `ev95percent` | double | yes | — | TODO |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | TODO |
| `brl_pa` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `bip` | int16 | yes | — | TODO |
| `ba` | double | yes | — | TODO |
| `est_ba` | double | yes | — | TODO |
| `est_ba_minus_ba_diff` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `est_slg` | double | yes | — | TODO |
| `est_slg_minus_slg_diff` | double | yes | — | TODO |
| `woba` | double | yes | — | TODO |
| `est_woba` | double | yes | — | TODO |
| `est_woba_minus_woba_diff` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `bip` | int16 | yes | — | TODO |
| `ba` | double | yes | — | TODO |
| `est_ba` | double | yes | — | TODO |
| `est_ba_minus_ba_diff` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `est_slg` | double | yes | — | TODO |
| `est_slg_minus_slg_diff` | double | yes | — | TODO |
| `woba` | double | yes | — | TODO |
| `est_woba` | double | yes | — | TODO |
| `est_woba_minus_woba_diff` | double | yes | — | TODO |
| `era` | double | yes | — | TODO |
| `xera` | double | yes | — | Expected ERA, or xERA, is a simple 1:1 translation of Expected Weighted On-Base Average (xwOBA), converted to the ERA scale. xwOBA takes into account the amount of contact (strikeouts, walks, hit by pitch) and the quality of that contact (exit velocity and launch angle), in an attempt to credit the pitcher or hitter for the moment of contact, not for what might happen to that contact thanks to other factors like ballpark, weather, or defense. (src: mlb_glossary_expected_era) |
| `era_minus_xera_diff` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `player` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `team_abbrev` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `type` | string | yes | — | TODO |
| `avg_hr_trot` | double | yes | — | TODO |
| `doubters` | int16 | yes | — | TODO |
| `mostly_gone` | int16 | yes | — | TODO |
| `no_doubters` | int16 | yes | — | TODO |
| `no_doubter_per` | double | yes | — | TODO |
| `hr_total` | int16 | yes | — | TODO |
| `xhr` | double | yes | — | TODO |
| `xhr_diff` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `resp_fielder_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `outs_above_average` | int16 | yes | — | TODO |
| `outs_per_play` | double | yes | — | TODO |
| `rel_league_burst_distance` | double | yes | — | TODO |
| `rel_league_reaction_distance` | double | yes | — | TODO |
| `rel_league_routing_distance` | double | yes | — | TODO |
| `rel_league_bootup_distance` | double | yes | — | TODO |
| `f_bootup_distance` | double | yes | — | TODO |
| `n` | int16 | yes | — | TODO |
| `n_outs` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `display_team_name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `primary_pos_formatted` | string | yes | — | TODO |
| `fielding_runs_prevented` | int16 | yes | — | TODO |
| `outs_above_average` | int16 | yes | — | TODO |
| `outs_above_average_infront` | int16 | yes | — | TODO |
| `outs_above_average_lateral_toward3bline` | int16 | yes | — | TODO |
| `outs_above_average_lateral_toward1bline` | int16 | yes | — | TODO |
| `outs_above_average_behind` | int16 | yes | — | TODO |
| `outs_above_average_rhh` | int16 | yes | — | TODO |
| `outs_above_average_lhh` | int16 | yes | — | TODO |
| `actual_success_rate_formatted` | string | yes | — | TODO |
| `adj_estimated_success_rate_formatted` | string | yes | — | TODO |
| `diff_success_rate_formatted` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `grouping_venue_conditions` | string | yes | — | TODO |
| `key_is_year_rolling` | int16 | yes | — | TODO |
| `key_num_years_rolling` | int16 | yes | — | TODO |
| `key_year` | int16 | yes | — | TODO |
| `is_sport_mlb` | int16 | yes | — | TODO |
| `is_sport_milb` | int16 | yes | — | TODO |
| `sport_id` | int16 | yes | — | TODO |
| `key_bat_side` | string | yes | — | TODO |
| `venue_id` | int16 | yes | — | TODO |
| `venue_name` | string | yes | — | TODO |
| `main_team_id` | int16 | yes | — | TODO |
| `name_display_club` | string | yes | — | TODO |
| `n_pa` | int32 | yes | — | TODO |
| `index_runs` | int16 | yes | — | TODO |
| `index_hardhit` | string | yes | — | TODO |
| `index_woba` | int16 | yes | — | TODO |
| `index_wobatto` | int16 | yes | — | TODO |
| `index_wobacon` | int16 | yes | — | TODO |
| `index_xwobacon` | string | yes | — | TODO |
| `index_xbacon` | string | yes | — | TODO |
| `index_obp` | int16 | yes | — | TODO |
| `index_so` | int16 | yes | — | TODO |
| `index_bb` | int16 | yes | — | TODO |
| `index_bacon` | int16 | yes | — | TODO |
| `index_hits` | int16 | yes | — | TODO |
| `index_1b` | int16 | yes | — | TODO |
| `index_2b` | int16 | yes | — | TODO |
| `index_3b` | int16 | yes | — | TODO |
| `index_hr` | int16 | yes | — | TODO |
| `year_range` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `player_name` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `xwoba` | int16 | yes | — | Expected Weighted On-base Average (xwOBA) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_woba) |
| `xba` | int16 | yes | — | Expected Batting Average (xBA) is a Statcast metric that measures the likelihood that a batted ball will become a hit. (src: mlb_glossary_expected_batting_average) |
| `xslg` | int16 | yes | — | Expected Slugging Percentage (xSLG) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_slugging_percentage) |
| `xiso` | int16 | yes | — | TODO |
| `xobp` | int16 | yes | — | TODO |
| `brl` | int16 | yes | — | TODO |
| `brl_percent` | int16 | yes | — | TODO |
| `exit_velocity` | int16 | yes | — | TODO |
| `max_ev` | int16 | yes | — | TODO |
| `hard_hit_percent` | int16 | yes | — | Statcast defines a 'hard-hit ball' as one hit with an exit velocity of 95 mph or higher, and a player's "hard-hit rate" is simply showing the percentage of batted balls that were hit at 95 mph or more. (src: mlb_glossary_hard_hit_rate) |
| `k_percent` | int16 | yes | — | TODO |
| `bb_percent` | int16 | yes | — | TODO |
| `whiff_percent` | int16 | yes | — | TODO |
| `chase_percent` | int16 | yes | — | TODO |
| `arm_strength` | string | yes | — | On an individual play, Arm Strength is defined as the maximum velocity of any throw made by a fielder -- with the max velocity always being at the release point, due to physics. (src: mlb_glossary_arm_strength) |
| `sprint_speed` | int16 | yes | — | Introduced during the 2017 season, Sprint Speed is a Statcast metric that aims to more precisely quantify speed by measuring how many feet per second a player runs in his fastest one-second window. (src: mlb_glossary_sprint_speed) |
| `oaa` | string | yes | — | Outs Above Average (OAA) is a range-based metric of skill that shows how many outs a player has saved. (src: mlb_glossary_outs_above_average) |
| `bat_speed` | string | yes | — | TODO |
| `squared_up_rate` | string | yes | — | A swing’s squared-up rate tells us how much of the highest possible exit velocity available (based on the physics related to the swing speed and pitch speed) a batter was able to obtain – it is, at its simplest, how much exit velocity did you get as a share of how much exit velocity was possible based on your swing speed and the speed of the pitch. (src: mlb_glossary_squared_up) |
| `swing_length` | string | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `player_name` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `xwoba` | int16 | yes | — | Expected Weighted On-base Average (xwOBA) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_woba) |
| `xba` | int16 | yes | — | Expected Batting Average (xBA) is a Statcast metric that measures the likelihood that a batted ball will become a hit. (src: mlb_glossary_expected_batting_average) |
| `xslg` | int16 | yes | — | Expected Slugging Percentage (xSLG) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_slugging_percentage) |
| `xiso` | int16 | yes | — | TODO |
| `xobp` | int16 | yes | — | TODO |
| `brl` | int16 | yes | — | TODO |
| `brl_percent` | int16 | yes | — | TODO |
| `exit_velocity` | int16 | yes | — | TODO |
| `max_ev` | int16 | yes | — | TODO |
| `hard_hit_percent` | int16 | yes | — | Statcast defines a 'hard-hit ball' as one hit with an exit velocity of 95 mph or higher, and a player's "hard-hit rate" is simply showing the percentage of batted balls that were hit at 95 mph or more. (src: mlb_glossary_hard_hit_rate) |
| `k_percent` | int16 | yes | — | TODO |
| `bb_percent` | int16 | yes | — | TODO |
| `whiff_percent` | int16 | yes | — | TODO |
| `chase_percent` | int16 | yes | — | TODO |
| `arm_strength` | string | yes | — | On an individual play, Arm Strength is defined as the maximum velocity of any throw made by a fielder -- with the max velocity always being at the release point, due to physics. (src: mlb_glossary_arm_strength) |
| `xera` | int16 | yes | — | Expected ERA, or xERA, is a simple 1:1 translation of Expected Weighted On-Base Average (xwOBA), converted to the ERA scale. xwOBA takes into account the amount of contact (strikeouts, walks, hit by pitch) and the quality of that contact (exit velocity and launch angle), in an attempt to credit the pitcher or hitter for the moment of contact, not for what might happen to that contact thanks to other factors like ballpark, weather, or defense. (src: mlb_glossary_expected_era) |
| `fb_velocity` | int16 | yes | — | TODO |
| `fb_spin` | int16 | yes | — | TODO |
| `curve_spin` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `team_name_alt` | string | yes | — | TODO |
| `pitch_type` | string | yes | — | TODO |
| `pitch_name` | string | yes | — | TODO |
| `run_value_per_100` | double | yes | — | TODO |
| `run_value` | int16 | yes | — | TODO |
| `pitches` | int16 | yes | — | TODO |
| `pitch_usage` | double | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `ba` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `woba` | double | yes | — | TODO |
| `whiff_percent` | double | yes | — | TODO |
| `k_percent` | double | yes | — | TODO |
| `put_away` | double | yes | — | TODO |
| `est_ba` | double | yes | — | TODO |
| `est_slg` | double | yes | — | TODO |
| `est_woba` | double | yes | — | TODO |
| `hard_hit_percent` | double | yes | — | Statcast defines a 'hard-hit ball' as one hit with an exit velocity of 95 mph or higher, and a player's "hard-hit rate" is simply showing the percentage of batted balls that were hit at 95 mph or more. (src: mlb_glossary_hard_hit_rate) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `pitcher` | int32 | yes | — | TODO |
| `ff_avg_speed` | double | yes | — | TODO |
| `si_avg_speed` | double | yes | — | TODO |
| `fc_avg_speed` | double | yes | — | TODO |
| `sl_avg_speed` | double | yes | — | TODO |
| `ch_avg_speed` | double | yes | — | TODO |
| `cu_avg_speed` | double | yes | — | TODO |
| `fs_avg_speed` | double | yes | — | TODO |
| `kn_avg_speed` | double | yes | — | TODO |
| `st_avg_speed` | string | yes | — | TODO |
| `sv_avg_speed` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `entity_id` | int16 | yes | — | TODO |
| `entity_name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `pitches` | int32 | yes | — | TODO |
| `all_violations` | int16 | yes | — | TODO |
| `pitcher_timer` | int16 | yes | — | TODO |
| `batter_timer` | int16 | yes | — | TODO |
| `batter_timeout` | int16 | yes | — | TODO |
| `catcher_timer` | int16 | yes | — | TODO |
| `defensive_shift` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `year` | int16 | yes | — | TODO |
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `pitcher_id` | int32 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `team_name_abbrev` | string | yes | — | TODO |
| `pitch_hand` | string | yes | — | TODO |
| `avg_speed` | double | yes | — | TODO |
| `pitches_thrown` | int16 | yes | — | TODO |
| `total_pitches` | int16 | yes | — | TODO |
| `pitches_per_game` | double | yes | — | TODO |
| `pitch_per` | double | yes | — | TODO |
| `pitch_type` | string | yes | — | TODO |
| `pitch_type_name` | string | yes | — | TODO |
| `pitcher_break_z` | double | yes | — | TODO |
| `league_break_z` | double | yes | — | TODO |
| `diff_z` | double | yes | — | TODO |
| `rise` | int16 | yes | — | TODO |
| `pitcher_break_z_induced` | double | yes | — | TODO |
| `pitcher_break_x` | double | yes | — | TODO |
| `league_break_x` | double | yes | — | TODO |
| `diff_x` | double | yes | — | TODO |
| `tail` | int32 | yes | — | TODO |
| `percent_rank_diff_z` | double | yes | — | TODO |
| `percent_rank_diff_x` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `entity_id` | int32 | yes | — | TODO |
| `entity_name` | string | yes | — | TODO |
| `entity_code` | string | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `total_pitches` | int16 | yes | — | TODO |
| `total_pitches_2` | int16 | yes | `total_pitches__2` | TODO |
| `total_pitches_empty` | int16 | yes | — | TODO |
| `median_seconds_empty` | double | yes | — | TODO |
| `total_pitches_onbase` | int16 | yes | — | TODO |
| `median_seconds_empty_2` | double | yes | `median_seconds_empty__2` | TODO |
| `freq_hot` | double | yes | — | TODO |
| `freq_warm` | double | yes | — | TODO |
| `freq_cold` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `entity_name` | string | yes | — | TODO |
| `entity_id` | int32 | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `age` | int16 | yes | — | TODO |
| `maxeff_arm_2b_3b_sba` | double | yes | — | TODO |
| `exchange_2b_3b_sba` | double | yes | — | TODO |
| `pop_2b_sba_count` | int16 | yes | — | TODO |
| `pop_2b_sba` | double | yes | — | TODO |
| `pop_2b_cs` | double | yes | — | TODO |
| `pop_2b_sb` | double | yes | — | TODO |
| `pop_3b_sba_count` | int16 | yes | — | TODO |
| `pop_3b_sba` | double | yes | — | TODO |
| `pop_3b_cs` | double | yes | — | TODO |
| `pop_3b_sb` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `name_abbrev` | string | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `position_name` | string | yes | — | TODO |
| `age` | int16 | yes | — | TODO |
| `bat_side` | string | yes | — | TODO |
| `seconds_since_hit_000` | double | yes | — | TODO |
| `seconds_since_hit_005` | double | yes | — | TODO |
| `seconds_since_hit_010` | double | yes | — | TODO |
| `seconds_since_hit_015` | double | yes | — | TODO |
| `seconds_since_hit_020` | double | yes | — | TODO |
| `seconds_since_hit_025` | double | yes | — | TODO |
| `seconds_since_hit_030` | double | yes | — | TODO |
| `seconds_since_hit_035` | double | yes | — | TODO |
| `seconds_since_hit_040` | double | yes | — | TODO |
| `seconds_since_hit_045` | double | yes | — | TODO |
| `seconds_since_hit_050` | double | yes | — | TODO |
| `seconds_since_hit_055` | double | yes | — | TODO |
| `seconds_since_hit_060` | double | yes | — | TODO |
| `seconds_since_hit_065` | double | yes | — | TODO |
| `seconds_since_hit_070` | double | yes | — | TODO |
| `seconds_since_hit_075` | double | yes | — | TODO |
| `seconds_since_hit_080` | double | yes | — | TODO |
| `seconds_since_hit_085` | double | yes | — | TODO |
| `seconds_since_hit_090` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `year` | int16 | yes | — | TODO |
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `pitch_hand` | string | yes | — | TODO |
| `api_pitch_type` | string | yes | — | TODO |
| `n_pitches` | int16 | yes | — | TODO |
| `release_speed` | double | yes | — | TODO |
| `spin_rate` | int16 | yes | — | Spin Rate measures the spin on the baseball when the pitch is released. (src: mlb_glossary_spin_rate) |
| `movement_inches` | double | yes | — | TODO |
| `alan_active_spin_pct` | double | yes | — | TODO |
| `active_spin` | double | yes | — | TODO |
| `hawkeye_measured` | double | yes | — | TODO |
| `movement_inferred` | double | yes | — | TODO |
| `api_pitch_name` | string | yes | — | TODO |
| `active_spin_formatted` | int16 | yes | — | TODO |
| `hawkeye_measured_clock_minutes` | int16 | yes | — | TODO |
| `movement_inferred_clock_minutes` | int16 | yes | — | TODO |
| `diff_measured_inferred` | double | yes | — | TODO |
| `diff2` | double | yes | — | TODO |
| `diff_measured_inferred_minutes` | int16 | yes | — | TODO |
| `hawkeye_measured_clock_hh` | int16 | yes | — | TODO |
| `hawkeye_measured_clock_mm` | int16 | yes | — | TODO |
| `movement_inferred_clock_hh` | int16 | yes | — | TODO |
| `movement_inferred_clock_mm` | int16 | yes | — | TODO |
| `diff_clock_hh` | int16 | yes | — | TODO |
| `diff_clock_mm` | int16 | yes | — | TODO |
| `hawkeye_measured_clock_label` | string | yes | — | TODO |
| `movement_inferred_clock_label` | string | yes | — | TODO |
| `diff_clock_label` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `age` | int16 | yes | — | TODO |
| `competitive_runs` | int16 | yes | — | TODO |
| `bolts` | int16 | yes | — | A Bolt is any run where the Sprint Speed (defined as "feet per second in a player's fastest one-second window") of the runner is at least 30 ft/sec. (src: mlb_glossary_bolt) |
| `hp_to_1b` | double | yes | — | TODO |
| `sprint_speed` | double | yes | — | Introduced during the 2017 season, Sprint Speed is a Statcast metric that aims to more precisely quantify speed by measuring how many feet per second a player runs in his fastest one-second window. (src: mlb_glossary_sprint_speed) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `side` | string | yes | — | TODO |
| `avg_bat_speed` | double | yes | — | TODO |
| `swing_tilt` | double | yes | — | Swing path is a metric that tells you the shape of a hitter's swing on the way toward contact. (src: mlb_glossary_swing_path_tilt) |
| `attack_angle` | double | yes | — | Attack angle measures the vertical direction that the sweet spot of the bat is traveling at the moment it hits the baseball. (src: mlb_glossary_attack_angle) |
| `attack_direction` | double | yes | — | Attack direction measures the horizontal direction that the sweet spot of the bat is moving at the point of contact with the baseball (or the point the bat and ball cross paths on a swing-and-miss). (src: mlb_glossary_attack_direction) |
| `ideal_attack_angle_rate` | double | yes | — | TODO |
| `avg_intercept_y_vs_plate` | double | yes | — | TODO |
| `avg_intercept_y_vs_batter` | double | yes | — | TODO |
| `avg_batter_y_position` | double | yes | — | TODO |
| `avg_batter_x_position` | double | yes | — | TODO |
| `competitive_swings` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `year` | int16 | yes | — | TODO |
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `pitches` | int16 | yes | — | TODO |
| `runs_all` | double | yes | — | TODO |
| `runs_heart` | double | yes | — | TODO |
| `runs_shadow` | double | yes | — | TODO |
| `runs_chase` | double | yes | — | TODO |
| `runs_waste` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_swing_take -->

<!-- BEGIN GENERATED:statcast.leaderboard_fielding_run_value -->
### Dataset: leaderboard_fielding_run_value

Fielding run value by fielder (embedded JSON rows of the page, no qualifier).

- **View:** `statcast_leaderboard_fielding_run_value`
- **Processed path:** `processed/statcast/leaderboard_fielding_run_value/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `total_runs` | string | yes | — | TODO |
| `inf_of_runs` | string | yes | — | TODO |
| `range_runs` | string | yes | — | TODO |
| `arm_runs` | string | yes | — | TODO |
| `dp_runs` | string | yes | — | TODO |
| `fielding_runs_prevented_on_rec1b` | string | yes | — | TODO |
| `catching_runs` | string | yes | — | TODO |
| `framing_runs` | string | yes | — | TODO |
| `throwing_runs` | string | yes | — | TODO |
| `blocking_runs` | string | yes | — | TODO |
| `abs_runs` | string | yes | — | TODO |
| `outs_total` | int16 | yes | — | TODO |
| `tot_pa` | double | yes | — | TODO |
| `max_pos` | int16 | yes | — | TODO |
| `outs_2` | int16 | yes | — | TODO |
| `outs_3` | int16 | yes | — | TODO |
| `outs_4` | int16 | yes | — | TODO |
| `outs_5` | int16 | yes | — | TODO |
| `outs_6` | int16 | yes | — | TODO |
| `outs_7` | int16 | yes | — | TODO |
| `outs_8` | int16 | yes | — | TODO |
| `outs_9` | int16 | yes | — | TODO |
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `n_teams` | int16 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_fielding_run_value -->

<!-- BEGIN GENERATED:statcast.leaderboard_rolling -->
### Dataset: leaderboard_rolling

Rolling last-N-batted-ball xwOBA windows (50/100/250) per batter and pitcher: a snapshot of the current season (the page ignores the season parameter).

- **View:** `statcast_leaderboard_rolling`
- **Processed path:** `processed/statcast/leaderboard_rolling/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `player_id`, `cat`, `cat_bin`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_name` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `player_team_id` | int16 | yes | — | TODO |
| `cat` | string | yes | — | TODO |
| `cat_bin` | int16 | yes | — | TODO |
| `last_x_xwoba` | double | yes | — | TODO |
| `penultimate_x_xwoba` | double | yes | — | TODO |
| `xwoba_delta` | double | yes | — | TODO |
| `last_x_woba` | double | yes | — | TODO |
| `penultimate_x_woba` | double | yes | — | TODO |
| `woba_delta` | double | yes | — | TODO |
| `last_x_xba` | double | yes | — | TODO |
| `penultimate_x_xba` | double | yes | — | TODO |
| `xba_delta` | double | yes | — | TODO |
| `last_x_ba` | double | yes | — | TODO |
| `penultimate_x_ba` | double | yes | — | TODO |
| `ba_delta` | double | yes | — | TODO |
| `last_x_xslg` | double | yes | — | TODO |
| `penultimate_x_xslg` | double | yes | — | TODO |
| `xslg_delta` | double | yes | — | TODO |
| `last_x_slg` | double | yes | — | TODO |
| `penultimate_x_slg` | double | yes | — | TODO |
| `slg_delta` | double | yes | — | TODO |
| `type_cat_bin` | string | yes | — | TODO |
| `slug` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_rolling -->

<!-- BEGIN GENERATED:statcast.pitches_minors -->
### Dataset: pitches_minors

Minor-league pitch-level Statcast search results (minors=true, 2021 onwards).

- **View:** `statcast_pitches_minors`
- **Processed path:** `processed/statcast/pitches_minors/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `at_bat_number`, `pitch_number`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — | Unique Id for Game. (src: savant_csv_docs) |
| `game_date` | date32[day] | yes | — | Date of the Game. (src: savant_csv_docs) |
| `game_year` | int16 | yes | — | Year game took place. (src: savant_csv_docs) |
| `game_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Type of Game. E = Exhibition, S = Spring Training, R = Regular Season, F = Wild Card, D = Divisional Series, L = League Championship Series, W = World Series (src: savant_csv_docs) |
| `at_bat_number` | int16 | yes | — | Plate appearance number of the game. (src: savant_csv_docs) |
| `pitch_number` | int16 | yes | — | Total pitch number of the plate appearance. (src: savant_csv_docs) |
| `pitcher` | int32 | yes | — | MLB Player Id tied to the play event. (src: savant_csv_docs) |
| `batter` | int32 | yes | — | MLB Player Id tied to the play event. (src: savant_csv_docs) |
| `player_name` | string | yes | — | Player's name tied to the event of the search. (src: savant_csv_docs) |
| `home_team` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Abbreviation of home team. (src: savant_csv_docs) |
| `away_team` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Abbreviation of away team. (src: savant_csv_docs) |
| `inning` | int8 | yes | — | Pre-pitch inning number. (src: savant_csv_docs) |
| `inning_topbot` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Pre-pitch top or bottom of inning. (src: savant_csv_docs) |
| `balls` | int8 | yes | — | Pre-pitch number of balls in count. (src: savant_csv_docs) |
| `strikes` | int8 | yes | — | Pre-pitch number of strikes in count. (src: savant_csv_docs) |
| `outs_when_up` | int8 | yes | — | Pre-pitch number of outs. (src: savant_csv_docs) |
| `pitch_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | The type of pitch derived from Statcast. (src: savant_csv_docs) |
| `pitch_name` | dictionary<values=string, indices=int8, ordered=0> | yes | — | The name of the pitch derived from the Statcast Data. (src: savant_csv_docs) |
| `release_speed` | float | yes | — | Pitch velocity in MPH. Values from 2008-16 are via PitchFX, and adjusted to roughly out-of-hand release point. All velocities from 2017 and beyond are Statcast, which are reported out-of-hand. All velocities are thus on the same scale. (src: savant_csv_docs) |
| `effective_speed` | float | yes | — | Derived speed based on the the extension of the pitcher's release. (src: savant_csv_docs) |
| `release_spin_rate` | float | yes | — | TODO |
| `release_extension` | float | yes | — | Release extension of pitch in feet as tracked by Statcast. (src: savant_csv_docs) |
| `spin_axis` | float | yes | — | The Spin Axis in the 2D X-Z plane in degrees from 0 to 360, such that 180 represents a pure backspin fastball and 0 degrees represents a pure topspin (12-6) curveball (src: savant_csv_docs) |
| `release_pos_x` | float | yes | — | Horizontal Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_y` | float | yes | — | Release position of pitch measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_z` | float | yes | — | Vertical Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `arm_angle` | float | yes | — | The angle between a line parallel to the ground and a l line extending from the location of the pitcher's throwing shoulder and the location of the ball at the time of the pitch. (src: savant_csv_docs) |
| `zone` | int8 | yes | — | Zone location of the ball when it crosses the plate from the catcher's perspective. (src: savant_csv_docs) |
| `plate_x` | float | yes | — | Horizontal position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `plate_z` | float | yes | — | Vertical position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `sz_top` | float | yes | — | Top of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, top of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the top of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `sz_bot` | float | yes | — | Bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the bottom of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `pfx_x` | float | yes | — | Horizontal movement in feet from the catcher's perspective. (src: savant_csv_docs) |
| `pfx_z` | float | yes | — | Vertical movement in feet from the catcher's perpsective. (src: savant_csv_docs) |
| `vx0` | float | yes | — | The velocity of the pitch, in feet per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vy0` | float | yes | — | The velocity of the pitch, in feet per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vz0` | float | yes | — | TODO |
| `ax` | float | yes | — | The acceleration of the pitch, in feet per second per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `ay` | float | yes | — | The acceleration of the pitch, in feet per second per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `az` | float | yes | — | The acceleration of the pitch, in feet per second per second, in z-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `stand` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Side of the plate batter is standing. (src: savant_csv_docs) |
| `p_throws` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Hand pitcher throws with. (src: savant_csv_docs) |
| `type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Short hand of pitch result. B = ball, S = strike, X = in play. (src: savant_csv_docs) |
| `events` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Event of the resulting Plate Appearance. (src: savant_csv_docs) |
| `description` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Description of the resulting pitch. (src: savant_csv_docs) |
| `des` | string | yes | — | Plate appearance description from game day. (src: savant_csv_docs) |
| `bb_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Batted ball type, ground_ball, line_drive, fly_ball, popup. (src: savant_csv_docs) |
| `hit_location` | int8 | yes | — | Position of first fielder to touch the ball. (src: savant_csv_docs) |
| `launch_speed` | float | yes | — | Exit velocity of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_angle` | float | yes | — | Launch angle of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_speed_angle` | int8 | yes | — | Launch speed/angle zone based on launch angle and exit velocity. Weak Topped Under Flare/Burner Solid Contact Barrel (src: savant_csv_docs) |
| `hit_distance_sc` | float | yes | — | TODO |
| `hc_x` | float | yes | — | Hit coordinate X of batted ball. (src: savant_csv_docs) |
| `hc_y` | float | yes | — | Hit coordinate Y of batted ball. (src: savant_csv_docs) |
| `bat_speed` | float | yes | — | TODO |
| `swing_length` | float | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `estimated_ba_using_speedangle` | float | yes | — | Estimated Batting Avg based on launch angle and exit velocity. (src: savant_csv_docs) |
| `estimated_woba_using_speedangle` | float | yes | — | Estimated wOBA based on launch angle and exit velocity. (src: savant_csv_docs) |
| `woba_value` | float | yes | — | wOBA value based on result of play. (src: savant_csv_docs) |
| `woba_denom` | float | yes | — | wOBA denominator based on result of play. (src: savant_csv_docs) |
| `babip_value` | float | yes | — | BABIP value based on result of play. (src: savant_csv_docs) |
| `iso_value` | float | yes | — | ISO value based on result of play. (src: savant_csv_docs) |
| `delta_home_win_exp` | float | yes | — | The change in Win Expectancy before the Plate Appearance and after the Plate Appearance (src: savant_csv_docs) |
| `delta_run_exp` | float | yes | — | The change in Run Expectancy before the Pitch and after the Pitch (src: savant_csv_docs) |
| `on_1b` | int32 | yes | — | Pre-pitch MLB Player Id of Runner on 1B. (src: savant_csv_docs) |
| `on_2b` | int32 | yes | — | Pre-pitch MLB Player Id of Runner on 2B. (src: savant_csv_docs) |
| `on_3b` | int32 | yes | — | Pre-pitch MLB Player Id of Runner on 3B. (src: savant_csv_docs) |
| `home_score` | int16 | yes | — | Pre-pitch home score (src: savant_csv_docs) |
| `away_score` | int16 | yes | — | Pre-pitch away score (src: savant_csv_docs) |
| `bat_score` | int16 | yes | — | Pre-pitch bat team score (src: savant_csv_docs) |
| `fld_score` | int16 | yes | — | Pre-pitch field team score (src: savant_csv_docs) |
| `post_home_score` | int16 | yes | — | Post-pitch home score (src: savant_csv_docs) |
| `post_away_score` | int16 | yes | — | Post-pitch away score (src: savant_csv_docs) |
| `post_bat_score` | int16 | yes | — | Post-pitch bat team score (src: savant_csv_docs) |
| `post_fld_score` | int16 | yes | — | TODO |
| `fielder_2` | int32 | yes | — | Pre-pitch MLB Player Id of Catcher. (src: savant_csv_docs) |
| `fielder_3` | int32 | yes | — | MLB Player Id for 1B. (src: savant_csv_docs) |
| `fielder_4` | int32 | yes | — | MLB Player Id for 2B. (src: savant_csv_docs) |
| `fielder_5` | int32 | yes | — | MLB Player Id for 3B. (src: savant_csv_docs) |
| `fielder_6` | int32 | yes | — | MLB Player Id for SS. (src: savant_csv_docs) |
| `fielder_7` | int32 | yes | — | MLB Player Id for LF. (src: savant_csv_docs) |
| `fielder_8` | int32 | yes | — | MLB Player Id for CF. (src: savant_csv_docs) |
| `fielder_9` | int32 | yes | — | MLB Player Id for RF. (src: savant_csv_docs) |
| `if_fielding_alignment` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Infield fielding alignment at the time of the pitch. (src: savant_csv_docs) |
| `of_fielding_alignment` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Outfield fielding alignment at the time of the pitch. (src: savant_csv_docs) |
| `spin_dir` | string | yes | — | * Deprecated field from the old tracking system. (src: savant_csv_docs) |
| `spin_rate_deprecated` | string | yes | — | * Deprecated field from the old tracking system. Replaced by release_spin (src: savant_csv_docs) |
| `break_angle_deprecated` | string | yes | — | * Deprecated field from the old tracking system. (src: savant_csv_docs) |
| `break_length_deprecated` | string | yes | — | * Deprecated field from the old tracking system. (src: savant_csv_docs) |
| `tfs_deprecated` | string | yes | — | * Deprecated field from old tracking system. (src: savant_csv_docs) |
| `tfs_zulu_deprecated` | string | yes | — | * Deprecated field from old tracking system. (src: savant_csv_docs) |
| `umpire` | string | yes | — | * Deprecated field from old tracking system. (src: savant_csv_docs) |
| `sv_id` | string | yes | — | Non-unique Id of play event per game. (src: savant_csv_docs) |
| `miss_distance` | float | yes | — | TODO |
| `estimated_slg_using_speedangle` | float | yes | — | TODO |
| `delta_pitcher_run_exp` | float | yes | — | TODO |
| `hyper_speed` | float | yes | — | Savant display name: Adjusted EV. Adjusted Exit Velocity sets every batted ball hit below 88 mph as 88 mph, otherwise it uses the actual Exit Velocity (src: savant_csv_docs) |
| `home_score_diff` | int16 | yes | — | Home score minus Away score (src: savant_csv_docs) |
| `bat_score_diff` | int16 | yes | — | Batting team score less Pitching team score (src: savant_csv_docs) |
| `home_win_exp` | float | yes | — | Home team win expectancy (src: savant_csv_docs) |
| `bat_win_exp` | float | yes | — | Bat team win expectancy (src: savant_csv_docs) |
| `age_pit_legacy` | int16 | yes | — | pitcher age on 6/30 (src: savant_csv_docs) |
| `age_bat_legacy` | int16 | yes | — | batter age on 6/30 (src: savant_csv_docs) |
| `age_pit` | int16 | yes | — | pitcher age on 12/31 (src: savant_csv_docs) |
| `age_bat` | int16 | yes | — | batter age on 12/31 (src: savant_csv_docs) |
| `n_thruorder_pitcher` | int16 | yes | — | pitcher times through the order (src: savant_csv_docs) |
| `n_priorpa_thisgame_player_at_bat` | int16 | yes | — | number of prior PAs in this game for this batter (src: savant_csv_docs) |
| `pitcher_days_since_prev_game` | int16 | yes | — | number of days since pitcher's last game (src: savant_csv_docs) |
| `batter_days_since_prev_game` | int16 | yes | — | number of days since batter's last game (src: savant_csv_docs) |
| `pitcher_days_until_next_game` | int16 | yes | — | number of days until the pitcher's next game (src: savant_csv_docs) |
| `batter_days_until_next_game` | int16 | yes | — | number of days until the batter's next game (src: savant_csv_docs) |
| `api_break_z_with_gravity` | float | yes | — | Vertical break with gravity included (src: savant_csv_docs) |
| `api_break_x_arm` | float | yes | — | Break, in inches, of a pitch to the pitcher's arm side. (src: savant_csv_docs) |
| `api_break_x_batter_in` | float | yes | — | Break, in inches, of a pitch toward the batter's side of plate. (src: savant_csv_docs) |
| `attack_angle` | float | yes | — | Attack Angle measures the vertical angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to the ground. (src: savant_csv_docs) |
| `attack_direction` | float | yes | — | Attack Direction measures the horizontal angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to a line from home plate to straightaway center field. (src: savant_csv_docs) |
| `swing_path_tilt` | float | yes | — | The vertical angular orientation of the "plane" of the swing, as compared to the ground, defined by the path of the bat in the 40 ms prior to contact, which approximates a slice of a flat disc in shape. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_x_inches` | float | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the X (horizontal) direction. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_y_inches` | float | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the Y (mound-to-plate) direction. (src: savant_csv_docs) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.pitches_minors -->

<!-- BEGIN GENERATED:statcast.leaderboard_active_spin -->
### Dataset: leaderboard_active_spin

Active spin (measured vs inferred) per pitcher and pitch type; the `min` qualifier breaks this route, so it is not sent.

- **View:** `statcast_leaderboard_active_spin`
- **Processed path:** `processed/statcast/leaderboard_active_spin/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`, `pitch_hand`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `entity_name` | string | yes | — | TODO |
| `entity_id` | int32 | yes | — | TODO |
| `pitch_hand` | string | yes | — | TODO |
| `active_spin_fourseam` | double | yes | — | TODO |
| `active_spin_sinker` | double | yes | — | TODO |
| `active_spin_cutter` | double | yes | — | TODO |
| `active_spin_changeup` | double | yes | — | TODO |
| `active_spin_splitter` | double | yes | — | TODO |
| `active_spin_curve` | double | yes | — | TODO |
| `active_spin_slider` | double | yes | — | TODO |
| `active_spin_sweeper` | double | yes | — | TODO |
| `active_spin_slurve` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_active_spin -->

<!-- BEGIN GENERATED:statcast.leaderboard_catch_probability -->
### Dataset: leaderboard_catch_probability

Fielder catch probability by star bucket (2016 onwards). The `type` parameter empties this route (and produced anonymous rows in an earlier probe), so it is not sent.

- **View:** `statcast_leaderboard_catch_probability`
- **Processed path:** `processed/statcast/leaderboard_catch_probability/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `oaa` | int16 | yes | — | Outs Above Average (OAA) is a range-based metric of skill that shows how many outs a player has saved. (src: mlb_glossary_outs_above_average) |
| `n_fieldout_5stars` | int16 | yes | — | TODO |
| `n_opp_5stars` | int16 | yes | — | TODO |
| `n_5star_percent` | double | yes | — | TODO |
| `n_fieldout_4stars` | int16 | yes | — | TODO |
| `n_opp_4stars` | int16 | yes | — | TODO |
| `n_4star_percent` | double | yes | — | TODO |
| `n_fieldout_3stars` | int16 | yes | — | TODO |
| `n_opp_3stars` | int16 | yes | — | TODO |
| `n_3star_percent` | double | yes | — | TODO |
| `n_fieldout_2stars` | int16 | yes | — | TODO |
| `n_opp_2stars` | int16 | yes | — | TODO |
| `n_2star_percent` | double | yes | — | TODO |
| `n_fieldout_1stars` | int16 | yes | — | TODO |
| `n_opp_1stars` | int16 | yes | — | TODO |
| `n_1star_percent` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_catch_probability -->
