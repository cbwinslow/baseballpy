# Statcast (Baseball Savant) Endpoint & Schema Catalog

Probed live on 2026-10-27 (`docs/savant_probe.json`, `scripts/gen_savant_schemas.py`); every claim below
is from that probe, not from memory.

## Upstream Overview
- **Provider:** Baseball Savant (MLBAM), `https://baseballsavant.mlb.com`, `GET`, UTF-8 CSV (BOM possible).
- **Rate limit:** 2.5 requests/second through the shared `HttpClient` (token bucket, retries, HTTP/2).
- **Server cap:** a pitch search returns at most 25,000 rows; `baseballpy` bisects any window that reaches it
  and raises `TruncatedResultError` if a single day still hits it (nothing is ever truncated silently).
- **Precision (decided 2026-11-12):** every decimal column is a 64-bit float. The pitch tables used 32-bit floats until the round-trip check showed that the text `85.8` was stored as `85.80000305175781` and `-0.4576421044460543` as `-0.4576421082019806` (50 columns, differences up to 7e-6). The 64-bit form costs 2.5% of file size (2024: 96.7 MB to 99.1 MB).
- **What Savant's own documentation says (read 2026-11-12, baseballsavant.mlb.com/csv-docs):** it gives units for some fields (`release_speed` in MPH, `pfx_x` in feet) but **no data types and no precision** for any column, and says `batter`, `pitcher`, `fielder_2`..`fielder_9` are MLB player ids and `game_pk` the game id. Two things to remember: (1) **`plate_x` changed meaning in 2026**: through 2025 it measures from the front of the plate, from 2026 from the middle of the plate to match the ABS system, so a model that spans the change must adjust; (2) the documentation lists `vy0` twice (the second entry is `vz0`), a labelling error in the provider's page.
- **Savant revises data and the raw windows overlap.** A window that hits the 25,000-row cap is stored as the capped window and as its halves, and the same pitch fetched at different times can differ in some columns. The processed data keeps one version per key. The round-trip check therefore reports key coverage, not values, for such seasons (minor leagues 2026: 1,123,498 raw rows hold 869,226 distinct keys, all present).
- **Typing:** every dataset has a strict PyArrow schema generated from the live headers; columns that appear
  later land in a trailing `_extras` JSON column (and log `schema_drift` once); uncastable cells are quarantined.

## How the data is verified (2026-11-12)
`baseballpy verify-roundtrip statcast [--full]` compares sampled raw files with the stored cells (a leaderboard kept as a page is decoded first); 48 of 50 datasets were clean and the two losses (32-bit floats in the pitch tables) are fixed. Windows that overlap or several fetched versions of a pitch are checked by key coverage, because Savant revises data.

---

**Result of the full check (2026-11-12):** `pitches` 15,007,133 rows and `pitches_minors` 4,536,245 rows equal the raw text after the 64-bit rebuild (the minor-league files also hold 91,845 rows that are other fetched versions of the same pitches, checked by key). **Known provider quirk:** in 2026 Savant returns every `hit_into_play` pitch twice, byte-identical (35,430 of 909,080 rows; no earlier season does). The lake keeps them, as the raw files have them; query the view `v_pitches_unique` (one row per `game_pk, at_bat_number, pitch_number`, ADR 119) when one row per pitch is needed. The ingest logs a duplicate-key warning for it.

## Where the column types come from, and the latest check (2026-11-14)
- **No provider gives types.** Savant's own CSV page (`baseballsavant.mlb.com/csv-docs`) defines each column but names no type; pybaseball has no type table; baseballr's reference lists R types (character, Date, numeric) that it regenerated from live answers in version 2.0.0. So the types here are read from the data, widened over samples of every season (`scripts/gen_savant_schemas.py`), and then proven against the raw text.
- **Rules that follow from real losses:** decimals are 64-bit floats (never 32-bit: `85.8` once became `85.80000305175781`), identifiers and codes are text, an empty cell is NULL, a column the provider sends but nothing reads is kept in `_extras` (never dropped).
- **Mixed number-and-text fields:** none was found in the pitch table. The text columns are team codes, pitch and event names, descriptions, `sv_id`, `umpire`, the fielding alignments and the old tracking fields that Savant still sends empty (`spin_dir`, `*_deprecated`: no value in any season, so nothing is lost).
- **Check of 2026-11-14 (`baseballpy verify-roundtrip`, whole lake):** 48 Statcast datasets clean; `pitches` 56 raw files and 984,924 rows compared cell by cell with no loss and nothing quarantined. The same run found no loss in Retrosheet (36 datasets), Lahman (27), FanGraphs (10), Chadwick (4), Kalshi (4) and Polymarket (4).

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

**Season bounds (ADR 56):** no Statcast dataset is requested before 2008 (`pitches_minors` before 2021, a leaderboard before its own first season); the top is the newest season whose first day (spring training) has arrived on the lake clock, read from the MLB season calendar (`core/season_calendar.py`, ADR 66), never a constant, and a season whose calendar has not started (January and February) is skipped. Bulk ingests report such a season as `skipped` with the reason and make no request; `extract`, `get_leaderboard` and `table` raise `ValueError`. The rule lives in `sources/statcast/seasons.py`.

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
| `leaderboard_swing_timing_miss_distance_batter` | `/leaderboard/bat-tracking/swing-timing-miss-distance` | `type=batter` | `season_array` | `None` | None | player-season | `id, year` |
| `leaderboard_swing_timing_miss_distance_pitcher` | `/leaderboard/bat-tracking/swing-timing-miss-distance` | `type=pitcher` | `season_array` | `None` | None | player-season | `id, year` |
| `leaderboard_year_to_year_batter` | `/leaderboard/statcast-year-to-year` | - | `year` | `None` | None | player | `entity_id` |
| `leaderboard_year_to_year_pitcher` | `/leaderboard/statcast-year-to-year` | `group=Pitcher` | `year` | `None` | None | player | `entity_id` |
| `leaderboard_pitcher_arm_angles` | `/leaderboard/pitcher-arm-angles` | - | `season` | `None` | None | player-season | `pitcher` |
| `leaderboard_pitcher_running_game` | `/leaderboard/pitcher-running-game` | - | `season_snake` | `None` | None | player-season | `player_id, key_target_base` |
| `leaderboard_first_base_receiving` | `/leaderboard/first-base-scoops-receiving` | - | `season_array` | `None` | None | player-season | `id, year` |
| `leaderboard_outfield_directional_oaa` | `/leaderboard/outfield_directional_outs_above_average` | - | `year` | `None` | None | player-season | `player_id` |
| `leaderboard_catcher_stance` | `/leaderboard/catcher-stance` | - | `season_range` | `None` | None | player-season | `id, year` |
| `leaderboard_catcher_throwing` | `/leaderboard/catcher-throwing` | - | `season_snake` | `None` | None | player-season | `player_id` |
| `leaderboard_hot_stove_batter` | `/leaderboard/hot-stove` | - | `none` | `None` | None | player-season | `player_id, year` |
| `leaderboard_hot_stove_pitcher` | `/leaderboard/hot-stove` | - | `none` | `None` | None | player-season | `player_id, year` |

### Routes probed and not ingested

The first probe (2026-10-27) guessed route names and wrongly reported four routes as 404. Checked again on 2026-11-11 against the live Savant menu: `outfield_directional_outs_above_average`, `catcher-throwing` and `statcast-year-to-year` answer CSV (they are now the datasets `leaderboard_outfield_directional_oaa`, `leaderboard_catcher_throwing`, `leaderboard_year_to_year_batter` and `_pitcher`), and eight more menu routes were missing and were added (`swing_timing_miss_distance_batter` and `_pitcher`, `pitcher_arm_angles`, `pitcher_running_game`, `first_base_receiving`, `catcher_stance`, `hot_stove_batter` and `_pitcher`).

| Route | Reason (probed 2026-10-27) |
|---|---|
| `/leaderboard/bat-speed` (`bat_speed`) | route answers 404; bat speed is a column of bat_tracking |
| `/statcast-search-world-baseball-classic/csv` (World Baseball Classic pitch search) | probed 2026-11-11: the route answers 200 with the same rows as `/statcast_search/csv` for every filter tried (`hfGT=F\|D\|L\|W\|`, `hfSea=2023\|`, date windows): MLB spring-training and postseason pitches, no WBC game. The page's script offers the rounds `F` Pool Play, `D` Quarterfinals, `L` Semifinals, `W` Championship and says WBC pitch data begin with the 2023 tournament, but the request that selects the WBC population was not found. Open item. |
| `/leaderboard/top-performers` | probed 2026-11-11: answers 200 HTML with no embedded array of rows (the data is drawn by the page); not yet parsed. Open item. |
| `/leaderboard/weighted-score` (Enhanced Game Scores) | probed 2026-11-11: answers 200 HTML whose only embedded array is a player picker list (`playerList`), not the scores. Open item. |

**API:** `get_leaderboard(slug_or_legacy_name, year, type=...)`, `StatcastLeaderboardExtractor.ingest_leaderboard(slug)`,
`ingest_all()`, `custom_leaderboard(year, selections=[...])` (ad hoc: `/leaderboard/custom`, types inferred, never persisted).
The `StatcastLeaderboard` enum has one member per supported slug (a test compares it with the registry).

## Savant revises past seasons (found by `verify-sample`, 2026-11-11)

Statcast is a live upstream: Baseball Savant corrects and reclassifies past pitches. A fresh download of the 2024
regular season into a scratch home matched the lake in the numbers and keys of every chunk, but in about 65 of the
5-day windows a few dozen pitches carry another `pitch_type` and `pitch_name` than the copy downloaded earlier (for
example 24 pitches in the window 2024-07-19 to 2024-07-23 changed from `SL`/Slider to `ST`/Sweeper). The code did
not change; the provider did. What this means for users:

- A closed season is treated as final, so it is not downloaded again by itself (the freshness policy). To pick up
  Savant's revisions, run `baseballpy ingest statcast -s <year> -d pitches --refresh`. The refresh replaces the raw file and the manifest keeps the sha256, size and time of the version it
  replaced (`previous`, ADR 122).
- Two users who downloaded the same season at different times can hold different `pitch_type` values for a small
  share of pitches. The raw files keep exactly what each download received (`raw/statcast/pitches/season=YYYY/`,
  sha256 in the manifest), so the difference is traceable.
- `baseballpy verify-sample statcast -s <year> -d pitches` shows which windows differ and in which column.

## Storage Layout (lake v2)
- Raw: `raw/statcast/pitches/season=YYYY/<start>_<end>.csv`; `raw/statcast/leaderboard_<slug>/season=YYYY/<slug>_<year>.csv` (`.html` for `park_factors`); `raw/statcast/game_feed/season=YYYY/<pk>.json`. Each raw file records its sha256 and source URL in the dataset manifest.
- Typed: `processed/statcast/pitches/season=YYYY/part-<start>_<end>.parquet` (view `statcast_pitches`) and `processed/statcast/leaderboard_<slug>/season=YYYY/part-<slug>_<year>.parquet` (view `statcast_leaderboard_<slug>`). Leaderboards never share a directory with pitches.
- Documentation: Savant's data dictionary page is kept as `raw/statcast/documents/csv-docs.html` (job `documents`, once per lake).
- Fingerprints: Savant sends no version marker, so each raw file records its ETag when there is one, else its sha256; past seasons are immutable and the trailing days of the current season are refetched.
- Python: `baseballpy.sources.statcast.table(name, season)` returns any registered dataset (`table("pitches", 2024)` ingests the season first, `table("leaderboard_sprint_speed", 2024)` fetches one leaderboard); `datasets()` lists the names.
- Export (`baseballpy export statcast --to parquet|csv|duckdb|postgres`): see the checks recorded in the review's design notes.

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
| `release_speed` | double | yes | — | Pitch velocity in MPH. Values from 2008-16 are via PitchFX, and adjusted to roughly out-of-hand release point. All velocities from 2017 and beyond are Statcast, which are reported out-of-hand. All velocities are thus on the same scale. (src: savant_csv_docs) |
| `effective_speed` | double | yes | — | Derived speed based on the the extension of the pitcher's release. (src: savant_csv_docs) |
| `release_spin_rate` | double | yes | — | TODO |
| `release_extension` | double | yes | — | Release extension of pitch in feet as tracked by Statcast. (src: savant_csv_docs) |
| `spin_axis` | double | yes | — | The Spin Axis in the 2D X-Z plane in degrees from 0 to 360, such that 180 represents a pure backspin fastball and 0 degrees represents a pure topspin (12-6) curveball (src: savant_csv_docs) |
| `release_pos_x` | double | yes | — | Horizontal Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_y` | double | yes | — | Release position of pitch measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_z` | double | yes | — | Vertical Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `arm_angle` | double | yes | — | The angle between a line parallel to the ground and a l line extending from the location of the pitcher's throwing shoulder and the location of the ball at the time of the pitch. (src: savant_csv_docs) |
| `zone` | int8 | yes | — | Zone location of the ball when it crosses the plate from the catcher's perspective. (src: savant_csv_docs) |
| `plate_x` | double | yes | — | Horizontal position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `plate_z` | double | yes | — | Vertical position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `sz_top` | double | yes | — | Top of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, top of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the top of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `sz_bot` | double | yes | — | Bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the bottom of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `pfx_x` | double | yes | — | Horizontal movement in feet from the catcher's perspective. (src: savant_csv_docs) |
| `pfx_z` | double | yes | — | Vertical movement in feet from the catcher's perpsective. (src: savant_csv_docs) |
| `vx0` | double | yes | — | The velocity of the pitch, in feet per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vy0` | double | yes | — | The velocity of the pitch, in feet per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vz0` | double | yes | — | TODO |
| `ax` | double | yes | — | The acceleration of the pitch, in feet per second per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `ay` | double | yes | — | The acceleration of the pitch, in feet per second per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `az` | double | yes | — | The acceleration of the pitch, in feet per second per second, in z-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `stand` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Side of the plate batter is standing. (src: savant_csv_docs) |
| `p_throws` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Hand pitcher throws with. (src: savant_csv_docs) |
| `type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Short hand of pitch result. B = ball, S = strike, X = in play. (src: savant_csv_docs) |
| `events` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Event of the resulting Plate Appearance. (src: savant_csv_docs) |
| `description` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Description of the resulting pitch. (src: savant_csv_docs) |
| `des` | string | yes | — | Plate appearance description from game day. (src: savant_csv_docs) |
| `bb_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Batted ball type, ground_ball, line_drive, fly_ball, popup. (src: savant_csv_docs) |
| `hit_location` | int8 | yes | — | Position of first fielder to touch the ball. (src: savant_csv_docs) |
| `launch_speed` | double | yes | — | Exit velocity of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_angle` | double | yes | — | Launch angle of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_speed_angle` | int8 | yes | — | Launch speed/angle zone based on launch angle and exit velocity. Weak Topped Under Flare/Burner Solid Contact Barrel (src: savant_csv_docs) |
| `hit_distance_sc` | double | yes | — | TODO |
| `hc_x` | double | yes | — | Hit coordinate X of batted ball. (src: savant_csv_docs) |
| `hc_y` | double | yes | — | Hit coordinate Y of batted ball. (src: savant_csv_docs) |
| `bat_speed` | double | yes | — | Bat speed is measured at the sweet-spot of the bat. Average bat speed is the average of the top 90% of a player's swings. (src: savant_csv_docs) |
| `swing_length` | double | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `estimated_ba_using_speedangle` | double | yes | — | Estimated Batting Avg based on launch angle and exit velocity. (src: savant_csv_docs) |
| `estimated_woba_using_speedangle` | double | yes | — | Estimated wOBA based on launch angle and exit velocity. (src: savant_csv_docs) |
| `woba_value` | double | yes | — | wOBA value based on result of play. (src: savant_csv_docs) |
| `woba_denom` | double | yes | — | wOBA denominator based on result of play. (src: savant_csv_docs) |
| `babip_value` | double | yes | — | BABIP value based on result of play. (src: savant_csv_docs) |
| `iso_value` | double | yes | — | ISO value based on result of play. (src: savant_csv_docs) |
| `delta_home_win_exp` | double | yes | — | The change in Win Expectancy before the Plate Appearance and after the Plate Appearance (src: savant_csv_docs) |
| `delta_run_exp` | double | yes | — | The change in Run Expectancy before the Pitch and after the Pitch (src: savant_csv_docs) |
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
| `miss_distance` | double | yes | — | TODO |
| `estimated_slg_using_speedangle` | double | yes | — | TODO |
| `delta_pitcher_run_exp` | double | yes | — | TODO |
| `hyper_speed` | double | yes | — | Savant display name: Adjusted EV. Adjusted Exit Velocity sets every batted ball hit below 88 mph as 88 mph, otherwise it uses the actual Exit Velocity (src: savant_csv_docs) |
| `home_score_diff` | int16 | yes | — | Home score minus Away score (src: savant_csv_docs) |
| `bat_score_diff` | int16 | yes | — | Batting team score less Pitching team score (src: savant_csv_docs) |
| `home_win_exp` | double | yes | — | Home team win expectancy (src: savant_csv_docs) |
| `bat_win_exp` | double | yes | — | Bat team win expectancy (src: savant_csv_docs) |
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
| `api_break_z_with_gravity` | double | yes | — | Vertical break with gravity included (src: savant_csv_docs) |
| `api_break_x_arm` | double | yes | — | Break, in inches, of a pitch to the pitcher's arm side. (src: savant_csv_docs) |
| `api_break_x_batter_in` | double | yes | — | Break, in inches, of a pitch toward the batter's side of plate. (src: savant_csv_docs) |
| `attack_angle` | double | yes | — | Attack Angle measures the vertical angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to the ground. (src: savant_csv_docs) |
| `attack_direction` | double | yes | — | Attack Direction measures the horizontal angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to a line from home plate to straightaway center field. (src: savant_csv_docs) |
| `swing_path_tilt` | double | yes | — | The vertical angular orientation of the "plane" of the swing, as compared to the ground, defined by the path of the bat in the 40 ms prior to contact, which approximates a slice of a flat disc in shape. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_x_inches` | double | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the X (horizontal) direction. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_y_inches` | double | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the Y (mound-to-plate) direction. (src: savant_csv_docs) |
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
| `max_arm_strength` | double | yes | — | Arm strength is how hard, in miles per hour, a fielder throws the ball. (src: savant_csv_docs) |
| `arm_1b` | double | yes | — | TODO |
| `arm_2b` | double | yes | — | TODO |
| `arm_3b` | double | yes | — | TODO |
| `arm_ss` | double | yes | — | TODO |
| `arm_lf` | double | yes | — | TODO |
| `arm_cf` | double | yes | — | TODO |
| `arm_rf` | double | yes | — | TODO |
| `arm_inf` | double | yes | — | TODO |
| `arm_of` | double | yes | — | TODO |
| `arm_overall` | double | yes | — | Arm strength is how hard, in miles per hour, a fielder throws the ball. (src: savant_csv_docs) |
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
| `avg_bat_speed` | double | yes | — | Bat speed is measured at the sweet-spot of the bat. Average bat speed is the average of the top 90% of a player's swings. (src: savant_csv_docs) |
| `hard_swing_rate` | double | yes | — | TODO |
| `squared_up_per_bat_contact` | double | yes | — | Squared-up: how much exit velocity was obtained compared to the maximum possible exit velocity available. (src: savant_csv_docs) |
| `squared_up_per_swing` | double | yes | — | Squared-up: how much exit velocity was obtained compared to the maximum possible exit velocity available. (src: savant_csv_docs) |
| `blast_per_bat_contact` | double | yes | — | Blasts: batted balls that were both squared-up and hit with a fast swing. (src: savant_csv_docs) |
| `blast_per_swing` | double | yes | — | Blasts: batted balls that were both squared-up and hit with a fast swing. (src: savant_csv_docs) |
| `swing_length` | double | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `swords` | int16 | yes | — | A bat tracking metric that quantifies when a pitcher forces a batter to take a non-competitive, ugly-looking swing. (src: savant_csv_docs) |
| `batter_run_value` | double | yes | — | TODO |
| `whiffs` | int16 | yes | — | TODO |
| `whiff_per_swing` | double | yes | — | TODO |
| `batted_ball_events` | int16 | yes | — | A Batted Ball Event represents any batted ball that produces a result. (src: savant_csv_docs) |
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
| `bbe` | int16 | yes | — | A Batted Ball Event represents any batted ball that produces a result. (src: savant_csv_docs) |
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
| `rv_tot` | double | yes | — | TODO |
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
| `avg_hit_angle` | double | yes | — | Average launch angle: how high or low, in degrees, a ball was hit by a batter. (src: savant_csv_docs) |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | Average exit velocity: how fast, in miles per hour, a ball was hit by a batter. (src: savant_csv_docs) |
| `ev50` | double | yes | — | For a batter, EV50 is an average of the hardest 50% of his batted balls. (src: savant_csv_docs) |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `ev95percent` | double | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
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
| `avg_hit_angle` | double | yes | — | Average launch angle: how high or low, in degrees, a ball was hit by a batter. (src: savant_csv_docs) |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | Average exit velocity: how fast, in miles per hour, a ball was hit by a batter. (src: savant_csv_docs) |
| `ev50` | double | yes | — | For a batter, EV50 is an average of the hardest 50% of his batted balls. (src: savant_csv_docs) |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `ev95percent` | double | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
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
| `avg_hit_angle` | double | yes | — | Average launch angle: how high or low, in degrees, a ball was hit by a batter. (src: savant_csv_docs) |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | Average exit velocity: how fast, in miles per hour, a ball was hit by a batter. (src: savant_csv_docs) |
| `ev50` | double | yes | — | For a batter, EV50 is an average of the hardest 50% of his batted balls. (src: savant_csv_docs) |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `ev95percent` | double | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
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
| `avg_hit_angle` | double | yes | — | Average launch angle: how high or low, in degrees, a ball was hit by a batter. (src: savant_csv_docs) |
| `anglesweetspotpercent` | double | yes | — | Colloquially, a player who hits the ball solidly is said to have gotten the "sweet spot" of the bat on the ball. (src: mlb_glossary_sweet_spot) |
| `max_hit_speed` | double | yes | — | TODO |
| `avg_hit_speed` | double | yes | — | Average exit velocity: how fast, in miles per hour, a ball was hit by a batter. (src: savant_csv_docs) |
| `ev50` | double | yes | — | For a batter, EV50 is an average of the hardest 50% of his batted balls. (src: savant_csv_docs) |
| `fbld` | double | yes | — | TODO |
| `gb` | double | yes | — | TODO |
| `max_distance` | int16 | yes | — | TODO |
| `avg_distance` | int16 | yes | — | TODO |
| `avg_hr_distance` | int16 | yes | — | TODO |
| `ev95plus` | int16 | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `ev95percent` | double | yes | — | Hard-hit balls: Statcast defines a hard-hit ball as one hit with an exit velocity of 95 mph or higher. (src: savant_csv_docs) |
| `barrels` | int16 | yes | — | The Barrel classification is assigned to batted-ball events whose comparable hit types (in terms of exit velocity and launch angle) have led to a minimum .500 batting average and 1.500 slugging percentage since Statcast was implemented Major League wide in 2015. (src: mlb_glossary_barrel) |
| `brl_percent` | double | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
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
| `est_ba` | double | yes | — | xBA measures the likelihood that a batted ball will become a hit. (src: savant_csv_docs) |
| `est_ba_minus_ba_diff` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `est_slg` | double | yes | — | TODO |
| `est_slg_minus_slg_diff` | double | yes | — | TODO |
| `woba` | double | yes | — | TODO |
| `est_woba` | double | yes | — | xwOBA is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: savant_csv_docs) |
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
| `est_ba` | double | yes | — | xBA measures the likelihood that a batted ball will become a hit. (src: savant_csv_docs) |
| `est_ba_minus_ba_diff` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `est_slg` | double | yes | — | TODO |
| `est_slg_minus_slg_diff` | double | yes | — | TODO |
| `woba` | double | yes | — | TODO |
| `est_woba` | double | yes | — | xwOBA is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: savant_csv_docs) |
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
| `outs_above_average` | int16 | yes | — | A range-based metric of skill that shows how many outs a player has saved over his peers. (src: savant_csv_docs) |
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
| `outs_above_average` | int16 | yes | — | A range-based metric of skill that shows how many outs a player has saved over his peers. (src: savant_csv_docs) |
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
| `index_hardhit` | int16 | yes | — | TODO |
| `index_woba` | int16 | yes | — | TODO |
| `index_wobatto` | int16 | yes | — | TODO |
| `index_wobacon` | int16 | yes | — | TODO |
| `index_xwobacon` | int16 | yes | — | TODO |
| `index_xbacon` | int16 | yes | — | TODO |
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
| `brl` | int16 | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `brl_percent` | int16 | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `exit_velocity` | int16 | yes | — | TODO |
| `max_ev` | int16 | yes | — | TODO |
| `hard_hit_percent` | int16 | yes | — | Statcast defines a 'hard-hit ball' as one hit with an exit velocity of 95 mph or higher, and a player's "hard-hit rate" is simply showing the percentage of batted balls that were hit at 95 mph or more. (src: mlb_glossary_hard_hit_rate) |
| `k_percent` | int16 | yes | — | TODO |
| `bb_percent` | int16 | yes | — | TODO |
| `whiff_percent` | int16 | yes | — | TODO |
| `chase_percent` | int16 | yes | — | TODO |
| `arm_strength` | int16 | yes | — | On an individual play, Arm Strength is defined as the maximum velocity of any throw made by a fielder -- with the max velocity always being at the release point, due to physics. (src: mlb_glossary_arm_strength) |
| `sprint_speed` | int16 | yes | — | Introduced during the 2017 season, Sprint Speed is a Statcast metric that aims to more precisely quantify speed by measuring how many feet per second a player runs in his fastest one-second window. (src: mlb_glossary_sprint_speed) |
| `oaa` | int16 | yes | — | Outs Above Average (OAA) is a range-based metric of skill that shows how many outs a player has saved. (src: mlb_glossary_outs_above_average) |
| `bat_speed` | int16 | yes | — | Bat speed is measured at the sweet-spot of the bat. Average bat speed is the average of the top 90% of a player's swings. (src: savant_csv_docs) |
| `squared_up_rate` | int16 | yes | — | A swing’s squared-up rate tells us how much of the highest possible exit velocity available (based on the physics related to the swing speed and pitch speed) a batter was able to obtain – it is, at its simplest, how much exit velocity did you get as a share of how much exit velocity was possible based on your swing speed and the speed of the pitch. (src: mlb_glossary_squared_up) |
| `swing_length` | int16 | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
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
| `brl` | int16 | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `brl_percent` | int16 | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
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
| `est_ba` | double | yes | — | xBA measures the likelihood that a batted ball will become a hit. (src: savant_csv_docs) |
| `est_slg` | double | yes | — | TODO |
| `est_woba` | double | yes | — | xwOBA is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: savant_csv_docs) |
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
| `st_avg_speed` | double | yes | — | TODO |
| `sv_avg_speed` | double | yes | — | TODO |
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
| `avg_bat_speed` | double | yes | — | Bat speed is measured at the sweet-spot of the bat. Average bat speed is the average of the top 90% of a player's swings. (src: savant_csv_docs) |
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
| `total_runs` | double | yes | — | TODO |
| `inf_of_runs` | double | yes | — | TODO |
| `range_runs` | double | yes | — | TODO |
| `arm_runs` | double | yes | — | TODO |
| `dp_runs` | double | yes | — | TODO |
| `fielding_runs_prevented_on_rec1b` | double | yes | — | TODO |
| `catching_runs` | double | yes | — | TODO |
| `framing_runs` | double | yes | — | TODO |
| `throwing_runs` | double | yes | — | TODO |
| `blocking_runs` | double | yes | — | TODO |
| `abs_runs` | double | yes | — | TODO |
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
| `release_speed` | double | yes | — | Pitch velocity in MPH. Values from 2008-16 are via PitchFX, and adjusted to roughly out-of-hand release point. All velocities from 2017 and beyond are Statcast, which are reported out-of-hand. All velocities are thus on the same scale. (src: savant_csv_docs) |
| `effective_speed` | double | yes | — | Derived speed based on the the extension of the pitcher's release. (src: savant_csv_docs) |
| `release_spin_rate` | double | yes | — | TODO |
| `release_extension` | double | yes | — | Release extension of pitch in feet as tracked by Statcast. (src: savant_csv_docs) |
| `spin_axis` | double | yes | — | The Spin Axis in the 2D X-Z plane in degrees from 0 to 360, such that 180 represents a pure backspin fastball and 0 degrees represents a pure topspin (12-6) curveball (src: savant_csv_docs) |
| `release_pos_x` | double | yes | — | Horizontal Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_y` | double | yes | — | Release position of pitch measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `release_pos_z` | double | yes | — | Vertical Release Position of the ball measured in feet from the catcher's perspective. (src: savant_csv_docs) |
| `arm_angle` | double | yes | — | The angle between a line parallel to the ground and a l line extending from the location of the pitcher's throwing shoulder and the location of the ball at the time of the pitch. (src: savant_csv_docs) |
| `zone` | int8 | yes | — | Zone location of the ball when it crosses the plate from the catcher's perspective. (src: savant_csv_docs) |
| `plate_x` | double | yes | — | Horizontal position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `plate_z` | double | yes | — | Vertical position of the ball when it crosses home plate from the catcher's perspective. Through 2025, this was front-of-plate. From 2026 on, this is middle-of-plate to align with the ABS system. (src: savant_csv_docs) |
| `sz_top` | double | yes | — | Top of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, top of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the top of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `sz_bot` | double | yes | — | Bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. Through 2025, bottom of the batter's strike zone set by the operator when the ball is halfway to the plate. From 2026 on, this is the bottom of the batter's ABS-defined strike zone. (src: savant_csv_docs) |
| `pfx_x` | double | yes | — | Horizontal movement in feet from the catcher's perspective. (src: savant_csv_docs) |
| `pfx_z` | double | yes | — | Vertical movement in feet from the catcher's perpsective. (src: savant_csv_docs) |
| `vx0` | double | yes | — | The velocity of the pitch, in feet per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vy0` | double | yes | — | The velocity of the pitch, in feet per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `vz0` | double | yes | — | TODO |
| `ax` | double | yes | — | The acceleration of the pitch, in feet per second per second, in x-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `ay` | double | yes | — | The acceleration of the pitch, in feet per second per second, in y-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `az` | double | yes | — | The acceleration of the pitch, in feet per second per second, in z-dimension, determined at y=50 feet. (src: savant_csv_docs) |
| `stand` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Side of the plate batter is standing. (src: savant_csv_docs) |
| `p_throws` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Hand pitcher throws with. (src: savant_csv_docs) |
| `type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Short hand of pitch result. B = ball, S = strike, X = in play. (src: savant_csv_docs) |
| `events` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Event of the resulting Plate Appearance. (src: savant_csv_docs) |
| `description` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Description of the resulting pitch. (src: savant_csv_docs) |
| `des` | string | yes | — | Plate appearance description from game day. (src: savant_csv_docs) |
| `bb_type` | dictionary<values=string, indices=int8, ordered=0> | yes | — | Batted ball type, ground_ball, line_drive, fly_ball, popup. (src: savant_csv_docs) |
| `hit_location` | int8 | yes | — | Position of first fielder to touch the ball. (src: savant_csv_docs) |
| `launch_speed` | double | yes | — | Exit velocity of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_angle` | double | yes | — | Launch angle of the batted ball as tracked by Statcast. For the limited subset of batted balls not tracked directly, estimates are included based on the process described here . (src: savant_csv_docs) |
| `launch_speed_angle` | int8 | yes | — | Launch speed/angle zone based on launch angle and exit velocity. Weak Topped Under Flare/Burner Solid Contact Barrel (src: savant_csv_docs) |
| `hit_distance_sc` | double | yes | — | TODO |
| `hc_x` | double | yes | — | Hit coordinate X of batted ball. (src: savant_csv_docs) |
| `hc_y` | double | yes | — | Hit coordinate Y of batted ball. (src: savant_csv_docs) |
| `bat_speed` | double | yes | — | Bat speed is measured at the sweet-spot of the bat. Average bat speed is the average of the top 90% of a player's swings. (src: savant_csv_docs) |
| `swing_length` | double | yes | — | Swing length is a metric intended to identify if a batter has a short or long swing. (src: mlb_glossary_swing_length) |
| `estimated_ba_using_speedangle` | double | yes | — | Estimated Batting Avg based on launch angle and exit velocity. (src: savant_csv_docs) |
| `estimated_woba_using_speedangle` | double | yes | — | Estimated wOBA based on launch angle and exit velocity. (src: savant_csv_docs) |
| `woba_value` | double | yes | — | wOBA value based on result of play. (src: savant_csv_docs) |
| `woba_denom` | double | yes | — | wOBA denominator based on result of play. (src: savant_csv_docs) |
| `babip_value` | double | yes | — | BABIP value based on result of play. (src: savant_csv_docs) |
| `iso_value` | double | yes | — | ISO value based on result of play. (src: savant_csv_docs) |
| `delta_home_win_exp` | double | yes | — | The change in Win Expectancy before the Plate Appearance and after the Plate Appearance (src: savant_csv_docs) |
| `delta_run_exp` | double | yes | — | The change in Run Expectancy before the Pitch and after the Pitch (src: savant_csv_docs) |
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
| `miss_distance` | double | yes | — | TODO |
| `estimated_slg_using_speedangle` | double | yes | — | TODO |
| `delta_pitcher_run_exp` | double | yes | — | TODO |
| `hyper_speed` | double | yes | — | Savant display name: Adjusted EV. Adjusted Exit Velocity sets every batted ball hit below 88 mph as 88 mph, otherwise it uses the actual Exit Velocity (src: savant_csv_docs) |
| `home_score_diff` | int16 | yes | — | Home score minus Away score (src: savant_csv_docs) |
| `bat_score_diff` | int16 | yes | — | Batting team score less Pitching team score (src: savant_csv_docs) |
| `home_win_exp` | double | yes | — | Home team win expectancy (src: savant_csv_docs) |
| `bat_win_exp` | double | yes | — | Bat team win expectancy (src: savant_csv_docs) |
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
| `api_break_z_with_gravity` | double | yes | — | Vertical break with gravity included (src: savant_csv_docs) |
| `api_break_x_arm` | double | yes | — | Break, in inches, of a pitch to the pitcher's arm side. (src: savant_csv_docs) |
| `api_break_x_batter_in` | double | yes | — | Break, in inches, of a pitch toward the batter's side of plate. (src: savant_csv_docs) |
| `attack_angle` | double | yes | — | Attack Angle measures the vertical angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to the ground. (src: savant_csv_docs) |
| `attack_direction` | double | yes | — | Attack Direction measures the horizontal angle of the direction in which the sweet spot of the bat is traveling as it impacts the ball, as compared to a line from home plate to straightaway center field. (src: savant_csv_docs) |
| `swing_path_tilt` | double | yes | — | The vertical angular orientation of the "plane" of the swing, as compared to the ground, defined by the path of the bat in the 40 ms prior to contact, which approximates a slice of a flat disc in shape. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_x_inches` | double | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the X (horizontal) direction. (src: savant_csv_docs) |
| `intercept_ball_minus_batter_pos_y_inches` | double | yes | — | Distance, in inches, between the intercept point of the bat/ball and the batter's center of mass, in the Y (mound-to-plate) direction. (src: savant_csv_docs) |
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

<!-- BEGIN GENERATED:statcast.leaderboard_catcher_stance -->
### Dataset: leaderboard_catcher_stance

Catcher stance (knee and hand positions) per catcher-season.

- **View:** `statcast_leaderboard_catcher_stance`
- **Processed path:** `processed/statcast/leaderboard_catcher_stance/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `pitches` | int32 | yes | — | TODO |
| `knee_down_pct` | double | yes | — | TODO |
| `l_down_r_up_pct` | double | yes | — | TODO |
| `r_down_l_up_pct` | double | yes | — | TODO |
| `both_down_pct` | double | yes | — | TODO |
| `both_up_pct` | double | yes | — | TODO |
| `extended_leg_pct` | double | yes | — | TODO |
| `inside_down_pct` | double | yes | — | TODO |
| `outside_down_pct` | double | yes | — | TODO |
| `one_knee_framing_rv` | double | yes | — | TODO |
| `other_framing_rv` | double | yes | — | TODO |
| `one_knee_calledstr_pct` | double | yes | — | TODO |
| `other_calledstr_pct` | double | yes | — | TODO |
| `one_knee_blocking_rv` | double | yes | — | TODO |
| `other_blocking_rv` | double | yes | — | TODO |
| `one_knee_pbwp100` | double | yes | — | TODO |
| `other_pbwp100` | double | yes | — | TODO |
| `one_knee_throwing_rv` | double | yes | — | TODO |
| `other_throwing_rv` | double | yes | — | TODO |
| `one_knee_csaa100` | double | yes | — | TODO |
| `other_csaa100` | double | yes | — | TODO |
| `catching_rv` | double | yes | — | TODO |
| `one_knee_pitching_rv` | double | yes | — | TODO |
| `other_pitching_rv` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_catcher_stance -->

<!-- BEGIN GENERATED:statcast.leaderboard_catcher_throwing -->
### Dataset: leaderboard_catcher_throwing

Catcher throwing (stolen-base runs, caught stealing) per catcher.

- **View:** `statcast_leaderboard_catcher_throwing`
- **Processed path:** `processed/statcast/leaderboard_catcher_throwing/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | int32 | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `start_year` | int16 | yes | — | TODO |
| `end_year` | int16 | yes | — | TODO |
| `sb_attempts` | int16 | yes | — | TODO |
| `catcher_stealing_runs` | double | yes | — | TODO |
| `caught_stealing_above_average` | double | yes | — | TODO |
| `n_cs` | int16 | yes | — | TODO |
| `rate_cs` | double | yes | — | TODO |
| `est_cs_pct` | double | yes | — | TODO |
| `cs_aa_per_throw` | double | yes | — | TODO |
| `seasonal_runner_speed` | double | yes | — | TODO |
| `runner_distance_from_second` | double | yes | — | TODO |
| `pop_time` | double | yes | — | How quickly, in seconds, a catcher can get the ball out of his glove and to the base on a stolen base or pickoff attempt. (src: savant_csv_docs) |
| `exchange_time` | double | yes | — | TODO |
| `arm_strength` | double | yes | — | On an individual play, Arm Strength is defined as the maximum velocity of any throw made by a fielder -- with the max velocity always being at the release point, due to physics. (src: mlb_glossary_arm_strength) |
| `n_xcs_with_flight_over_xcs` | double | yes | — | TODO |
| `n_xcs_with_exchange_over_xcs` | double | yes | — | TODO |
| `n_xcs_with_accuracy_over_xcs` | double | yes | — | TODO |
| `n_xcs_with_ground_other_over_xcs` | double | yes | — | TODO |
| `n_xcs_with_onfly_other_over_xcs` | double | yes | — | TODO |
| `n_xcs_with_untracked_other_over_xcs` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_catcher_throwing -->

<!-- BEGIN GENERATED:statcast.leaderboard_first_base_receiving -->
### Dataset: leaderboard_first_base_receiving

First base scoops and receiving (outs above average on throws) per first baseman-season.

- **View:** `statcast_leaderboard_first_base_receiving`
- **Processed path:** `processed/statcast/leaderboard_first_base_receiving/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `fielder_3_hand` | string | yes | — | TODO |
| `height_in_inches` | int16 | yes | — | TODO |
| `n_outs` | int16 | yes | — | TODO |
| `n_plays` | int16 | yes | — | TODO |
| `total_oaa` | double | yes | — | TODO |
| `oaa_on_target` | double | yes | — | TODO |
| `oaa_bounce` | double | yes | — | TODO |
| `oaa_scoop` | double | yes | — | TODO |
| `oaa_low` | double | yes | — | TODO |
| `oaa_high` | double | yes | — | TODO |
| `oaa_wide` | double | yes | — | TODO |
| `n_on_target` | int16 | yes | — | TODO |
| `n_bounce` | int16 | yes | — | TODO |
| `n_scoop` | int16 | yes | — | TODO |
| `n_low` | int16 | yes | — | TODO |
| `n_high` | int16 | yes | — | TODO |
| `n_wide` | int16 | yes | — | TODO |
| `outs_on_target` | int16 | yes | — | TODO |
| `outs_bounce` | int16 | yes | — | TODO |
| `outs_scoop` | int16 | yes | — | TODO |
| `outs_low` | int16 | yes | — | TODO |
| `outs_high` | int16 | yes | — | TODO |
| `outs_wide` | int16 | yes | — | TODO |
| `avg_expected_rate_out` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_first_base_receiving -->

<!-- BEGIN GENERATED:statcast.leaderboard_hot_stove_batter -->
### Dataset: leaderboard_hot_stove_batter

Hot Stove leaderboard: batters of the season with Statcast batting metrics.

- **View:** `statcast_leaderboard_hot_stove_batter`
- **Processed path:** `processed/statcast/leaderboard_hot_stove_batter/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_name` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `yearhidden` | int16 | yes | — | TODO |
| `player_age` | int16 | yes | — | TODO |
| `ab` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `hit` | int16 | yes | — | TODO |
| `single` | int16 | yes | — | TODO |
| `double` | int16 | yes | — | TODO |
| `triple` | int16 | yes | — | TODO |
| `home_run` | int16 | yes | — | TODO |
| `strikeout` | int16 | yes | — | TODO |
| `walk` | int16 | yes | — | TODO |
| `k_percent` | double | yes | — | TODO |
| `bb_percent` | double | yes | — | TODO |
| `batting_avg` | double | yes | — | TODO |
| `slg_percent` | double | yes | — | TODO |
| `on_base_percent` | double | yes | — | TODO |
| `on_base_plus_slg` | double | yes | — | TODO |
| `isolated_power` | double | yes | — | TODO |
| `babip` | double | yes | — | TODO |
| `xba` | double | yes | — | Expected Batting Average (xBA) is a Statcast metric that measures the likelihood that a batted ball will become a hit. (src: mlb_glossary_expected_batting_average) |
| `xslg` | double | yes | — | Expected Slugging Percentage (xSLG) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_slugging_percentage) |
| `woba` | double | yes | — | TODO |
| `xwoba` | double | yes | — | Expected Weighted On-base Average (xwOBA) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_woba) |
| `xera` | string | yes | — | Expected ERA, or xERA, is a simple 1:1 translation of Expected Weighted On-Base Average (xwOBA), converted to the ERA scale. xwOBA takes into account the amount of contact (strikeouts, walks, hit by pitch) and the quality of that contact (exit velocity and launch angle), in an attempt to credit the pitcher or hitter for the moment of contact, not for what might happen to that contact thanks to other factors like ballpark, weather, or defense. (src: mlb_glossary_expected_era) |
| `xobp` | double | yes | — | TODO |
| `xiso` | double | yes | — | TODO |
| `wobacon` | double | yes | — | TODO |
| `xwobacon` | double | yes | — | TODO |
| `bacon` | double | yes | — | TODO |
| `xbacon` | double | yes | — | TODO |
| `xbadiff` | double | yes | — | TODO |
| `xslgdiff` | double | yes | — | TODO |
| `wobadiff` | double | yes | — | TODO |
| `exit_velocity_avg` | double | yes | — | Average exit velocity: how fast, in miles per hour, a ball was hit by a batter. (src: savant_csv_docs) |
| `launch_angle_avg` | double | yes | — | Average launch angle: how high or low, in degrees, a ball was hit by a batter. (src: savant_csv_docs) |
| `sweet_spot_percent` | double | yes | — | Launch angle sweet-spot: a batted-ball event with a launch angle between eight and 32 degrees. (src: savant_csv_docs) |
| `barrel` | int16 | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `barrel_batted_rate` | double | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `solidcontact_percent` | double | yes | — | TODO |
| `flareburner_percent` | double | yes | — | TODO |
| `poorlyunder_percent` | double | yes | — | TODO |
| `poorlytopped_percent` | double | yes | — | TODO |
| `poorlyweak_percent` | double | yes | — | TODO |
| `hard_hit_percent` | double | yes | — | Statcast defines a 'hard-hit ball' as one hit with an exit velocity of 95 mph or higher, and a player's "hard-hit rate" is simply showing the percentage of batted balls that were hit at 95 mph or more. (src: mlb_glossary_hard_hit_rate) |
| `avg_best_speed` | double | yes | — | TODO |
| `avg_hyper_speed` | double | yes | — | Adjusted EV averages the maximum of 88 and the actual exit velocity of each batted ball event. (src: savant_csv_docs) |
| `z_swing_percent` | double | yes | — | TODO |
| `z_swing_miss_percent` | double | yes | — | TODO |
| `oz_swing_percent` | double | yes | — | TODO |
| `oz_swing_miss_percent` | double | yes | — | TODO |
| `oz_contact_percent` | double | yes | — | TODO |
| `out_zone_swing_miss` | int16 | yes | — | TODO |
| `out_zone_swing` | int16 | yes | — | TODO |
| `out_zone_percent` | double | yes | — | TODO |
| `out_zone` | int16 | yes | — | TODO |
| `meatball_swing_percent` | double | yes | — | TODO |
| `meatball_percent` | double | yes | — | TODO |
| `pitch_count_offspeed` | int16 | yes | — | TODO |
| `pitch_count_fastball` | int16 | yes | — | TODO |
| `pitch_count_breaking` | int16 | yes | — | TODO |
| `pitch_count` | int16 | yes | — | TODO |
| `iz_contact_percent` | double | yes | — | TODO |
| `in_zone_swing_miss` | int16 | yes | — | TODO |
| `in_zone_swing` | int16 | yes | — | TODO |
| `in_zone_percent` | double | yes | — | TODO |
| `in_zone` | int16 | yes | — | TODO |
| `edge_percent` | double | yes | — | TODO |
| `edge` | int16 | yes | — | TODO |
| `whiff_percent` | double | yes | — | TODO |
| `swing_percent` | double | yes | — | TODO |
| `pull_percent` | double | yes | — | TODO |
| `straightaway_percent` | double | yes | — | TODO |
| `opposite_percent` | double | yes | — | TODO |
| `batted_ball` | int16 | yes | — | TODO |
| `f_strike_percent` | double | yes | — | TODO |
| `groundballs_percent` | double | yes | — | TODO |
| `groundballs` | int16 | yes | — | TODO |
| `flyballs_percent` | double | yes | — | TODO |
| `flyballs` | int16 | yes | — | TODO |
| `linedrives_percent` | double | yes | — | TODO |
| `linedrives` | int16 | yes | — | TODO |
| `popups_percent` | double | yes | — | TODO |
| `popups` | int16 | yes | — | TODO |
| `avg_swing_length` | double | yes | — | Swing length is the total (sum) distance in feet traveled by the head of the bat. (src: savant_csv_docs) |
| `avg_swing_speed` | double | yes | — | TODO |
| `blasts_contact` | double | yes | — | Blasts: batted balls that were both squared-up and hit with a fast swing. (src: savant_csv_docs) |
| `blasts_swing` | double | yes | — | Blasts: batted balls that were both squared-up and hit with a fast swing. (src: savant_csv_docs) |
| `squared_up_contact` | double | yes | — | Squared-up: how much exit velocity was obtained compared to the maximum possible exit velocity available. (src: savant_csv_docs) |
| `squared_up_swing` | double | yes | — | Squared-up: how much exit velocity was obtained compared to the maximum possible exit velocity available. (src: savant_csv_docs) |
| `swords` | int16 | yes | — | A bat tracking metric that quantifies when a pitcher forces a batter to take a non-competitive, ugly-looking swing. (src: savant_csv_docs) |
| `fast_swing_rate` | double | yes | — | A fast swing is one that has 75 MPH or more of bat speed. (src: savant_csv_docs) |
| `attack_angle` | double | yes | — | Attack angle measures the vertical direction that the sweet spot of the bat is traveling at the moment it hits the baseball. (src: mlb_glossary_attack_angle) |
| `attack_direction` | double | yes | — | Attack direction measures the horizontal direction that the sweet spot of the bat is moving at the point of contact with the baseball (or the point the bat and ball cross paths on a swing-and-miss). (src: mlb_glossary_attack_direction) |
| `ideal_angle_rate` | double | yes | — | Ideal attack angle is when a ball is hit with a 5-20 degree attack angle. (src: savant_csv_docs) |
| `vertical_swing_path` | double | yes | — | TODO |
| `swing_take_run_value` | int16 | yes | — | TODO |
| `runner_run_value` | int16 | yes | — | TODO |
| `fielding_run_value` | int16 | yes | — | Statcast's overall metric for capturing a player's measurable defensive performance onto a run-based scale. (src: savant_csv_docs) |
| `pitch_run_value_fastball` | double | yes | — | TODO |
| `pitch_run_value_breaking` | double | yes | — | TODO |
| `pitch_run_value_offspeed` | double | yes | — | TODO |
| `b_total_pa` | int16 | yes | — | TODO |
| `b_rbi` | int16 | yes | — | TODO |
| `b_lob` | int16 | yes | — | TODO |
| `b_total_bases` | int16 | yes | — | TODO |
| `r_total_caught_stealing` | int16 | yes | — | TODO |
| `r_total_stolen_base` | int16 | yes | — | TODO |
| `b_ab_scoring` | int16 | yes | — | TODO |
| `b_ball` | int16 | yes | — | TODO |
| `b_called_strike` | int16 | yes | — | TODO |
| `b_catcher_interf` | int16 | yes | — | TODO |
| `b_foul` | int16 | yes | — | TODO |
| `b_foul_tip` | int16 | yes | — | TODO |
| `b_game` | int16 | yes | — | TODO |
| `b_gnd_into_dp` | int16 | yes | — | TODO |
| `b_gnd_into_tp` | int16 | yes | — | TODO |
| `b_gnd_rule_double` | int16 | yes | — | TODO |
| `b_hit_by_pitch` | int16 | yes | — | TODO |
| `b_hit_ground` | int16 | yes | — | TODO |
| `b_hit_fly` | int16 | yes | — | TODO |
| `b_hit_into_play` | int16 | yes | — | TODO |
| `b_hit_line_drive` | int16 | yes | — | TODO |
| `b_hit_popup` | int16 | yes | — | TODO |
| `b_out_fly` | int16 | yes | — | TODO |
| `b_out_ground` | int16 | yes | — | TODO |
| `b_out_line_drive` | int16 | yes | — | TODO |
| `b_out_popup` | int16 | yes | — | TODO |
| `b_intent_ball` | int16 | yes | — | TODO |
| `b_intent_walk` | int16 | yes | — | TODO |
| `b_interference` | int16 | yes | — | TODO |
| `b_pinch_hit` | int16 | yes | — | TODO |
| `b_pinch_run` | int16 | yes | — | TODO |
| `b_pitchout` | int16 | yes | — | TODO |
| `b_played_dh` | int16 | yes | — | TODO |
| `b_sac_bunt` | int16 | yes | — | TODO |
| `b_sac_fly` | int16 | yes | — | TODO |
| `b_swinging_strike` | int16 | yes | — | TODO |
| `r_caught_stealing_2b` | int16 | yes | — | TODO |
| `r_caught_stealing_3b` | int16 | yes | — | TODO |
| `r_caught_stealing_home` | int16 | yes | — | TODO |
| `r_defensive_indiff` | int16 | yes | — | TODO |
| `r_interference` | int16 | yes | — | TODO |
| `r_pickoff_1b` | int16 | yes | — | TODO |
| `r_pickoff_2b` | int16 | yes | — | TODO |
| `r_pickoff_3b` | int16 | yes | — | TODO |
| `r_run` | int16 | yes | — | TODO |
| `r_stolen_base_2b` | int16 | yes | — | TODO |
| `r_stolen_base_3b` | int16 | yes | — | TODO |
| `r_stolen_base_home` | int16 | yes | — | TODO |
| `b_total_ball` | int16 | yes | — | TODO |
| `b_total_sacrifices` | int16 | yes | — | TODO |
| `b_total_strike` | int16 | yes | — | TODO |
| `b_total_swinging_strike` | int16 | yes | — | TODO |
| `b_total_pitches` | int16 | yes | — | TODO |
| `r_stolen_base_pct` | string | yes | — | TODO |
| `r_total_pickoff` | int16 | yes | — | TODO |
| `b_reached_on_error` | int16 | yes | — | TODO |
| `b_walkoff` | int16 | yes | — | TODO |
| `b_reached_on_int` | int16 | yes | — | TODO |
| `pop_2b_sba_count` | int16 | yes | — | TODO |
| `pop_2b_sba` | double | yes | — | TODO |
| `pop_2b_sb` | double | yes | — | TODO |
| `pop_2b_cs` | double | yes | — | TODO |
| `pop_3b_sba_count` | int16 | yes | — | TODO |
| `pop_3b_sba` | double | yes | — | TODO |
| `pop_3b_sb` | double | yes | — | TODO |
| `pop_3b_cs` | double | yes | — | TODO |
| `exchange_2b_3b_sba` | double | yes | — | TODO |
| `maxeff_arm_2b_3b_sba` | double | yes | — | TODO |
| `n_outs_above_average` | int16 | yes | — | TODO |
| `n_fieldout_5stars` | int16 | yes | — | TODO |
| `n_opp_5stars` | int16 | yes | — | TODO |
| `n_5star_percent` | double | yes | — | TODO |
| `n_fieldout_4stars` | int16 | yes | — | TODO |
| `n_opp_4stars` | int16 | yes | — | TODO |
| `n_4star_percent` | double | yes | — | TODO |
| `n_fieldout_3stars` | int16 | yes | — | TODO |
| `n_opp_3stars` | int16 | yes | — | TODO |
| `n_3star_percent` | double | yes | — | TODO |
| `n_opp_2stars` | int16 | yes | — | TODO |
| `n_2star_percent` | double | yes | — | TODO |
| `n_fieldout_2stars` | int16 | yes | — | TODO |
| `n_1star_percent` | double | yes | — | TODO |
| `n_fieldout_1stars` | int16 | yes | — | TODO |
| `n_opp_1stars` | int16 | yes | — | TODO |
| `rel_league_reaction_distance` | double | yes | — | TODO |
| `rel_league_burst_distance` | double | yes | — | TODO |
| `rel_league_routing_distance` | double | yes | — | TODO |
| `rel_league_bootup_distance` | double | yes | — | TODO |
| `f_bootup_distance` | double | yes | — | TODO |
| `n_bolts` | int16 | yes | — | TODO |
| `hp_to_1b` | double | yes | — | TODO |
| `sprint_speed` | double | yes | — | Introduced during the 2017 season, Sprint Speed is a Statcast metric that aims to more precisely quantify speed by measuring how many feet per second a player runs in his fastest one-second window. (src: mlb_glossary_sprint_speed) |
| `p_formatted_ip` | int16 | yes | — | TODO |
| `p_game` | int16 | yes | — | TODO |
| `stats_api` | string | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `original_team_id` | int16 | yes | — | TODO |
| `new_team_id` | int32 | yes | — | TODO |
| `diff_team` | string | yes | — | TODO |
| `original_team_abbrev` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `bat_side` | string | yes | — | TODO |
| `pitch_hand` | string | yes | — | TODO |
| `current_age` | int16 | yes | — | TODO |
| `notes` | string | yes | — | TODO |
| `transaction_type` | string | yes | — | TODO |
| `home_runs_per_nine` | string | yes | — | TODO |
| `home_run_percent` | double | yes | — | TODO |
| `new_team_abbrev` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_hot_stove_batter -->

<!-- BEGIN GENERATED:statcast.leaderboard_hot_stove_pitcher -->
### Dataset: leaderboard_hot_stove_pitcher

Hot Stove leaderboard: pitchers of the season with Statcast pitching metrics.

- **View:** `statcast_leaderboard_hot_stove_pitcher`
- **Processed path:** `processed/statcast/leaderboard_hot_stove_pitcher/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `player_id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_name` | string | yes | — | TODO |
| `player_id` | int32 | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `yearhidden` | int16 | yes | — | TODO |
| `player_age` | int16 | yes | — | TODO |
| `ab` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `hit` | int16 | yes | — | TODO |
| `single` | int16 | yes | — | TODO |
| `double` | int16 | yes | — | TODO |
| `triple` | int16 | yes | — | TODO |
| `home_run` | int16 | yes | — | TODO |
| `strikeout` | int16 | yes | — | TODO |
| `walk` | int16 | yes | — | TODO |
| `k_percent` | double | yes | — | TODO |
| `bb_percent` | double | yes | — | TODO |
| `batting_avg` | double | yes | — | TODO |
| `slg_percent` | double | yes | — | TODO |
| `on_base_percent` | double | yes | — | TODO |
| `on_base_plus_slg` | double | yes | — | TODO |
| `isolated_power` | double | yes | — | TODO |
| `babip` | double | yes | — | TODO |
| `xba` | double | yes | — | Expected Batting Average (xBA) is a Statcast metric that measures the likelihood that a batted ball will become a hit. (src: mlb_glossary_expected_batting_average) |
| `xslg` | double | yes | — | Expected Slugging Percentage (xSLG) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_slugging_percentage) |
| `woba` | double | yes | — | TODO |
| `xwoba` | double | yes | — | Expected Weighted On-base Average (xwOBA) is formulated using exit velocity, launch angle and, on certain types of batted balls, Sprint Speed. (src: mlb_glossary_expected_woba) |
| `xera` | double | yes | — | Expected ERA, or xERA, is a simple 1:1 translation of Expected Weighted On-Base Average (xwOBA), converted to the ERA scale. xwOBA takes into account the amount of contact (strikeouts, walks, hit by pitch) and the quality of that contact (exit velocity and launch angle), in an attempt to credit the pitcher or hitter for the moment of contact, not for what might happen to that contact thanks to other factors like ballpark, weather, or defense. (src: mlb_glossary_expected_era) |
| `xobp` | double | yes | — | TODO |
| `xiso` | double | yes | — | TODO |
| `wobacon` | double | yes | — | TODO |
| `xwobacon` | double | yes | — | TODO |
| `bacon` | double | yes | — | TODO |
| `xbacon` | double | yes | — | TODO |
| `xbadiff` | double | yes | — | TODO |
| `xslgdiff` | double | yes | — | TODO |
| `wobadiff` | double | yes | — | TODO |
| `exit_velocity_avg` | double | yes | — | Average exit velocity: how fast, in miles per hour, a ball was hit by a batter. (src: savant_csv_docs) |
| `launch_angle_avg` | double | yes | — | Average launch angle: how high or low, in degrees, a ball was hit by a batter. (src: savant_csv_docs) |
| `sweet_spot_percent` | double | yes | — | Launch angle sweet-spot: a batted-ball event with a launch angle between eight and 32 degrees. (src: savant_csv_docs) |
| `barrel` | int16 | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `barrel_batted_rate` | double | yes | — | Barrels: a batted ball with the perfect combination of exit velocity and launch angle. (src: savant_csv_docs) |
| `solidcontact_percent` | double | yes | — | TODO |
| `flareburner_percent` | double | yes | — | TODO |
| `poorlyunder_percent` | double | yes | — | TODO |
| `poorlytopped_percent` | double | yes | — | TODO |
| `poorlyweak_percent` | double | yes | — | TODO |
| `hard_hit_percent` | double | yes | — | Statcast defines a 'hard-hit ball' as one hit with an exit velocity of 95 mph or higher, and a player's "hard-hit rate" is simply showing the percentage of batted balls that were hit at 95 mph or more. (src: mlb_glossary_hard_hit_rate) |
| `avg_best_speed` | double | yes | — | TODO |
| `avg_hyper_speed` | double | yes | — | Adjusted EV averages the maximum of 88 and the actual exit velocity of each batted ball event. (src: savant_csv_docs) |
| `z_swing_percent` | double | yes | — | TODO |
| `z_swing_miss_percent` | double | yes | — | TODO |
| `oz_swing_percent` | double | yes | — | TODO |
| `oz_swing_miss_percent` | double | yes | — | TODO |
| `oz_contact_percent` | double | yes | — | TODO |
| `out_zone_swing_miss` | int16 | yes | — | TODO |
| `out_zone_swing` | int16 | yes | — | TODO |
| `out_zone_percent` | double | yes | — | TODO |
| `out_zone` | int16 | yes | — | TODO |
| `meatball_swing_percent` | double | yes | — | TODO |
| `meatball_percent` | double | yes | — | TODO |
| `pitch_count_offspeed` | int16 | yes | — | TODO |
| `pitch_count_fastball` | int16 | yes | — | TODO |
| `pitch_count_breaking` | int16 | yes | — | TODO |
| `pitch_count` | int16 | yes | — | TODO |
| `iz_contact_percent` | double | yes | — | TODO |
| `in_zone_swing_miss` | int16 | yes | — | TODO |
| `in_zone_swing` | int16 | yes | — | TODO |
| `in_zone_percent` | double | yes | — | TODO |
| `in_zone` | int16 | yes | — | TODO |
| `edge_percent` | double | yes | — | TODO |
| `edge` | int16 | yes | — | TODO |
| `whiff_percent` | double | yes | — | TODO |
| `swing_percent` | double | yes | — | TODO |
| `pull_percent` | double | yes | — | TODO |
| `straightaway_percent` | double | yes | — | TODO |
| `opposite_percent` | double | yes | — | TODO |
| `batted_ball` | int16 | yes | — | TODO |
| `f_strike_percent` | double | yes | — | TODO |
| `groundballs_percent` | double | yes | — | TODO |
| `groundballs` | int16 | yes | — | TODO |
| `flyballs_percent` | double | yes | — | TODO |
| `flyballs` | int16 | yes | — | TODO |
| `linedrives_percent` | double | yes | — | TODO |
| `linedrives` | int16 | yes | — | TODO |
| `popups_percent` | double | yes | — | TODO |
| `popups` | int16 | yes | — | TODO |
| `avg_swing_length` | double | yes | — | Swing length is the total (sum) distance in feet traveled by the head of the bat. (src: savant_csv_docs) |
| `avg_swing_speed` | double | yes | — | TODO |
| `blasts_contact` | double | yes | — | Blasts: batted balls that were both squared-up and hit with a fast swing. (src: savant_csv_docs) |
| `blasts_swing` | double | yes | — | Blasts: batted balls that were both squared-up and hit with a fast swing. (src: savant_csv_docs) |
| `squared_up_contact` | double | yes | — | Squared-up: how much exit velocity was obtained compared to the maximum possible exit velocity available. (src: savant_csv_docs) |
| `squared_up_swing` | double | yes | — | Squared-up: how much exit velocity was obtained compared to the maximum possible exit velocity available. (src: savant_csv_docs) |
| `swords` | int16 | yes | — | A bat tracking metric that quantifies when a pitcher forces a batter to take a non-competitive, ugly-looking swing. (src: savant_csv_docs) |
| `fast_swing_rate` | double | yes | — | A fast swing is one that has 75 MPH or more of bat speed. (src: savant_csv_docs) |
| `attack_angle` | double | yes | — | Attack angle measures the vertical direction that the sweet spot of the bat is traveling at the moment it hits the baseball. (src: mlb_glossary_attack_angle) |
| `attack_direction` | double | yes | — | Attack direction measures the horizontal direction that the sweet spot of the bat is moving at the point of contact with the baseball (or the point the bat and ball cross paths on a swing-and-miss). (src: mlb_glossary_attack_direction) |
| `ideal_angle_rate` | double | yes | — | Ideal attack angle is when a ball is hit with a 5-20 degree attack angle. (src: savant_csv_docs) |
| `vertical_swing_path` | double | yes | — | TODO |
| `swing_take_run_value` | int16 | yes | — | TODO |
| `runner_run_value` | string | yes | — | TODO |
| `fielding_run_value` | string | yes | — | Statcast's overall metric for capturing a player's measurable defensive performance onto a run-based scale. (src: savant_csv_docs) |
| `pitch_run_value_fastball` | double | yes | — | TODO |
| `pitch_run_value_breaking` | double | yes | — | TODO |
| `pitch_run_value_offspeed` | double | yes | — | TODO |
| `p_game` | int16 | yes | — | TODO |
| `p_total_pa` | int16 | yes | — | TODO |
| `p_ab` | int16 | yes | — | TODO |
| `p_total_hits` | int16 | yes | — | TODO |
| `p_single` | int16 | yes | — | TODO |
| `p_double` | int16 | yes | — | TODO |
| `p_triple` | int16 | yes | — | TODO |
| `p_home_run` | int16 | yes | — | TODO |
| `p_strikeout` | int16 | yes | — | TODO |
| `p_walk` | int16 | yes | — | TODO |
| `p_earned_run` | int16 | yes | — | TODO |
| `p_run` | int16 | yes | — | TODO |
| `p_save` | int16 | yes | — | TODO |
| `p_blown_save` | int16 | yes | — | TODO |
| `p_out` | int16 | yes | — | TODO |
| `p_win` | int16 | yes | — | TODO |
| `p_loss` | int16 | yes | — | TODO |
| `p_wild_pitch` | int16 | yes | — | TODO |
| `p_balk` | int16 | yes | — | TODO |
| `p_shutout` | int16 | yes | — | TODO |
| `p_opp_batting_avg` | string | yes | — | TODO |
| `p_opp_on_base_avg` | string | yes | — | TODO |
| `p_total_stolen_base` | int16 | yes | — | TODO |
| `p_pickoff_attempt_1b` | int16 | yes | — | TODO |
| `p_pickoff_attempt_2b` | int16 | yes | — | TODO |
| `p_pickoff_attempt_3b` | int16 | yes | — | TODO |
| `p_pickoff_1b` | int16 | yes | — | TODO |
| `p_pickoff_2b` | int16 | yes | — | TODO |
| `p_pickoff_3b` | int16 | yes | — | TODO |
| `p_lob` | int16 | yes | — | TODO |
| `p_rbi` | int16 | yes | — | TODO |
| `p_stolen_base_2b` | int16 | yes | — | TODO |
| `p_stolen_base_3b` | int16 | yes | — | TODO |
| `p_stolen_base_home` | int16 | yes | — | TODO |
| `p_quality_start` | int16 | yes | — | TODO |
| `p_walkoff` | int16 | yes | — | TODO |
| `p_run_support` | int16 | yes | — | TODO |
| `p_ab_scoring` | int16 | yes | — | TODO |
| `p_automatic_ball` | int16 | yes | — | TODO |
| `p_ball` | int16 | yes | — | TODO |
| `p_called_strike` | int16 | yes | — | TODO |
| `p_catcher_interf` | int16 | yes | — | TODO |
| `p_caught_stealing_2b` | int16 | yes | — | TODO |
| `p_caught_stealing_3b` | int16 | yes | — | TODO |
| `p_caught_stealing_home` | int16 | yes | — | TODO |
| `p_complete_game` | int16 | yes | — | TODO |
| `p_defensive_indiff` | int16 | yes | — | TODO |
| `p_foul` | int16 | yes | — | TODO |
| `p_foul_tip` | int16 | yes | — | TODO |
| `p_game_finished` | int16 | yes | — | TODO |
| `p_game_in_relief` | int16 | yes | — | TODO |
| `p_gnd_into_dp` | int16 | yes | — | TODO |
| `p_gnd_into_tp` | int16 | yes | — | TODO |
| `p_gnd_rule_double` | int16 | yes | — | TODO |
| `p_hit_by_pitch` | int16 | yes | — | TODO |
| `p_hit_fly` | int16 | yes | — | TODO |
| `p_hit_ground` | int16 | yes | — | TODO |
| `p_hit_line_drive` | int16 | yes | — | TODO |
| `p_hit_into_play` | int16 | yes | — | TODO |
| `p_hit_scoring` | int16 | yes | — | TODO |
| `p_hold` | int16 | yes | — | TODO |
| `p_intent_ball` | int16 | yes | — | TODO |
| `p_intent_walk` | int16 | yes | — | TODO |
| `p_missed_bunt` | int16 | yes | — | TODO |
| `p_out_fly` | int16 | yes | — | TODO |
| `p_out_ground` | int16 | yes | — | TODO |
| `p_out_line_drive` | int16 | yes | — | TODO |
| `p_passed_ball` | int16 | yes | — | TODO |
| `p_pickoff_error_1b` | int16 | yes | — | TODO |
| `p_pickoff_error_2b` | int16 | yes | — | TODO |
| `p_pickoff_error_3b` | int16 | yes | — | TODO |
| `p_pitchout` | int16 | yes | — | TODO |
| `p_relief_no_out` | int16 | yes | — | TODO |
| `p_sac_bunt` | int16 | yes | — | TODO |
| `p_sac_fly` | int16 | yes | — | TODO |
| `p_starting_p` | int16 | yes | — | TODO |
| `p_swinging_strike` | int16 | yes | — | TODO |
| `p_unearned_run` | int16 | yes | — | TODO |
| `p_total_ball` | int16 | yes | — | TODO |
| `p_total_bases` | int16 | yes | — | TODO |
| `p_total_caught_stealing` | int16 | yes | — | TODO |
| `p_total_pickoff` | int16 | yes | — | TODO |
| `p_total_pickoff_attempt` | int16 | yes | — | TODO |
| `p_total_pickoff_error` | int16 | yes | — | TODO |
| `p_total_pitches` | int16 | yes | — | TODO |
| `p_total_sacrifices` | int16 | yes | — | TODO |
| `p_total_strike` | int16 | yes | — | TODO |
| `p_total_swinging_strike` | int16 | yes | — | TODO |
| `p_inh_runner` | int16 | yes | — | TODO |
| `p_inh_runner_scored` | int16 | yes | — | TODO |
| `p_beq_runner` | int16 | yes | — | TODO |
| `p_beq_runner_scored` | int16 | yes | — | TODO |
| `p_reached_on_error` | int16 | yes | — | TODO |
| `p_formatted_ip` | double | yes | — | TODO |
| `p_era` | double | yes | — | TODO |
| `pitch_hand` | string | yes | — | TODO |
| `n` | int16 | yes | — | TODO |
| `n_ff_formatted` | double | yes | — | TODO |
| `ff_avg_speed` | double | yes | — | TODO |
| `ff_avg_spin` | int16 | yes | — | TODO |
| `ff_avg_break_x` | double | yes | — | TODO |
| `ff_avg_break_z` | double | yes | — | TODO |
| `ff_avg_break_z_induced` | double | yes | — | TODO |
| `ff_avg_break` | double | yes | — | TODO |
| `ff_range_speed` | double | yes | — | TODO |
| `n_sl_formatted` | double | yes | — | TODO |
| `sl_avg_speed` | double | yes | — | TODO |
| `sl_avg_spin` | int16 | yes | — | TODO |
| `sl_avg_break_x` | double | yes | — | TODO |
| `sl_avg_break_z` | double | yes | — | TODO |
| `sl_avg_break_z_induced` | double | yes | — | TODO |
| `sl_avg_break` | double | yes | — | TODO |
| `sl_range_speed` | double | yes | — | TODO |
| `n_ch_formatted` | double | yes | — | TODO |
| `ch_avg_speed` | double | yes | — | TODO |
| `ch_avg_spin` | int16 | yes | — | TODO |
| `ch_avg_break_x` | double | yes | — | TODO |
| `ch_avg_break_z` | double | yes | — | TODO |
| `ch_avg_break_z_induced` | double | yes | — | TODO |
| `ch_avg_break` | double | yes | — | TODO |
| `ch_range_speed` | double | yes | — | TODO |
| `n_cu_formatted` | double | yes | — | TODO |
| `cu_avg_speed` | double | yes | — | TODO |
| `cu_avg_spin` | int16 | yes | — | TODO |
| `cu_avg_break_x` | double | yes | — | TODO |
| `cu_avg_break_z` | double | yes | — | TODO |
| `cu_avg_break_z_induced` | double | yes | — | TODO |
| `cu_avg_break` | double | yes | — | TODO |
| `cu_range_speed` | double | yes | — | TODO |
| `n_si_formatted` | double | yes | — | TODO |
| `si_avg_speed` | double | yes | — | TODO |
| `si_avg_spin` | int16 | yes | — | TODO |
| `si_avg_break_x` | double | yes | — | TODO |
| `si_avg_break_z` | double | yes | — | TODO |
| `si_avg_break_z_induced` | double | yes | — | TODO |
| `si_avg_break` | double | yes | — | TODO |
| `si_range_speed` | double | yes | — | TODO |
| `n_fc_formatted` | double | yes | — | TODO |
| `fc_avg_speed` | double | yes | — | TODO |
| `fc_avg_spin` | int16 | yes | — | TODO |
| `fc_avg_break_x` | double | yes | — | TODO |
| `fc_avg_break_z` | double | yes | — | TODO |
| `fc_avg_break_z_induced` | double | yes | — | TODO |
| `fc_avg_break` | double | yes | — | TODO |
| `fc_range_speed` | double | yes | — | TODO |
| `n_fs_formatted` | double | yes | — | TODO |
| `fs_avg_speed` | double | yes | — | TODO |
| `fs_avg_spin` | int16 | yes | — | TODO |
| `fs_avg_break_x` | double | yes | — | TODO |
| `fs_avg_break_z` | double | yes | — | TODO |
| `fs_avg_break_z_induced` | double | yes | — | TODO |
| `fs_avg_break` | double | yes | — | TODO |
| `fs_range_speed` | double | yes | — | TODO |
| `n_kn_formatted` | string | yes | — | TODO |
| `kn_avg_speed` | string | yes | — | TODO |
| `kn_avg_spin` | string | yes | — | TODO |
| `kn_avg_break_x` | string | yes | — | TODO |
| `kn_avg_break_z` | string | yes | — | TODO |
| `kn_avg_break_z_induced` | string | yes | — | TODO |
| `kn_avg_break` | string | yes | — | TODO |
| `kn_range_speed` | string | yes | — | TODO |
| `n_st_formatted` | double | yes | — | TODO |
| `st_avg_speed` | double | yes | — | TODO |
| `st_avg_spin` | int16 | yes | — | TODO |
| `st_avg_break_x` | double | yes | — | TODO |
| `st_avg_break_z` | double | yes | — | TODO |
| `st_avg_break_z_induced` | double | yes | — | TODO |
| `st_avg_break` | double | yes | — | TODO |
| `st_range_speed` | double | yes | — | TODO |
| `n_sv_formatted` | double | yes | — | TODO |
| `sv_avg_speed` | double | yes | — | TODO |
| `sv_avg_spin` | int16 | yes | — | TODO |
| `sv_avg_break_x` | double | yes | — | TODO |
| `sv_avg_break_z` | double | yes | — | TODO |
| `sv_avg_break_z_induced` | double | yes | — | TODO |
| `sv_avg_break` | double | yes | — | TODO |
| `sv_range_speed` | double | yes | — | TODO |
| `n_fo_formatted` | string | yes | — | TODO |
| `fo_avg_speed` | string | yes | — | TODO |
| `fo_avg_spin` | string | yes | — | TODO |
| `fo_avg_break_x` | string | yes | — | TODO |
| `fo_avg_break_z` | string | yes | — | TODO |
| `fo_avg_break_z_induced` | string | yes | — | TODO |
| `fo_avg_break` | string | yes | — | TODO |
| `fo_range_speed` | string | yes | — | TODO |
| `n_sc_formatted` | string | yes | — | TODO |
| `sc_avg_speed` | string | yes | — | TODO |
| `sc_avg_spin` | string | yes | — | TODO |
| `sc_avg_break_x` | string | yes | — | TODO |
| `sc_avg_break_z` | string | yes | — | TODO |
| `sc_avg_break_z_induced` | string | yes | — | TODO |
| `sc_avg_break` | string | yes | — | TODO |
| `sc_range_speed` | string | yes | — | TODO |
| `n_fastball_formatted` | double | yes | — | TODO |
| `fastball_avg_speed` | double | yes | — | TODO |
| `fastball_avg_spin` | int16 | yes | — | TODO |
| `fastball_avg_break_x` | double | yes | — | TODO |
| `fastball_avg_break_z` | double | yes | — | TODO |
| `fastball_avg_break_z_induced` | double | yes | — | TODO |
| `fastball_avg_break` | double | yes | — | TODO |
| `fastball_range_speed` | double | yes | — | TODO |
| `n_breaking_formatted` | double | yes | — | TODO |
| `breaking_avg_speed` | double | yes | — | TODO |
| `breaking_avg_spin` | int16 | yes | — | TODO |
| `breaking_avg_break_x` | double | yes | — | TODO |
| `breaking_avg_break_z` | double | yes | — | TODO |
| `breaking_avg_break_z_induced` | double | yes | — | TODO |
| `breaking_avg_break` | double | yes | — | TODO |
| `breaking_range_speed` | double | yes | — | TODO |
| `n_offspeed_formatted` | double | yes | — | TODO |
| `offspeed_avg_speed` | double | yes | — | TODO |
| `offspeed_avg_spin` | int16 | yes | — | TODO |
| `offspeed_avg_break_x` | double | yes | — | TODO |
| `offspeed_avg_break_z` | double | yes | — | TODO |
| `offspeed_avg_break_z_induced` | double | yes | — | TODO |
| `offspeed_avg_break` | double | yes | — | TODO |
| `offspeed_range_speed` | double | yes | — | TODO |
| `arm_angle` | double | yes | — | TODO |
| `stats_api` | string | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `original_team_id` | int16 | yes | — | TODO |
| `new_team_id` | int32 | yes | — | TODO |
| `diff_team` | string | yes | — | TODO |
| `original_team_abbrev` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `bat_side` | string | yes | — | TODO |
| `current_age` | int16 | yes | — | TODO |
| `transaction_type` | string | yes | — | TODO |
| `home_runs_per_nine` | double | yes | — | TODO |
| `home_run_percent` | double | yes | — | TODO |
| `notes` | string | yes | — | TODO |
| `new_team_abbrev` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_hot_stove_pitcher -->

<!-- BEGIN GENERATED:statcast.leaderboard_outfield_directional_oaa -->
### Dataset: leaderboard_outfield_directional_oaa

Outfield outs above average by direction of the batted ball per outfielder-season.

- **View:** `statcast_leaderboard_outfield_directional_oaa`
- **Processed path:** `processed/statcast/leaderboard_outfield_directional_oaa/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `last_name_first_name` | string | yes | `last_name, first_name` | TODO |
| `player_id` | int32 | yes | — | TODO |
| `attempts` | int16 | yes | — | TODO |
| `n_outs_above_average` | int16 | yes | — | TODO |
| `n_oaa_slice_back_left` | int16 | yes | — | TODO |
| `n_oaa_slice_back` | int16 | yes | — | TODO |
| `n_oaa_slice_back_right` | int16 | yes | — | TODO |
| `n_oaa_slice_back_all` | int16 | yes | — | TODO |
| `n_oaa_slice_in_left` | int16 | yes | — | TODO |
| `n_oaa_slice_in` | int16 | yes | — | TODO |
| `n_oaa_slice_in_right` | int16 | yes | — | TODO |
| `n_oaa_slice_in_all` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_outfield_directional_oaa -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitcher_arm_angles -->
### Dataset: leaderboard_pitcher_arm_angles

Arm angle and release point per pitcher-season.

- **View:** `statcast_leaderboard_pitcher_arm_angles`
- **Processed path:** `processed/statcast/leaderboard_pitcher_arm_angles/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `pitcher`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `pitcher` | int32 | yes | — | TODO |
| `pitcher_name` | string | yes | — | TODO |
| `pitch_hand` | string | yes | — | TODO |
| `n_pitches` | int16 | yes | — | TODO |
| `team_id` | int16 | yes | — | TODO |
| `ball_angle` | double | yes | — | TODO |
| `relative_release_ball_x` | double | yes | — | TODO |
| `release_ball_z` | double | yes | — | TODO |
| `relative_shoulder_x` | double | yes | — | TODO |
| `shoulder_z` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_pitcher_arm_angles -->

<!-- BEGIN GENERATED:statcast.leaderboard_pitcher_running_game -->
### Dataset: leaderboard_pitcher_running_game

Running game against each pitcher by target base (runs prevented, stolen-base attempts).

- **View:** `statcast_leaderboard_pitcher_running_game`
- **Processed path:** `processed/statcast/leaderboard_pitcher_running_game/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `key_target_base`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | int32 | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `start_year` | int16 | yes | — | TODO |
| `end_year` | int16 | yes | — | TODO |
| `key_target_base` | string | yes | — | TODO |
| `runs_prevented_on_running_attr` | double | yes | — | TODO |
| `n_pitcher_cs_aa` | double | yes | — | TODO |
| `n_init` | int16 | yes | — | TODO |
| `rate_sbx` | double | yes | — | TODO |
| `n_sb` | int16 | yes | — | TODO |
| `n_cs` | int16 | yes | — | TODO |
| `n_pk` | int16 | yes | — | TODO |
| `n_bk` | int16 | yes | — | TODO |
| `n_fb` | int16 | yes | — | TODO |
| `n_plus` | int16 | yes | — | TODO |
| `n_minus` | int16 | yes | — | TODO |
| `net_attr_plus` | double | yes | — | TODO |
| `net_attr_minus` | double | yes | — | TODO |
| `r_primary_lead` | double | yes | — | TODO |
| `r_secondary_lead` | double | yes | — | TODO |
| `r_sec_minus_prim_lead` | double | yes | — | TODO |
| `r_primary_lead_sbx` | double | yes | — | TODO |
| `r_secondary_lead_sbx` | double | yes | — | TODO |
| `r_sec_minus_prim_lead_sbx` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_pitcher_running_game -->

<!-- BEGIN GENERATED:statcast.leaderboard_swing_timing_miss_distance_batter -->
### Dataset: leaderboard_swing_timing_miss_distance_batter

Swing timing and miss distance per batter-season (bat tracking).

- **View:** `statcast_leaderboard_swing_timing_miss_distance_batter`
- **Processed path:** `processed/statcast/leaderboard_swing_timing_miss_distance_batter/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `bat_side_formatted` | string | yes | — | TODO |
| `miss_distance` | double | yes | — | TODO |
| `flawed_percent` | double | yes | — | TODO |
| `perfect_percent` | double | yes | — | TODO |
| `tied_up_percent` | double | yes | — | TODO |
| `avg_x_tied_up` | double | yes | — | TODO |
| `centered_percent` | double | yes | — | TODO |
| `flailed_percent` | double | yes | — | TODO |
| `avg_x_flail` | double | yes | — | TODO |
| `early_percent` | double | yes | — | TODO |
| `avg_y_early` | double | yes | — | TODO |
| `on_time_percent` | double | yes | — | TODO |
| `late_percent` | double | yes | — | TODO |
| `avg_y_late` | double | yes | — | TODO |
| `n_swings` | int16 | yes | — | TODO |
| `whiff_rate` | double | yes | — | TODO |
| `competitive_percent` | double | yes | — | TODO |
| `over_percent` | double | yes | — | TODO |
| `avg_z_over` | double | yes | — | TODO |
| `lined_up_percent` | double | yes | — | TODO |
| `under_percent` | double | yes | — | TODO |
| `avg_z_under` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_swing_timing_miss_distance_batter -->

<!-- BEGIN GENERATED:statcast.leaderboard_swing_timing_miss_distance_pitcher -->
### Dataset: leaderboard_swing_timing_miss_distance_pitcher

Swing timing and miss distance against each pitcher-season (bat tracking).

- **View:** `statcast_leaderboard_swing_timing_miss_distance_pitcher`
- **Processed path:** `processed/statcast/leaderboard_swing_timing_miss_distance_pitcher/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |
| `team_name` | string | yes | — | TODO |
| `bat_side_formatted` | string | yes | — | TODO |
| `miss_distance` | double | yes | — | TODO |
| `flawed_percent` | double | yes | — | TODO |
| `perfect_percent` | double | yes | — | TODO |
| `tied_up_percent` | double | yes | — | TODO |
| `avg_x_tied_up` | double | yes | — | TODO |
| `centered_percent` | double | yes | — | TODO |
| `flailed_percent` | double | yes | — | TODO |
| `avg_x_flail` | double | yes | — | TODO |
| `early_percent` | double | yes | — | TODO |
| `avg_y_early` | double | yes | — | TODO |
| `on_time_percent` | double | yes | — | TODO |
| `late_percent` | double | yes | — | TODO |
| `avg_y_late` | double | yes | — | TODO |
| `n_swings` | int16 | yes | — | TODO |
| `whiff_rate` | double | yes | — | TODO |
| `competitive_percent` | double | yes | — | TODO |
| `over_percent` | double | yes | — | TODO |
| `avg_z_over` | double | yes | — | TODO |
| `lined_up_percent` | double | yes | — | TODO |
| `under_percent` | double | yes | — | TODO |
| `avg_z_under` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_swing_timing_miss_distance_pitcher -->

<!-- BEGIN GENERATED:statcast.leaderboard_year_to_year_batter -->
### Dataset: leaderboard_year_to_year_batter

Year-to-year changes of Statcast batting metrics per batter (one column per year and delta).

- **View:** `statcast_leaderboard_year_to_year_batter`
- **Processed path:** `processed/statcast/leaderboard_year_to_year_batter/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | — | TODO |
| `entity_id` | int32 | yes | — | TODO |
| `2015` | double | yes | — | TODO |
| `2016` | double | yes | — | TODO |
| `delta_2015_2016` | double | yes | — | TODO |
| `2017` | double | yes | — | TODO |
| `delta_2016_2017` | double | yes | — | TODO |
| `2018` | double | yes | — | TODO |
| `delta_2017_2018` | double | yes | — | TODO |
| `2019` | double | yes | — | TODO |
| `delta_2018_2019` | double | yes | — | TODO |
| `2020` | double | yes | — | TODO |
| `delta_2019_2020` | double | yes | — | TODO |
| `2021` | double | yes | — | TODO |
| `delta_2020_2021` | double | yes | — | TODO |
| `2022` | double | yes | — | TODO |
| `delta_2021_2022` | double | yes | — | TODO |
| `2023` | double | yes | — | TODO |
| `delta_2022_2023` | double | yes | — | TODO |
| `2024` | double | yes | — | TODO |
| `delta_2023_2024` | double | yes | — | TODO |
| `2025` | double | yes | — | TODO |
| `delta_2024_2025` | double | yes | — | TODO |
| `2026` | double | yes | — | TODO |
| `delta_2025_2026` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_year_to_year_batter -->

<!-- BEGIN GENERATED:statcast.leaderboard_year_to_year_pitcher -->
### Dataset: leaderboard_year_to_year_pitcher

Year-to-year changes of Statcast pitching metrics per pitcher (one column per year and delta).

- **View:** `statcast_leaderboard_year_to_year_pitcher`
- **Processed path:** `processed/statcast/leaderboard_year_to_year_pitcher/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `entity_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | — | TODO |
| `entity_id` | int32 | yes | — | TODO |
| `2015` | double | yes | — | TODO |
| `2016` | double | yes | — | TODO |
| `delta_2015_2016` | double | yes | — | TODO |
| `2017` | double | yes | — | TODO |
| `delta_2016_2017` | double | yes | — | TODO |
| `2018` | double | yes | — | TODO |
| `delta_2017_2018` | double | yes | — | TODO |
| `2019` | double | yes | — | TODO |
| `delta_2018_2019` | double | yes | — | TODO |
| `2020` | double | yes | — | TODO |
| `delta_2019_2020` | double | yes | — | TODO |
| `2021` | double | yes | — | TODO |
| `delta_2020_2021` | double | yes | — | TODO |
| `2022` | double | yes | — | TODO |
| `delta_2021_2022` | double | yes | — | TODO |
| `2023` | double | yes | — | TODO |
| `delta_2022_2023` | double | yes | — | TODO |
| `2024` | double | yes | — | TODO |
| `delta_2023_2024` | double | yes | — | TODO |
| `2025` | double | yes | — | TODO |
| `delta_2024_2025` | double | yes | — | TODO |
| `2026` | double | yes | — | TODO |
| `delta_2025_2026` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:statcast.leaderboard_year_to_year_pitcher -->
