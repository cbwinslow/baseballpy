# MLB Stats API Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** Major League Baseball Advanced Media (MLBAM)
- **Base Endpoint URL:** `https://statsapi.mlb.com/api`
- **Method:** `GET`
- **Response Format:** JSON (JavaScript Object Notation)
- **Rate Limit Policy:** Max 8.0 requests/second (token bucket enforced via `aiolimiter`)
- **Transport Strategy:** HTTP/2 connection pooling with persistent keep-alive (`httpx.AsyncClient(http2=True)`).
- **Optimization Strategy:**
  - High-performance deserialization via `msgspec.Struct` (10–20x faster than standard library `json`).
  - Conditional HTTP headers (`If-None-Match` with `ETag`) for live polling to eliminate redundant payload transfer on unchanged game state (ADR 8 & ADR 12).
  - Monotonic sequence tracking `(atBatIndex, eventIndex)` to emit only new play deltas.

---

## 1. Schedule & Calendar Endpoint (`/v1/schedule`)
Returns official contest schedules, doubleheaders, game status lifecycles, and venue assignments.

### Parameters
| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sportId` | `int` | `1` | 1 = Major League Baseball, 11 = Triple-A, 12 = Double-A |
| `season` | `int` | Current | Championship season year (e.g. 2024) |
| `startDate` | `string` | Optional | `YYYY-MM-DD` |
| `endDate` | `string` | Optional | `YYYY-MM-DD` |
| `teamId` | `int` | Optional | Team MLBAM numeric ID filter |
| `gameType` | `string` | `"R"` | Game classification: `R` (Regular), `P` (Postseason), `S` (Spring) |

### Table Schema (`mlb_schedule`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_pk` | `int32()` | No | Official unique numeric Game ID (Primary Key) |
| `game_date` | `date32()` | No | Official contest date (`YYYY-MM-DD`) |
| `game_type` | `string()` | No | `R`, `P`, `S`, `E` |
| `season` | `int16()` | No | Championship season |
| `status_code` | `string()` | No | `S` (Scheduled), `I` (In Progress), `F` (Final), `D` (Postponed) |
| `status_detailed` | `string()` | No | `Final`, `In Progress`, `Pre-Game`, `Postponed` |
| `away_team_id` | `int32()` | No | Visiting team MLBAM ID |
| `away_team_name` | `string()` | No | Visiting team name |
| `away_score` | `int16()` | Yes | Visiting team runs |
| `home_team_id` | `int32()` | No | Home team MLBAM ID |
| `home_team_name` | `string()` | No | Home team name |
| `home_score` | `int16()` | Yes | Home team runs |
| `doubleheader` | `string()` | No | `N` (No), `S` (Split), `Y` (Traditional) |
| `game_num` | `int8()` | No | Game number in contest day (1 or 2) |
| `venue_id` | `int32()` | Yes | Ballpark venue ID |
| `venue_name` | `string()` | Yes | Ballpark name |

---

## 2. Real-Time Live Gameday Feed (`/v1.1/game/{game_pk}/feed/live`)
Provides the complete live event stream, continuous pitch trajectories, play descriptions, strike zone dimensions, and in-game substitutions.

### Live Event Schema (`mlb_live_plays`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_pk` | `int32()` | No | Game identifier |
| `at_bat_index` | `int16()` | No | Plate appearance sequential index (0-based) |
| `event_index` | `int16()` | No | Play event index within plate appearance |
| `is_pitch` | `bool_()` | No | True if event is a pitch, False if pickoff/action |
| `pitch_type` | `string()` | Yes | Pitch classification code (FF, SL, CH, etc.) |
| `start_speed` | `float32()` | Yes | Pitch velocity at release (MPH) |
| `end_speed` | `float32()` | Yes | Pitch velocity crossing front of plate (MPH) |
| `sz_top` | `float32()` | Yes | Batter strike zone top coordinate in feet |
| `sz_bottom` | `float32()` | Yes | Batter strike zone bottom coordinate in feet |
| `px` | `float32()` | Yes | Horizontal pitch location crossing plate (ft) |
| `pz` | `float32()` | Yes | Vertical pitch location crossing plate (ft) |
| `x` | `float32()` | Yes | Horizontal hit/pitch coordinate in video space |
| `y` | `float32()` | Yes | Vertical hit/pitch coordinate in video space |
| `description` | `string()` | No | Play / pitch description |
| `call_code` | `string()` | Yes | Pitch call code (`B`, `S`, `X`, etc.) |
| `event` | `string()` | Yes | Outcome event (`single`, `strikeout`, etc.) |
| `event_type` | `string()` | Yes | Event classification |
| `batter_id` | `int32()` | No | Batter MLBAM ID |
| `pitcher_id` | `int32()` | No | Pitcher MLBAM ID |
| `inning` | `int8()` | No | Inning number |
| `is_top_inning` | `bool_()` | No | True if top of inning, False if bottom |
| `outs` | `int8()` | No | Outs prior to play |
| `balls` | `int8()` | No | Balls count |
| `strikes` | `int8()` | No | Strikes count |
| `timestamp` | `timestamp("us", tz="UTC")` | Yes | Microsecond UTC event timestamp |

---

## 3. Official Boxscores (`/v1/game/{game_pk}/boxscore`)
Game-by-game individual player stat lines across hitting, pitching, and fielding.

### A. Batting Boxscore (`mlb_box_batting`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_pk` | `int32()` | No | Game identifier |
| `team_id` | `int32()` | No | Team MLBAM ID |
| `player_id` | `int32()` | No | Player MLBAM ID |
| `player_name` | `string()` | No | Full name |
| `position` | `string()` | No | Defensive position abbreviation |
| `batting_order` | `int16()` | Yes | Lineup slot (100, 200, ... or substitute) |
| `ab` | `int16()` | No | At-bats |
| `r` | `int16()` | No | Runs scored |
| `h` | `int16()` | No | Hits |
| `d` | `int16()` | No | Doubles |
| `t` | `int16()` | No | Triples |
| `hr` | `int16()` | No | Home runs |
| `rbi` | `int16()` | No | Runs batted in |
| `bb` | `int16()` | No | Walks |
| `so` | `int16()` | No | Strikeouts |
| `sb` | `int16()` | No | Stolen bases |
| `cs` | `int16()` | No | Caught stealing |

### B. Pitching Boxscore (`mlb_box_pitching`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `game_pk` | `int32()` | No | Game identifier |
| `team_id` | `int32()` | No | Team MLBAM ID |
| `player_id` | `int32()` | No | Pitcher MLBAM ID |
| `player_name` | `string()` | No | Full name |
| `ip` | `float32()` | No | Innings pitched (e.g. 6.1) |
| `h` | `int16()` | No | Hits allowed |
| `r` | `int16()` | No | Runs allowed |
| `er` | `int16()` | No | Earned runs allowed |
| `bb` | `int16()` | No | Walks allowed |
| `so` | `int16()` | No | Strikeouts thrown |
| `hr` | `int16()` | No | Home runs allowed |
| `pitches` | `int16()` | Yes | Total pitches |
| `strikes` | `int16()` | Yes | Total strikes |

---

## 4. Standings & Rankings (`/v1/standings`)
Division, league, and wild card standings.

### Standings Schema (`mlb_standings`)
| Column Name | PyArrow Physical Type | Nullable | Description |
| :--- | :--- | :---: | :--- |
| `season` | `int16()` | No | Season year |
| `division_id` | `int32()` | No | Division ID (e.g. 201 for AL East) |
| `division_name` | `string()` | No | Division name |
| `team_id` | `int32()` | No | Team MLBAM ID |
| `team_name` | `string()` | No | Franchise name |
| `wins` | `int16()` | No | Wins |
| `losses` | `int16()` | No | Losses |
| `win_pct` | `float32()` | No | Winning percentage |
| `games_back` | `float32()` | Yes | Games behind division leader |
| `wild_card_gb` | `float32()` | Yes | Games behind wild card berth |
| `run_differential` | `int16()` | No | Runs scored minus runs allowed |
| `streak` | `string()` | Yes | Current winning/losing streak (e.g. `W5`) |
| `elim_num` | `int16()` | Yes | Division elimination number |

---

## 5. Teams & Active Rosters (`/v1/teams`, `/v1/teams/{team_id}/roster`)
Franchise directory and roster movements.

### Teams Schema (`mlb_teams`)
- `team_id`: `int32()`
- `team_name`: `string()`
- `abbreviation`: `string()`
- `league_id`: `int32()`
- `league_name`: `string()`
- `division_id`: `int32()`
- `division_name`: `string()`
- `venue_id`: `int32()`
- `venue_name`: `string()`
- `active`: `bool_()`

### Rosters Schema (`mlb_rosters`)
- `team_id`: `int32()`
- `player_id`: `int32()`
- `player_name`: `string()`
- `jersey_number`: `string()`
- `position_code`: `string()`
- `position_name`: `string()`
- `status`: `string()` (`Active`, `Injured List 10-day`, `Injured List 60-day`)

---

## 6. Transactions (`/v1/transactions`)
- **URL:** `/api/v1/transactions?season={season}`
- **Columns:** `transaction_id`, `date`, `player_id`, `player_name`, `from_team_id`, `to_team_id`, `type_code`, `type_desc`, `description`.

---

## 7. Draft (`/v1/draft/{year}`)
- **URL:** `/api/v1/draft/{year}`
- **Columns:** `year`, `round`, `pick_round`, `pick_overall`, `team_id`, `player_id`, `player_name`, `school_name`, `signing_bonus`.

---

## 8. Venues / Ballparks (`/v1/venues`)
- **URL:** `/api/v1/venues`
- **Columns:** `venue_id`, `venue_name`, `city`, `state`, `country`, `capacity`, `turf_type`, `roof_type`.

## Declarative endpoints

Beyond the nine hand-written datasets above, every other MLB endpoint is *data*: a `MlbEndpoint` (path/params
template, record path, fan-out `scope`, key) in `sources/mlb_api/endpoints.py`. `scripts/gen_mlb_schemas.py` probes each
one live, flattens a sample and writes a strict schema (`mlb_tables.py`), fixtures (`tests/fixtures/mlb/`) and
`docs/mlb_probe.json`. The generic extractor fetches every request of an endpoint, stores the raw JSON (sha256) and one
typed Parquet part per request.

- **Flattening:** nested objects become dotted keys (`venue.location.city` -> `venue_location_city`); arrays are kept as JSON text; scalar fields of wrapper objects on the way to the records (e.g. `dates[*].date`) are carried as `dates.date`. Unknown fields go to `_extras`; cells that do not fit their type are quarantined; a payload whose shape contradicts the record path raises.
- **Scopes:** `flat` (once), `season` (x `sportId`), `teams_season` (one call with all team ids), `team_season` (per team), `game` (per `game_pk`). Fan-out values are added as columns when the payload does not repeat them (`game_pk`, `team_id`, `sport_id`).
- **Stats:** `stats_<statType>_<group>` (`/v1/stats`, league-wide, paginated 1000 rows) and `team_stats_<statType>_<group>` exist for every statType x group (hitting, pitching, fielding, catching, running) that returned data for 2024; the list is `stat_combos.py`.
- **API:** `get_endpoint(name, season)`, `MlbApiSource.ingest_reference()`, `ingest_season(season, include_games=False, max_games=None)`.
- **Standings sentinels:** in the hand-written `standings` dataset `gamesBack`/`wildCardGamesBack` `-` is 0 games and `eliminationNumber` `E` is 0 (`-` is NULL); they used to be quarantined on every run.
- **Not covered here:** the live streamer rewrite (diffPatch/timestamps), people-level stats (`/v1/people/{id}/stats`), award recipients and the draft/transactions fan-out beyond the hand-written datasets; `stats` combos that need a player id (e.g. `playLog`, `sprayChart`) return nothing league-wide.

| Dataset family | Datasets | Status (probe 2026-10-27) |
|---|---|---|
| `stats_*` | 39 | ok: 39 |
| `team_stats_*` | 56 | ok: 56 |
| `ref_*` | 28 | ok: 27, unsupported: 1 |
| `seasons_all` | 1 | ok: 1 |
| `teams_season` | 1 | ok: 1 |
| `divisions_season` | 1 | ok: 1 |
| `leagues_season` | 1 | ok: 1 |
| `team_affiliates` | 1 | ok: 1 |
| `team_history` | 1 | ok: 1 |
| `team_coaches` | 1 | ok: 1 |
| `team_personnel` | 1 | ok: 1 |
| `team_alumni` | 1 | ok: 1 |
| `team_roster_active` | 1 | ok: 1 |
| `team_roster_40_man` | 1 | ok: 1 |
| `team_roster_full_season` | 1 | ok: 1 |
| `team_roster_full_roster` | 1 | ok: 1 |
| `team_roster_non_roster_invitees` | 1 | ok: 1 |
| `team_roster_depth_chart` | 1 | ok: 1 |
| `players_season` | 1 | ok: 1 |
| `free_agents` | 1 | ok: 1 |
| `jobs_umpires` | 1 | ok: 1 |
| `jobs_datacasters` | 1 | ok: 1 |
| `jobs_official_scorers` | 1 | ok: 1 |
| `draft_prospects` | 1 | ok: 1 |
| `schedule_postseason` | 1 | ok: 1 |
| `schedule_postseason_series` | 1 | ok: 1 |
| `stats_leaders` | 1 | ok: 1 |
| `schedule_hydrated` | 1 | ok: 1 |
| `standings_regular_season` | 1 | ok: 1 |
| `standings_wild_card` | 1 | ok: 1 |
| `standings_division_leaders` | 1 | ok: 1 |
| `standings_wild_card_with_leaders` | 1 | ok: 1 |
| `standings_first_half` | 1 | empty: 1 |
| `standings_second_half` | 1 | empty: 1 |
| `standings_spring_training` | 1 | ok: 1 |
| `standings_postseason` | 1 | empty: 1 |
| `standings_by_division` | 1 | ok: 1 |
| `standings_by_conference` | 1 | ok: 1 |
| `standings_by_league` | 1 | ok: 1 |
| `standings_by_organization` | 1 | ok: 1 |
| `game_linescore` | 1 | ok: 1 |
| `game_win_probability` | 1 | ok: 1 |
| `game_play_by_play` | 1 | ok: 1 |
| `attendance` | 1 | unsupported: 1 |
| `game_color` | 1 | unsupported: 1 |
| `home_run_derby` | 1 | unsupported: 1 |

### Probed and not ingested

| Dataset | Reason |
|---|---|
| `attendance` | probe returned HTTP 400 with leagueId/season; see docs/mlb_probe.json |
| `game_color` | route answers 404 for a final game (probed 2026-10-27) |
| `home_run_derby` | route answers 404 for the probed game (probed 2026-10-27) |
| `ref_sky_conditions` | route answers 404 (probed 2026-10-27) |

Endpoints that answered 200 with no records for the sampled seasons (typed on first non-empty run): `standings_first_half`, `standings_second_half`, `standings_postseason`.

## Storage Layout (lake v2)
- Raw JSON payloads: `raw/mlb_api/<dataset>/[season=YYYY/]<ident>.json`.
- Typed Parquet: `processed/mlb_api/<dataset>/[season=YYYY/]part-<ident>.parquet` for `schedule`, `box_batting`, `box_pitching`, `standings`, `teams`, `rosters`, `transactions`, `draft`, `venues` (views `mlb_<dataset>`).
- Boxscores are immutable only once the game is final; the `final` flag lives in the `box_batting` manifest (`box_<game_pk>`).

## Dataset reference (generated)

<!-- BEGIN GENERATED:mlb_api.box_batting -->
### Dataset: box_batting

Official batting boxscore lines.

- **View:** `mlb_box_batting`
- **Processed path:** `processed/mlb_api/box_batting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `team_id`, `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `team_id` | int32 | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `position` | string | yes | — |  |
| `batting_order` | int16 | yes | — |  |
| `ab` | int16 | yes | — |  |
| `r` | int16 | yes | — |  |
| `h` | int16 | yes | — |  |
| `d` | int16 | yes | — |  |
| `t` | int16 | yes | — |  |
| `hr` | int16 | yes | — |  |
| `rbi` | int16 | yes | — |  |
| `bb` | int16 | yes | — |  |
| `so` | int16 | yes | — |  |
| `sb` | int16 | yes | — |  |
| `cs` | int16 | yes | — |  |

<!-- END GENERATED:mlb_api.box_batting -->

<!-- BEGIN GENERATED:mlb_api.box_pitching -->
### Dataset: box_pitching

Official pitching boxscore lines.

- **View:** `mlb_box_pitching`
- **Processed path:** `processed/mlb_api/box_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `team_id`, `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `team_id` | int32 | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `ip` | float | yes | — |  |
| `h` | int16 | yes | — |  |
| `r` | int16 | yes | — |  |
| `er` | int16 | yes | — |  |
| `bb` | int16 | yes | — |  |
| `so` | int16 | yes | — |  |
| `hr` | int16 | yes | — |  |
| `pitches` | int16 | yes | — |  |
| `strikes` | int16 | yes | — |  |

<!-- END GENERATED:mlb_api.box_pitching -->

<!-- BEGIN GENERATED:mlb_api.draft -->
### Dataset: draft

First-year player draft picks.

- **View:** `mlb_draft`
- **Processed path:** `processed/mlb_api/draft/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `year`, `pick_overall`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `year` | int16 | yes | — |  |
| `round` | string | yes | — |  |
| `pick_round` | int16 | yes | — |  |
| `pick_overall` | int16 | yes | — |  |
| `team_id` | int32 | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `school_name` | string | yes | — |  |
| `signing_bonus` | int64 | yes | — |  |

<!-- END GENERATED:mlb_api.draft -->

<!-- BEGIN GENERATED:mlb_api.rosters -->
### Dataset: rosters

Active team rosters.

- **View:** `mlb_rosters`
- **Processed path:** `processed/mlb_api/rosters/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `team_id`, `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `jersey_number` | string | yes | — |  |
| `position_code` | string | yes | — |  |
| `position_name` | string | yes | — |  |
| `status` | string | yes | — |  |

<!-- END GENERATED:mlb_api.rosters -->

<!-- BEGIN GENERATED:mlb_api.schedule -->
### Dataset: schedule

Game schedule.

- **View:** `mlb_schedule`
- **Processed path:** `processed/mlb_api/schedule/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `game_date` | date32[day] | yes | — |  |
| `game_type` | string | yes | — |  |
| `season` | int16 | yes | — |  |
| `status_code` | string | yes | — |  |
| `status_detailed` | string | yes | — |  |
| `away_team_id` | int32 | yes | — |  |
| `away_team_name` | string | yes | — |  |
| `away_score` | int16 | yes | — |  |
| `home_team_id` | int32 | yes | — |  |
| `home_team_name` | string | yes | — |  |
| `home_score` | int16 | yes | — |  |
| `doubleheader` | string | yes | — |  |
| `game_num` | int8 | yes | — |  |
| `venue_id` | int32 | yes | — |  |
| `venue_name` | string | yes | — |  |

<!-- END GENERATED:mlb_api.schedule -->

<!-- BEGIN GENERATED:mlb_api.standings -->
### Dataset: standings

League and division standings.

- **View:** `mlb_standings`
- **Processed path:** `processed/mlb_api/standings/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `season`, `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season` | int16 | yes | — |  |
| `division_id` | int32 | yes | — |  |
| `division_name` | string | yes | — |  |
| `team_id` | int32 | yes | — |  |
| `team_name` | string | yes | — |  |
| `wins` | int16 | yes | — |  |
| `losses` | int16 | yes | — |  |
| `win_pct` | float | yes | — |  |
| `games_back` | float | yes | — |  |
| `wild_card_gb` | float | yes | — |  |
| `run_differential` | int16 | yes | — |  |
| `streak` | string | yes | — |  |
| `elim_num` | int16 | yes | — |  |

<!-- END GENERATED:mlb_api.standings -->

<!-- BEGIN GENERATED:mlb_api.teams -->
### Dataset: teams

MLB franchises.

- **View:** `mlb_teams`
- **Processed path:** `processed/mlb_api/teams/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `team_name` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `league_id` | int32 | yes | — |  |
| `league_name` | string | yes | — |  |
| `division_id` | int32 | yes | — |  |
| `division_name` | string | yes | — |  |
| `venue_id` | int32 | yes | — |  |
| `venue_name` | string | yes | — |  |
| `active` | bool | yes | — |  |

<!-- END GENERATED:mlb_api.teams -->

<!-- BEGIN GENERATED:mlb_api.transactions -->
### Dataset: transactions

Roster transactions.

- **View:** `mlb_transactions`
- **Processed path:** `processed/mlb_api/transactions/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `transaction_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `transaction_id` | int32 | yes | — |  |
| `date` | string | yes | — |  |
| `player_id` | int32 | yes | — |  |
| `player_name` | string | yes | — |  |
| `from_team_id` | int32 | yes | — |  |
| `to_team_id` | int32 | yes | — |  |
| `type_code` | string | yes | — |  |
| `type_desc` | string | yes | — |  |
| `description` | string | yes | — |  |

<!-- END GENERATED:mlb_api.transactions -->

<!-- BEGIN GENERATED:mlb_api.venues -->
### Dataset: venues

Official ballparks.

- **View:** `mlb_venues`
- **Processed path:** `processed/mlb_api/venues/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `venue_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `venue_id` | int32 | yes | — |  |
| `venue_name` | string | yes | — |  |
| `city` | string | yes | — |  |
| `state` | string | yes | — |  |
| `country` | string | yes | — |  |
| `capacity` | int32 | yes | — |  |
| `turf_type` | string | yes | — |  |
| `roof_type` | string | yes | — |  |

<!-- END GENERATED:mlb_api.venues -->

<!-- BEGIN GENERATED:mlb_api.divisions_season -->
### Dataset: divisions_season

Divisions of a season.

- **View:** `mlb_divisions_season`
- **Processed path:** `processed/mlb_api/divisions_season/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `season` | string | yes | — |  |
| `name_short` | string | yes | `nameShort` |  |
| `link` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `num_playoff_teams` | int32 | yes | `numPlayoffTeams` |  |
| `active` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.divisions_season -->

<!-- BEGIN GENERATED:mlb_api.draft_prospects -->
### Dataset: draft_prospects

Draft prospects of a year.

- **View:** `mlb_draft_prospects`
- **Processed path:** `processed/mlb_api/draft_prospects/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `person_id`, `bis_player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `bis_player_id` | int32 | yes | `bisPlayerId` |  |
| `pick_round` | string | yes | `pickRound` |  |
| `pick_number` | int32 | yes | `pickNumber` |  |
| `home_city` | string | yes | `home.city` |  |
| `home_state` | string | yes | `home.state` |  |
| `home_country` | string | yes | `home.country` |  |
| `school_name` | string | yes | `school.name` |  |
| `school_school_class` | string | yes | `school.schoolClass` |  |
| `school_city` | string | yes | `school.city` |  |
| `school_country` | string | yes | `school.country` |  |
| `school_state` | string | yes | `school.state` |  |
| `headshot_link` | string | yes | `headshotLink` |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `person_first_name` | string | yes | `person.firstName` |  |
| `person_last_name` | string | yes | `person.lastName` |  |
| `person_birth_date` | date32[day] | yes | `person.birthDate` |  |
| `person_current_age` | int32 | yes | `person.currentAge` |  |
| `person_birth_city` | string | yes | `person.birthCity` |  |
| `person_birth_state_province` | string | yes | `person.birthStateProvince` |  |
| `person_birth_country` | string | yes | `person.birthCountry` |  |
| `person_height` | string | yes | `person.height` |  |
| `person_weight` | int32 | yes | `person.weight` |  |
| `person_active` | bool | yes | `person.active` |  |
| `person_primary_position_code` | string | yes | `person.primaryPosition.code` |  |
| `person_primary_position_name` | string | yes | `person.primaryPosition.name` |  |
| `person_primary_position_type` | string | yes | `person.primaryPosition.type` |  |
| `person_primary_position_abbreviation` | string | yes | `person.primaryPosition.abbreviation` |  |
| `person_use_name` | string | yes | `person.useName` |  |
| `person_use_last_name` | string | yes | `person.useLastName` |  |
| `person_middle_name` | string | yes | `person.middleName` |  |
| `person_boxscore_name` | string | yes | `person.boxscoreName` |  |
| `person_gender` | string | yes | `person.gender` |  |
| `person_is_player` | bool | yes | `person.isPlayer` |  |
| `person_is_verified` | bool | yes | `person.isVerified` |  |
| `person_draft_year` | int32 | yes | `person.draftYear` |  |
| `person_bat_side_code` | string | yes | `person.batSide.code` |  |
| `person_bat_side_description` | string | yes | `person.batSide.description` |  |
| `person_pitch_hand_code` | string | yes | `person.pitchHand.code` |  |
| `person_pitch_hand_description` | string | yes | `person.pitchHand.description` |  |
| `person_name_first_last` | string | yes | `person.nameFirstLast` |  |
| `person_name_slug` | string | yes | `person.nameSlug` |  |
| `person_first_last_name` | string | yes | `person.firstLastName` |  |
| `person_last_first_name` | string | yes | `person.lastFirstName` |  |
| `person_last_init_name` | string | yes | `person.lastInitName` |  |
| `person_init_last_name` | string | yes | `person.initLastName` |  |
| `person_full_fml_name` | string | yes | `person.fullFMLName` |  |
| `person_full_lfm_name` | string | yes | `person.fullLFMName` |  |
| `person_strike_zone_top` | double | yes | `person.strikeZoneTop` |  |
| `person_strike_zone_bottom` | double | yes | `person.strikeZoneBottom` |  |
| `team_spring_league_id` | int32 | yes | `team.springLeague.id` |  |
| `team_spring_league_name` | string | yes | `team.springLeague.name` |  |
| `team_spring_league_link` | string | yes | `team.springLeague.link` |  |
| `team_spring_league_abbreviation` | string | yes | `team.springLeague.abbreviation` |  |
| `team_all_star_status` | string | yes | `team.allStarStatus` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `team_season` | int32 | yes | `team.season` |  |
| `team_venue_id` | int32 | yes | `team.venue.id` |  |
| `team_venue_name` | string | yes | `team.venue.name` |  |
| `team_venue_link` | string | yes | `team.venue.link` |  |
| `team_spring_venue_id` | int32 | yes | `team.springVenue.id` |  |
| `team_spring_venue_link` | string | yes | `team.springVenue.link` |  |
| `team_team_code` | string | yes | `team.teamCode` |  |
| `team_file_code` | string | yes | `team.fileCode` |  |
| `team_abbreviation` | string | yes | `team.abbreviation` |  |
| `team_team_name` | string | yes | `team.teamName` |  |
| `team_location_name` | string | yes | `team.locationName` |  |
| `team_first_year_of_play` | string | yes | `team.firstYearOfPlay` |  |
| `team_league_id` | int32 | yes | `team.league.id` |  |
| `team_league_name` | string | yes | `team.league.name` |  |
| `team_league_link` | string | yes | `team.league.link` |  |
| `team_division_id` | int32 | yes | `team.division.id` |  |
| `team_division_name` | string | yes | `team.division.name` |  |
| `team_division_link` | string | yes | `team.division.link` |  |
| `team_sport_id` | int32 | yes | `team.sport.id` |  |
| `team_sport_link` | string | yes | `team.sport.link` |  |
| `team_sport_name` | string | yes | `team.sport.name` |  |
| `team_short_name` | string | yes | `team.shortName` |  |
| `team_franchise_name` | string | yes | `team.franchiseName` |  |
| `team_club_name` | string | yes | `team.clubName` |  |
| `team_active` | bool | yes | `team.active` |  |
| `draft_type_code` | string | yes | `draftType.code` |  |
| `draft_type_description` | string | yes | `draftType.description` |  |
| `is_drafted` | bool | yes | `isDrafted` |  |
| `is_pass` | bool | yes | `isPass` |  |
| `year` | string | yes | — |  |
| `rank` | int32 | yes | — |  |
| `scouting_report` | string | yes | `scoutingReport` |  |
| `blurb` | string | yes | — |  |
| `is_withdrawn` | bool | yes | `isWithdrawn` |  |
| `person_primary_number` | string | yes | `person.primaryNumber` |  |
| `person_name_title` | string | yes | `person.nameTitle` |  |
| `person_name_suffix` | string | yes | `person.nameSuffix` |  |
| `person_mlb_debut_date` | date32[day] | yes | `person.mlbDebutDate` |  |
| `person_pronunciation` | string | yes | `person.pronunciation` |  |
| `person_name_matrilineal` | string | yes | `person.nameMatrilineal` |  |
| `person_nick_name` | string | yes | `person.nickName` |  |
| `person_last_played_date` | date32[day] | yes | `person.lastPlayedDate` |  |
| `person_death_date` | date32[day] | yes | `person.deathDate` |  |
| `person_death_state_province` | string | yes | `person.deathStateProvince` |  |
| `person_death_country` | string | yes | `person.deathCountry` |  |
| `person_death_city` | string | yes | `person.deathCity` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.draft_prospects -->

<!-- BEGIN GENERATED:mlb_api.free_agents -->
### Dataset: free_agents

Free agents of a season.

- **View:** `mlb_free_agents`
- **Processed path:** `processed/mlb_api/free_agents/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `original_team_id` | int32 | yes | `originalTeam.id` |  |
| `original_team_name` | string | yes | `originalTeam.name` |  |
| `original_team_link` | string | yes | `originalTeam.link` |  |
| `new_team_id` | int32 | yes | `newTeam.id` |  |
| `new_team_name` | string | yes | `newTeam.name` |  |
| `new_team_link` | string | yes | `newTeam.link` |  |
| `notes` | string | yes | — |  |
| `date_signed` | date32[day] | yes | `dateSigned` |  |
| `date_declared` | date32[day] | yes | `dateDeclared` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.free_agents -->

<!-- BEGIN GENERATED:mlb_api.game_linescore -->
### Dataset: game_linescore

Inning-by-inning linescore of a game.

- **View:** `mlb_game_linescore`
- **Processed path:** `processed/mlb_api/game_linescore/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `num`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `num` | int32 | yes | — |  |
| `ordinal_num` | string | yes | `ordinalNum` |  |
| `home_runs` | int32 | yes | `home.runs` |  |
| `home_hits` | int32 | yes | `home.hits` |  |
| `home_errors` | int32 | yes | `home.errors` |  |
| `home_left_on_base` | int32 | yes | `home.leftOnBase` |  |
| `away_runs` | int32 | yes | `away.runs` |  |
| `away_hits` | int32 | yes | `away.hits` |  |
| `away_errors` | int32 | yes | `away.errors` |  |
| `away_left_on_base` | int32 | yes | `away.leftOnBase` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_linescore -->

<!-- BEGIN GENERATED:mlb_api.game_play_by_play -->
### Dataset: game_play_by_play

Every play of a game (matchup, result, count, runners as JSON).

- **View:** `mlb_game_play_by_play`
- **Processed path:** `processed/mlb_api/game_play_by_play/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `at_bat_index`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `result_type` | string | yes | `result.type` |  |
| `result_event` | string | yes | `result.event` |  |
| `result_event_type` | string | yes | `result.eventType` |  |
| `result_description` | string | yes | `result.description` |  |
| `result_rbi` | int32 | yes | `result.rbi` |  |
| `result_away_score` | int32 | yes | `result.awayScore` |  |
| `result_home_score` | int32 | yes | `result.homeScore` |  |
| `result_is_out` | bool | yes | `result.isOut` |  |
| `about_at_bat_index` | int32 | yes | `about.atBatIndex` |  |
| `about_half_inning` | string | yes | `about.halfInning` |  |
| `about_is_top_inning` | bool | yes | `about.isTopInning` |  |
| `about_inning` | int32 | yes | `about.inning` |  |
| `about_start_time` | timestamp[us, tz=UTC] | yes | `about.startTime` |  |
| `about_end_time` | timestamp[us, tz=UTC] | yes | `about.endTime` |  |
| `about_is_complete` | bool | yes | `about.isComplete` |  |
| `about_is_scoring_play` | bool | yes | `about.isScoringPlay` |  |
| `about_has_review` | bool | yes | `about.hasReview` |  |
| `about_has_out` | bool | yes | `about.hasOut` |  |
| `about_captivating_index` | int32 | yes | `about.captivatingIndex` |  |
| `count_balls` | int32 | yes | `count.balls` |  |
| `count_strikes` | int32 | yes | `count.strikes` |  |
| `count_outs` | int32 | yes | `count.outs` |  |
| `matchup_batter_id` | int32 | yes | `matchup.batter.id` |  |
| `matchup_batter_full_name` | string | yes | `matchup.batter.fullName` |  |
| `matchup_batter_link` | string | yes | `matchup.batter.link` |  |
| `matchup_bat_side_code` | string | yes | `matchup.batSide.code` |  |
| `matchup_bat_side_description` | string | yes | `matchup.batSide.description` |  |
| `matchup_pitcher_id` | int32 | yes | `matchup.pitcher.id` |  |
| `matchup_pitcher_full_name` | string | yes | `matchup.pitcher.fullName` |  |
| `matchup_pitcher_link` | string | yes | `matchup.pitcher.link` |  |
| `matchup_pitch_hand_code` | string | yes | `matchup.pitchHand.code` |  |
| `matchup_pitch_hand_description` | string | yes | `matchup.pitchHand.description` |  |
| `matchup_batter_hot_cold_zones` | string | yes | `matchup.batterHotColdZones` |  |
| `matchup_pitcher_hot_cold_zones` | string | yes | `matchup.pitcherHotColdZones` |  |
| `matchup_splits_batter` | string | yes | `matchup.splits.batter` |  |
| `matchup_splits_pitcher` | string | yes | `matchup.splits.pitcher` |  |
| `matchup_splits_men_on_base` | string | yes | `matchup.splits.menOnBase` |  |
| `pitch_index` | string | yes | `pitchIndex` |  |
| `action_index` | string | yes | `actionIndex` |  |
| `runner_index` | string | yes | `runnerIndex` |  |
| `runners` | string | yes | — |  |
| `play_events` | string | yes | `playEvents` |  |
| `play_end_time` | timestamp[us, tz=UTC] | yes | `playEndTime` |  |
| `at_bat_index` | int32 | yes | `atBatIndex` |  |
| `matchup_post_on_second_id` | int32 | yes | `matchup.postOnSecond.id` |  |
| `matchup_post_on_second_full_name` | string | yes | `matchup.postOnSecond.fullName` |  |
| `matchup_post_on_second_link` | string | yes | `matchup.postOnSecond.link` |  |
| `matchup_post_on_first_id` | int32 | yes | `matchup.postOnFirst.id` |  |
| `matchup_post_on_first_full_name` | string | yes | `matchup.postOnFirst.fullName` |  |
| `matchup_post_on_first_link` | string | yes | `matchup.postOnFirst.link` |  |
| `matchup_post_on_third_id` | int32 | yes | `matchup.postOnThird.id` |  |
| `matchup_post_on_third_full_name` | string | yes | `matchup.postOnThird.fullName` |  |
| `matchup_post_on_third_link` | string | yes | `matchup.postOnThird.link` |  |
| `review_details_is_overturned` | bool | yes | `reviewDetails.isOverturned` |  |
| `review_details_in_progress` | bool | yes | `reviewDetails.inProgress` |  |
| `review_details_review_type` | string | yes | `reviewDetails.reviewType` |  |
| `review_details_challenge_team_id` | int32 | yes | `reviewDetails.challengeTeamId` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_play_by_play -->

<!-- BEGIN GENERATED:mlb_api.game_win_probability -->
### Dataset: game_win_probability

Win probability after every play.

- **View:** `mlb_game_win_probability`
- **Processed path:** `processed/mlb_api/game_win_probability/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `at_bat_index`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `result_type` | string | yes | `result.type` |  |
| `result_event` | string | yes | `result.event` |  |
| `result_event_type` | string | yes | `result.eventType` |  |
| `result_description` | string | yes | `result.description` |  |
| `result_rbi` | int32 | yes | `result.rbi` |  |
| `result_away_score` | int32 | yes | `result.awayScore` |  |
| `result_home_score` | int32 | yes | `result.homeScore` |  |
| `result_is_out` | bool | yes | `result.isOut` |  |
| `about_at_bat_index` | int32 | yes | `about.atBatIndex` |  |
| `about_half_inning` | string | yes | `about.halfInning` |  |
| `about_is_top_inning` | bool | yes | `about.isTopInning` |  |
| `about_inning` | int32 | yes | `about.inning` |  |
| `about_start_time` | timestamp[us, tz=UTC] | yes | `about.startTime` |  |
| `about_end_time` | timestamp[us, tz=UTC] | yes | `about.endTime` |  |
| `about_is_complete` | bool | yes | `about.isComplete` |  |
| `about_is_scoring_play` | bool | yes | `about.isScoringPlay` |  |
| `about_has_review` | bool | yes | `about.hasReview` |  |
| `about_has_out` | bool | yes | `about.hasOut` |  |
| `about_captivating_index` | int32 | yes | `about.captivatingIndex` |  |
| `count_balls` | int32 | yes | `count.balls` |  |
| `count_strikes` | int32 | yes | `count.strikes` |  |
| `count_outs` | int32 | yes | `count.outs` |  |
| `matchup_batter_id` | int32 | yes | `matchup.batter.id` |  |
| `matchup_batter_full_name` | string | yes | `matchup.batter.fullName` |  |
| `matchup_batter_link` | string | yes | `matchup.batter.link` |  |
| `matchup_bat_side_code` | string | yes | `matchup.batSide.code` |  |
| `matchup_bat_side_description` | string | yes | `matchup.batSide.description` |  |
| `matchup_pitcher_id` | int32 | yes | `matchup.pitcher.id` |  |
| `matchup_pitcher_full_name` | string | yes | `matchup.pitcher.fullName` |  |
| `matchup_pitcher_link` | string | yes | `matchup.pitcher.link` |  |
| `matchup_pitch_hand_code` | string | yes | `matchup.pitchHand.code` |  |
| `matchup_pitch_hand_description` | string | yes | `matchup.pitchHand.description` |  |
| `matchup_batter_hot_cold_zones` | string | yes | `matchup.batterHotColdZones` |  |
| `matchup_pitcher_hot_cold_zones` | string | yes | `matchup.pitcherHotColdZones` |  |
| `matchup_splits_batter` | string | yes | `matchup.splits.batter` |  |
| `matchup_splits_pitcher` | string | yes | `matchup.splits.pitcher` |  |
| `matchup_splits_men_on_base` | string | yes | `matchup.splits.menOnBase` |  |
| `pitch_index` | string | yes | `pitchIndex` |  |
| `action_index` | string | yes | `actionIndex` |  |
| `runner_index` | string | yes | `runnerIndex` |  |
| `runners` | string | yes | — |  |
| `play_events` | string | yes | `playEvents` |  |
| `credits` | string | yes | — |  |
| `flags` | string | yes | — |  |
| `home_team_win_probability` | double | yes | `homeTeamWinProbability` |  |
| `away_team_win_probability` | double | yes | `awayTeamWinProbability` |  |
| `home_team_win_probability_added` | double | yes | `homeTeamWinProbabilityAdded` |  |
| `play_end_time` | timestamp[us, tz=UTC] | yes | `playEndTime` |  |
| `at_bat_index` | int32 | yes | `atBatIndex` |  |
| `leverage_index` | double | yes | `leverageIndex` |  |
| `drama_index` | double | yes | `dramaIndex` |  |
| `matchup_post_on_second_id` | int32 | yes | `matchup.postOnSecond.id` |  |
| `matchup_post_on_second_full_name` | string | yes | `matchup.postOnSecond.fullName` |  |
| `matchup_post_on_second_link` | string | yes | `matchup.postOnSecond.link` |  |
| `matchup_post_on_first_id` | int32 | yes | `matchup.postOnFirst.id` |  |
| `matchup_post_on_first_full_name` | string | yes | `matchup.postOnFirst.fullName` |  |
| `matchup_post_on_first_link` | string | yes | `matchup.postOnFirst.link` |  |
| `matchup_post_on_third_id` | int32 | yes | `matchup.postOnThird.id` |  |
| `matchup_post_on_third_full_name` | string | yes | `matchup.postOnThird.fullName` |  |
| `matchup_post_on_third_link` | string | yes | `matchup.postOnThird.link` |  |
| `review_details_is_overturned` | bool | yes | `reviewDetails.isOverturned` |  |
| `review_details_in_progress` | bool | yes | `reviewDetails.inProgress` |  |
| `review_details_review_type` | string | yes | `reviewDetails.reviewType` |  |
| `review_details_challenge_team_id` | int32 | yes | `reviewDetails.challengeTeamId` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_win_probability -->

<!-- BEGIN GENERATED:mlb_api.jobs_datacasters -->
### Dataset: jobs_datacasters

Current datacasters (the upstream listing repeats some people, so the key is not unique).

- **View:** `mlb_jobs_datacasters`
- **Processed path:** `processed/mlb_api/jobs_datacasters/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `person_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `job` | string | yes | — |  |
| `job_id` | string | yes | `jobId` |  |
| `title` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.jobs_datacasters -->

<!-- BEGIN GENERATED:mlb_api.jobs_official_scorers -->
### Dataset: jobs_official_scorers

Current official scorers (the upstream listing repeats some people, so the key is not unique).

- **View:** `mlb_jobs_official_scorers`
- **Processed path:** `processed/mlb_api/jobs_official_scorers/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `person_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `job` | string | yes | — |  |
| `job_id` | string | yes | `jobId` |  |
| `title` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.jobs_official_scorers -->

<!-- BEGIN GENERATED:mlb_api.jobs_umpires -->
### Dataset: jobs_umpires

Current umpire roster.

- **View:** `mlb_jobs_umpires`
- **Processed path:** `processed/mlb_api/jobs_umpires/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `person_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `job` | string | yes | — |  |
| `job_id` | string | yes | `jobId` |  |
| `title` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.jobs_umpires -->

<!-- BEGIN GENERATED:mlb_api.leagues_season -->
### Dataset: leagues_season

Leagues of a season.

- **View:** `mlb_leagues_season`
- **Processed path:** `processed/mlb_api/leagues_season/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `link` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `name_short` | string | yes | `nameShort` |  |
| `season_state` | string | yes | `seasonState` |  |
| `has_wild_card` | bool | yes | `hasWildCard` |  |
| `has_split_season` | bool | yes | `hasSplitSeason` |  |
| `num_games` | int32 | yes | `numGames` |  |
| `has_playoff_points` | bool | yes | `hasPlayoffPoints` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `num_wildcard_teams` | int32 | yes | `numWildcardTeams` |  |
| `season_date_info_season_id` | string | yes | `seasonDateInfo.seasonId` |  |
| `season_date_info_pre_season_start_date` | date32[day] | yes | `seasonDateInfo.preSeasonStartDate` |  |
| `season_date_info_pre_season_end_date` | date32[day] | yes | `seasonDateInfo.preSeasonEndDate` |  |
| `season_date_info_season_start_date` | date32[day] | yes | `seasonDateInfo.seasonStartDate` |  |
| `season_date_info_spring_start_date` | date32[day] | yes | `seasonDateInfo.springStartDate` |  |
| `season_date_info_spring_end_date` | date32[day] | yes | `seasonDateInfo.springEndDate` |  |
| `season_date_info_regular_season_start_date` | date32[day] | yes | `seasonDateInfo.regularSeasonStartDate` |  |
| `season_date_info_last_date1st_half` | date32[day] | yes | `seasonDateInfo.lastDate1stHalf` |  |
| `season_date_info_all_star_date` | date32[day] | yes | `seasonDateInfo.allStarDate` |  |
| `season_date_info_first_date2nd_half` | date32[day] | yes | `seasonDateInfo.firstDate2ndHalf` |  |
| `season_date_info_regular_season_end_date` | date32[day] | yes | `seasonDateInfo.regularSeasonEndDate` |  |
| `season_date_info_post_season_start_date` | date32[day] | yes | `seasonDateInfo.postSeasonStartDate` |  |
| `season_date_info_post_season_end_date` | date32[day] | yes | `seasonDateInfo.postSeasonEndDate` |  |
| `season_date_info_season_end_date` | date32[day] | yes | `seasonDateInfo.seasonEndDate` |  |
| `season_date_info_offseason_start_date` | date32[day] | yes | `seasonDateInfo.offseasonStartDate` |  |
| `season_date_info_off_season_end_date` | date32[day] | yes | `seasonDateInfo.offSeasonEndDate` |  |
| `season_date_info_season_level_gameday_type` | string | yes | `seasonDateInfo.seasonLevelGamedayType` |  |
| `season_date_info_game_level_gameday_type` | string | yes | `seasonDateInfo.gameLevelGamedayType` |  |
| `season_date_info_qualifier_plate_appearances` | double | yes | `seasonDateInfo.qualifierPlateAppearances` |  |
| `season_date_info_qualifier_outs_pitched` | double | yes | `seasonDateInfo.qualifierOutsPitched` |  |
| `season` | string | yes | — |  |
| `org_code` | string | yes | `orgCode` |  |
| `conferences_in_use` | bool | yes | `conferencesInUse` |  |
| `divisions_in_use` | bool | yes | `divisionsInUse` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `active` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.leagues_season -->

<!-- BEGIN GENERATED:mlb_api.players_season -->
### Dataset: players_season

Every player of a sport-season with biographical fields.

- **View:** `mlb_players_season`
- **Processed path:** `processed/mlb_api/players_season/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `id` | int32 | yes | — |  |
| `full_name` | string | yes | `fullName` |  |
| `link` | string | yes | — |  |
| `first_name` | string | yes | `firstName` |  |
| `last_name` | string | yes | `lastName` |  |
| `primary_number` | string | yes | `primaryNumber` |  |
| `birth_date` | date32[day] | yes | `birthDate` |  |
| `current_age` | int32 | yes | `currentAge` |  |
| `birth_city` | string | yes | `birthCity` |  |
| `birth_state_province` | string | yes | `birthStateProvince` |  |
| `birth_country` | string | yes | `birthCountry` |  |
| `height` | string | yes | — |  |
| `weight` | int32 | yes | — |  |
| `active` | bool | yes | — |  |
| `current_team_id` | int32 | yes | `currentTeam.id` |  |
| `current_team_name` | string | yes | `currentTeam.name` |  |
| `current_team_link` | string | yes | `currentTeam.link` |  |
| `primary_position_code` | string | yes | `primaryPosition.code` |  |
| `primary_position_name` | string | yes | `primaryPosition.name` |  |
| `primary_position_type` | string | yes | `primaryPosition.type` |  |
| `primary_position_abbreviation` | string | yes | `primaryPosition.abbreviation` |  |
| `use_name` | string | yes | `useName` |  |
| `use_last_name` | string | yes | `useLastName` |  |
| `middle_name` | string | yes | `middleName` |  |
| `boxscore_name` | string | yes | `boxscoreName` |  |
| `gender` | string | yes | — |  |
| `is_player` | bool | yes | `isPlayer` |  |
| `is_verified` | bool | yes | `isVerified` |  |
| `draft_year` | int32 | yes | `draftYear` |  |
| `mlb_debut_date` | date32[day] | yes | `mlbDebutDate` |  |
| `bat_side_code` | string | yes | `batSide.code` |  |
| `bat_side_description` | string | yes | `batSide.description` |  |
| `pitch_hand_code` | string | yes | `pitchHand.code` |  |
| `pitch_hand_description` | string | yes | `pitchHand.description` |  |
| `name_first_last` | string | yes | `nameFirstLast` |  |
| `name_slug` | string | yes | `nameSlug` |  |
| `first_last_name` | string | yes | `firstLastName` |  |
| `last_first_name` | string | yes | `lastFirstName` |  |
| `last_init_name` | string | yes | `lastInitName` |  |
| `init_last_name` | string | yes | `initLastName` |  |
| `full_fml_name` | string | yes | `fullFMLName` |  |
| `full_lfm_name` | string | yes | `fullLFMName` |  |
| `strike_zone_top` | double | yes | `strikeZoneTop` |  |
| `strike_zone_bottom` | double | yes | `strikeZoneBottom` |  |
| `name_matrilineal` | string | yes | `nameMatrilineal` |  |
| `nick_name` | string | yes | `nickName` |  |
| `pronunciation` | string | yes | — |  |
| `last_played_date` | date32[day] | yes | `lastPlayedDate` |  |
| `name_title` | string | yes | `nameTitle` |  |
| `name_suffix` | string | yes | `nameSuffix` |  |
| `death_date` | date32[day] | yes | `deathDate` |  |
| `death_city` | string | yes | `deathCity` |  |
| `death_state_province` | string | yes | `deathStateProvince` |  |
| `death_country` | string | yes | `deathCountry` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.players_season -->

<!-- BEGIN GENERATED:mlb_api.ref_awards -->
### Dataset: ref_awards

Award catalog.

- **View:** `mlb_ref_awards`
- **Processed path:** `processed/mlb_api/ref_awards/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | string | yes | — |  |
| `name` | string | yes | — |  |
| `description` | string | yes | — |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `sport_id` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `active` | bool | yes | — |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_link` | string | yes | `league.link` |  |
| `notes` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_awards -->

<!-- BEGIN GENERATED:mlb_api.ref_baseball_stats -->
### Dataset: ref_baseball_stats

Statistic definitions (name, group, lookup param).

- **View:** `mlb_ref_baseball_stats`
- **Processed path:** `processed/mlb_api/ref_baseball_stats/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `name`, `stat_groups`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | — |  |
| `lookup_param` | string | yes | `lookupParam` |  |
| `is_counting` | bool | yes | `isCounting` |  |
| `label` | string | yes | — |  |
| `stat_groups` | string | yes | `statGroups` |  |
| `org_types` | string | yes | `orgTypes` |  |
| `high_low_types` | string | yes | `highLowTypes` |  |
| `streak_levels` | string | yes | `streakLevels` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_baseball_stats -->

<!-- BEGIN GENERATED:mlb_api.ref_conferences -->
### Dataset: ref_conferences

All conferences.

- **View:** `mlb_ref_conferences`
- **Processed path:** `processed/mlb_api/ref_conferences/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `link` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `name_short` | string | yes | `nameShort` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_conferences -->

<!-- BEGIN GENERATED:mlb_api.ref_divisions -->
### Dataset: ref_divisions

All divisions.

- **View:** `mlb_ref_divisions`
- **Processed path:** `processed/mlb_api/ref_divisions/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `season` | string | yes | — |  |
| `name_short` | string | yes | `nameShort` |  |
| `link` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `active` | bool | yes | — |  |
| `num_playoff_teams` | int32 | yes | `numPlayoffTeams` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_divisions -->

<!-- BEGIN GENERATED:mlb_api.ref_event_types -->
### Dataset: ref_event_types

Play event types.

- **View:** `mlb_ref_event_types`
- **Processed path:** `processed/mlb_api/ref_event_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `plate_appearance` | bool | yes | `plateAppearance` |  |
| `hit` | bool | yes | — |  |
| `code` | string | yes | — |  |
| `base_running_event` | bool | yes | `baseRunningEvent` |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_event_types -->

<!-- BEGIN GENERATED:mlb_api.ref_game_status -->
### Dataset: ref_game_status

Game status codes.

- **View:** `mlb_ref_game_status`
- **Processed path:** `processed/mlb_api/ref_game_status/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `status_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `abstract_game_state` | string | yes | `abstractGameState` |  |
| `coded_game_state` | string | yes | `codedGameState` |  |
| `detailed_state` | string | yes | `detailedState` |  |
| `status_code` | string | yes | `statusCode` |  |
| `abstract_game_code` | string | yes | `abstractGameCode` |  |
| `reason` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_game_status -->

<!-- BEGIN GENERATED:mlb_api.ref_game_types -->
### Dataset: ref_game_types

Game type codes (R, P, S, ...).

- **View:** `mlb_ref_game_types`
- **Processed path:** `processed/mlb_api/ref_game_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_game_types -->

<!-- BEGIN GENERATED:mlb_api.ref_hit_trajectories -->
### Dataset: ref_hit_trajectories

Batted-ball trajectories.

- **View:** `mlb_ref_hit_trajectories`
- **Processed path:** `processed/mlb_api/ref_hit_trajectories/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_hit_trajectories -->

<!-- BEGIN GENERATED:mlb_api.ref_job_types -->
### Dataset: ref_job_types

Job (role) types.

- **View:** `mlb_ref_job_types`
- **Processed path:** `processed/mlb_api/ref_job_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `job` | string | yes | — |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_job_types -->

<!-- BEGIN GENERATED:mlb_api.ref_languages -->
### Dataset: ref_languages

Languages.

- **View:** `mlb_ref_languages`
- **Processed path:** `processed/mlb_api/ref_languages/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `language_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `language_id` | int32 | yes | `languageId` |  |
| `language_code` | string | yes | `languageCode` |  |
| `name` | string | yes | — |  |
| `locale` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_languages -->

<!-- BEGIN GENERATED:mlb_api.ref_league -->
### Dataset: ref_league

All leagues.

- **View:** `mlb_ref_league`
- **Processed path:** `processed/mlb_api/ref_league/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `link` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `name_short` | string | yes | `nameShort` |  |
| `season_state` | string | yes | `seasonState` |  |
| `has_wild_card` | bool | yes | `hasWildCard` |  |
| `has_split_season` | bool | yes | `hasSplitSeason` |  |
| `num_games` | int32 | yes | `numGames` |  |
| `has_playoff_points` | bool | yes | `hasPlayoffPoints` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `num_wildcard_teams` | int32 | yes | `numWildcardTeams` |  |
| `season_date_info_season_id` | string | yes | `seasonDateInfo.seasonId` |  |
| `season_date_info_pre_season_start_date` | date32[day] | yes | `seasonDateInfo.preSeasonStartDate` |  |
| `season_date_info_pre_season_end_date` | date32[day] | yes | `seasonDateInfo.preSeasonEndDate` |  |
| `season_date_info_season_start_date` | date32[day] | yes | `seasonDateInfo.seasonStartDate` |  |
| `season_date_info_spring_start_date` | date32[day] | yes | `seasonDateInfo.springStartDate` |  |
| `season_date_info_spring_end_date` | date32[day] | yes | `seasonDateInfo.springEndDate` |  |
| `season_date_info_regular_season_start_date` | date32[day] | yes | `seasonDateInfo.regularSeasonStartDate` |  |
| `season_date_info_last_date1st_half` | date32[day] | yes | `seasonDateInfo.lastDate1stHalf` |  |
| `season_date_info_all_star_date` | date32[day] | yes | `seasonDateInfo.allStarDate` |  |
| `season_date_info_first_date2nd_half` | date32[day] | yes | `seasonDateInfo.firstDate2ndHalf` |  |
| `season_date_info_regular_season_end_date` | date32[day] | yes | `seasonDateInfo.regularSeasonEndDate` |  |
| `season_date_info_post_season_start_date` | date32[day] | yes | `seasonDateInfo.postSeasonStartDate` |  |
| `season_date_info_post_season_end_date` | date32[day] | yes | `seasonDateInfo.postSeasonEndDate` |  |
| `season_date_info_season_end_date` | date32[day] | yes | `seasonDateInfo.seasonEndDate` |  |
| `season_date_info_offseason_start_date` | date32[day] | yes | `seasonDateInfo.offseasonStartDate` |  |
| `season_date_info_off_season_end_date` | date32[day] | yes | `seasonDateInfo.offSeasonEndDate` |  |
| `season_date_info_season_level_gameday_type` | string | yes | `seasonDateInfo.seasonLevelGamedayType` |  |
| `season_date_info_game_level_gameday_type` | string | yes | `seasonDateInfo.gameLevelGamedayType` |  |
| `season_date_info_qualifier_plate_appearances` | double | yes | `seasonDateInfo.qualifierPlateAppearances` |  |
| `season_date_info_qualifier_outs_pitched` | double | yes | `seasonDateInfo.qualifierOutsPitched` |  |
| `season` | string | yes | — |  |
| `org_code` | string | yes | `orgCode` |  |
| `conferences_in_use` | bool | yes | `conferencesInUse` |  |
| `divisions_in_use` | bool | yes | `divisionsInUse` |  |
| `sport_id` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `active` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_league -->

<!-- BEGIN GENERATED:mlb_api.ref_league_leader_types -->
### Dataset: ref_league_leader_types

League leader categories.

- **View:** `mlb_ref_league_leader_types`
- **Processed path:** `processed/mlb_api/ref_league_leader_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `display_name`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `display_name` | string | yes | `displayName` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_league_leader_types -->

<!-- BEGIN GENERATED:mlb_api.ref_logical_events -->
### Dataset: ref_logical_events

Logical event types.

- **View:** `mlb_ref_logical_events`
- **Processed path:** `processed/mlb_api/ref_logical_events/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_logical_events -->

<!-- BEGIN GENERATED:mlb_api.ref_metrics -->
### Dataset: ref_metrics

Tracking metrics.

- **View:** `mlb_ref_metrics`
- **Processed path:** `processed/mlb_api/ref_metrics/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `name`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | — |  |
| `metric_id` | int32 | yes | `metricId` |  |
| `group` | string | yes | — |  |
| `unit` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_metrics -->

<!-- BEGIN GENERATED:mlb_api.ref_pitch_types -->
### Dataset: ref_pitch_types

Pitch type codes.

- **View:** `mlb_ref_pitch_types`
- **Processed path:** `processed/mlb_api/ref_pitch_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_pitch_types -->

<!-- BEGIN GENERATED:mlb_api.ref_platforms -->
### Dataset: ref_platforms

Platforms.

- **View:** `mlb_ref_platforms`
- **Processed path:** `processed/mlb_api/ref_platforms/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `platform_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `platform_code` | string | yes | `platformCode` |  |
| `platform_description` | string | yes | `platformDescription` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_platforms -->

<!-- BEGIN GENERATED:mlb_api.ref_positions -->
### Dataset: ref_positions

Fielding/lineup positions.

- **View:** `mlb_ref_positions`
- **Processed path:** `processed/mlb_api/ref_positions/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `abbrev`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `short_name` | string | yes | `shortName` |  |
| `full_name` | string | yes | `fullName` |  |
| `abbrev` | string | yes | — |  |
| `code` | string | yes | — |  |
| `type` | string | yes | — |  |
| `formal_name` | string | yes | `formalName` |  |
| `display_name` | string | yes | `displayName` |  |
| `pitcher` | bool | yes | — |  |
| `game_position` | bool | yes | `gamePosition` |  |
| `fielder` | bool | yes | — |  |
| `outfield` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_positions -->

<!-- BEGIN GENERATED:mlb_api.ref_review_reasons -->
### Dataset: ref_review_reasons

Replay review reasons.

- **View:** `mlb_ref_review_reasons`
- **Processed path:** `processed/mlb_api/ref_review_reasons/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_review_reasons -->

<!-- BEGIN GENERATED:mlb_api.ref_roster_types -->
### Dataset: ref_roster_types

Roster types (active, 40Man, fullSeason, ...).

- **View:** `mlb_ref_roster_types`
- **Processed path:** `processed/mlb_api/ref_roster_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `parameter`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `description` | string | yes | — |  |
| `lookup_name` | string | yes | `lookupName` |  |
| `parameter` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_roster_types -->

<!-- BEGIN GENERATED:mlb_api.ref_schedule_event_types -->
### Dataset: ref_schedule_event_types

Schedule event types.

- **View:** `mlb_ref_schedule_event_types`
- **Processed path:** `processed/mlb_api/ref_schedule_event_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `name` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_schedule_event_types -->

<!-- BEGIN GENERATED:mlb_api.ref_schedule_types -->
### Dataset: ref_schedule_types

Schedule types.

- **View:** `mlb_ref_schedule_types`
- **Processed path:** `processed/mlb_api/ref_schedule_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_schedule_types -->

<!-- BEGIN GENERATED:mlb_api.ref_situation_codes -->
### Dataset: ref_situation_codes

Situation (split) codes.

- **View:** `mlb_ref_situation_codes`
- **Processed path:** `processed/mlb_api/ref_situation_codes/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `navigation_menu` | string | yes | `navigationMenu` |  |
| `description` | string | yes | — |  |
| `team` | bool | yes | — |  |
| `batting` | bool | yes | — |  |
| `fielding` | bool | yes | — |  |
| `pitching` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_situation_codes -->

<!-- BEGIN GENERATED:mlb_api.ref_sports -->
### Dataset: ref_sports

Sports / levels (MLB, AAA, ...).

- **View:** `mlb_ref_sports`
- **Processed path:** `processed/mlb_api/ref_sports/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | int32 | yes | — |  |
| `code` | string | yes | — |  |
| `link` | string | yes | — |  |
| `name` | string | yes | — |  |
| `abbreviation` | string | yes | — |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `active_status` | bool | yes | `activeStatus` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_sports -->

<!-- BEGIN GENERATED:mlb_api.ref_standings_types -->
### Dataset: ref_standings_types

Standings types (regularSeason, wildCard, ...).

- **View:** `mlb_ref_standings_types`
- **Processed path:** `processed/mlb_api/ref_standings_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `name`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_standings_types -->

<!-- BEGIN GENERATED:mlb_api.ref_stat_groups -->
### Dataset: ref_stat_groups

Stat groups (hitting, pitching, fielding, ...).

- **View:** `mlb_ref_stat_groups`
- **Processed path:** `processed/mlb_api/ref_stat_groups/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `display_name`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `display_name` | string | yes | `displayName` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_stat_groups -->

<!-- BEGIN GENERATED:mlb_api.ref_stat_types -->
### Dataset: ref_stat_types

Stat type names usable in /v1/stats (season, career, gameLog, ...).

- **View:** `mlb_ref_stat_types`
- **Processed path:** `processed/mlb_api/ref_stat_types/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `display_name`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `display_name` | string | yes | `displayName` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_stat_types -->

<!-- BEGIN GENERATED:mlb_api.ref_wind_direction -->
### Dataset: ref_wind_direction

Wind direction codes.

- **View:** `mlb_ref_wind_direction`
- **Processed path:** `processed/mlb_api/ref_wind_direction/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `code` | string | yes | — |  |
| `description` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.ref_wind_direction -->

<!-- BEGIN GENERATED:mlb_api.schedule_hydrated -->
### Dataset: schedule_hydrated

Season schedule with team, linescore, decisions, probable pitchers, officials, weather, venue, broadcasts, series and flags hydrated.

- **View:** `mlb_schedule_hydrated`
- **Processed path:** `processed/mlb_api/schedule_hydrated/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `dates_date`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `dates_date` | date32[day] | yes | `dates.date` |  |
| `dates_total_items` | int32 | yes | `dates.totalItems` |  |
| `dates_total_events` | int32 | yes | `dates.totalEvents` |  |
| `dates_total_games` | int32 | yes | `dates.totalGames` |  |
| `dates_total_games_in_progress` | int32 | yes | `dates.totalGamesInProgress` |  |
| `dates_events` | string | yes | `dates.events` |  |
| `game_pk` | int32 | yes | `gamePk` |  |
| `game_guid` | string | yes | `gameGuid` |  |
| `link` | string | yes | — |  |
| `game_type` | string | yes | `gameType` |  |
| `season` | string | yes | — |  |
| `game_date` | timestamp[us, tz=UTC] | yes | `gameDate` |  |
| `official_date` | date32[day] | yes | `officialDate` |  |
| `status_abstract_game_state` | string | yes | `status.abstractGameState` |  |
| `status_coded_game_state` | string | yes | `status.codedGameState` |  |
| `status_detailed_state` | string | yes | `status.detailedState` |  |
| `status_status_code` | string | yes | `status.statusCode` |  |
| `status_start_time_tbd` | bool | yes | `status.startTimeTBD` |  |
| `status_abstract_game_code` | string | yes | `status.abstractGameCode` |  |
| `teams_away_team_spring_league_id` | int32 | yes | `teams.away.team.springLeague.id` |  |
| `teams_away_team_spring_league_name` | string | yes | `teams.away.team.springLeague.name` |  |
| `teams_away_team_spring_league_link` | string | yes | `teams.away.team.springLeague.link` |  |
| `teams_away_team_spring_league_abbreviation` | string | yes | `teams.away.team.springLeague.abbreviation` |  |
| `teams_away_team_all_star_status` | string | yes | `teams.away.team.allStarStatus` |  |
| `teams_away_team_id` | int32 | yes | `teams.away.team.id` |  |
| `teams_away_team_name` | string | yes | `teams.away.team.name` |  |
| `teams_away_team_link` | string | yes | `teams.away.team.link` |  |
| `teams_away_team_season` | int32 | yes | `teams.away.team.season` |  |
| `teams_away_team_venue_id` | int32 | yes | `teams.away.team.venue.id` |  |
| `teams_away_team_venue_name` | string | yes | `teams.away.team.venue.name` |  |
| `teams_away_team_venue_link` | string | yes | `teams.away.team.venue.link` |  |
| `teams_away_team_spring_venue_id` | int32 | yes | `teams.away.team.springVenue.id` |  |
| `teams_away_team_spring_venue_link` | string | yes | `teams.away.team.springVenue.link` |  |
| `teams_away_team_team_code` | string | yes | `teams.away.team.teamCode` |  |
| `teams_away_team_file_code` | string | yes | `teams.away.team.fileCode` |  |
| `teams_away_team_abbreviation` | string | yes | `teams.away.team.abbreviation` |  |
| `teams_away_team_team_name` | string | yes | `teams.away.team.teamName` |  |
| `teams_away_team_location_name` | string | yes | `teams.away.team.locationName` |  |
| `teams_away_team_first_year_of_play` | string | yes | `teams.away.team.firstYearOfPlay` |  |
| `teams_away_team_league_id` | int32 | yes | `teams.away.team.league.id` |  |
| `teams_away_team_league_name` | string | yes | `teams.away.team.league.name` |  |
| `teams_away_team_league_link` | string | yes | `teams.away.team.league.link` |  |
| `teams_away_team_division_id` | int32 | yes | `teams.away.team.division.id` |  |
| `teams_away_team_division_name` | string | yes | `teams.away.team.division.name` |  |
| `teams_away_team_division_link` | string | yes | `teams.away.team.division.link` |  |
| `teams_away_team_sport_id` | int32 | yes | `teams.away.team.sport.id` |  |
| `teams_away_team_sport_link` | string | yes | `teams.away.team.sport.link` |  |
| `teams_away_team_sport_name` | string | yes | `teams.away.team.sport.name` |  |
| `teams_away_team_short_name` | string | yes | `teams.away.team.shortName` |  |
| `teams_away_team_franchise_name` | string | yes | `teams.away.team.franchiseName` |  |
| `teams_away_team_club_name` | string | yes | `teams.away.team.clubName` |  |
| `teams_away_team_active` | bool | yes | `teams.away.team.active` |  |
| `teams_away_league_record_wins` | int32 | yes | `teams.away.leagueRecord.wins` |  |
| `teams_away_league_record_losses` | int32 | yes | `teams.away.leagueRecord.losses` |  |
| `teams_away_league_record_ties` | int32 | yes | `teams.away.leagueRecord.ties` |  |
| `teams_away_league_record_pct` | string | yes | `teams.away.leagueRecord.pct` |  |
| `teams_away_score` | int32 | yes | `teams.away.score` |  |
| `teams_away_is_winner` | bool | yes | `teams.away.isWinner` |  |
| `teams_away_probable_pitcher_id` | int32 | yes | `teams.away.probablePitcher.id` |  |
| `teams_away_probable_pitcher_full_name` | string | yes | `teams.away.probablePitcher.fullName` |  |
| `teams_away_probable_pitcher_link` | string | yes | `teams.away.probablePitcher.link` |  |
| `teams_away_split_squad` | bool | yes | `teams.away.splitSquad` |  |
| `teams_away_series_number` | int32 | yes | `teams.away.seriesNumber` |  |
| `teams_away_spring_league_id` | int32 | yes | `teams.away.springLeague.id` |  |
| `teams_away_spring_league_name` | string | yes | `teams.away.springLeague.name` |  |
| `teams_away_spring_league_link` | string | yes | `teams.away.springLeague.link` |  |
| `teams_away_spring_league_abbreviation` | string | yes | `teams.away.springLeague.abbreviation` |  |
| `teams_home_team_spring_league_id` | int32 | yes | `teams.home.team.springLeague.id` |  |
| `teams_home_team_spring_league_name` | string | yes | `teams.home.team.springLeague.name` |  |
| `teams_home_team_spring_league_link` | string | yes | `teams.home.team.springLeague.link` |  |
| `teams_home_team_spring_league_abbreviation` | string | yes | `teams.home.team.springLeague.abbreviation` |  |
| `teams_home_team_all_star_status` | string | yes | `teams.home.team.allStarStatus` |  |
| `teams_home_team_id` | int32 | yes | `teams.home.team.id` |  |
| `teams_home_team_name` | string | yes | `teams.home.team.name` |  |
| `teams_home_team_link` | string | yes | `teams.home.team.link` |  |
| `teams_home_team_season` | int32 | yes | `teams.home.team.season` |  |
| `teams_home_team_venue_id` | int32 | yes | `teams.home.team.venue.id` |  |
| `teams_home_team_venue_name` | string | yes | `teams.home.team.venue.name` |  |
| `teams_home_team_venue_link` | string | yes | `teams.home.team.venue.link` |  |
| `teams_home_team_spring_venue_id` | int32 | yes | `teams.home.team.springVenue.id` |  |
| `teams_home_team_spring_venue_link` | string | yes | `teams.home.team.springVenue.link` |  |
| `teams_home_team_team_code` | string | yes | `teams.home.team.teamCode` |  |
| `teams_home_team_file_code` | string | yes | `teams.home.team.fileCode` |  |
| `teams_home_team_abbreviation` | string | yes | `teams.home.team.abbreviation` |  |
| `teams_home_team_team_name` | string | yes | `teams.home.team.teamName` |  |
| `teams_home_team_location_name` | string | yes | `teams.home.team.locationName` |  |
| `teams_home_team_first_year_of_play` | string | yes | `teams.home.team.firstYearOfPlay` |  |
| `teams_home_team_league_id` | int32 | yes | `teams.home.team.league.id` |  |
| `teams_home_team_league_name` | string | yes | `teams.home.team.league.name` |  |
| `teams_home_team_league_link` | string | yes | `teams.home.team.league.link` |  |
| `teams_home_team_division_id` | int32 | yes | `teams.home.team.division.id` |  |
| `teams_home_team_division_name` | string | yes | `teams.home.team.division.name` |  |
| `teams_home_team_division_link` | string | yes | `teams.home.team.division.link` |  |
| `teams_home_team_sport_id` | int32 | yes | `teams.home.team.sport.id` |  |
| `teams_home_team_sport_link` | string | yes | `teams.home.team.sport.link` |  |
| `teams_home_team_sport_name` | string | yes | `teams.home.team.sport.name` |  |
| `teams_home_team_short_name` | string | yes | `teams.home.team.shortName` |  |
| `teams_home_team_franchise_name` | string | yes | `teams.home.team.franchiseName` |  |
| `teams_home_team_club_name` | string | yes | `teams.home.team.clubName` |  |
| `teams_home_team_active` | bool | yes | `teams.home.team.active` |  |
| `teams_home_league_record_wins` | int32 | yes | `teams.home.leagueRecord.wins` |  |
| `teams_home_league_record_losses` | int32 | yes | `teams.home.leagueRecord.losses` |  |
| `teams_home_league_record_ties` | int32 | yes | `teams.home.leagueRecord.ties` |  |
| `teams_home_league_record_pct` | string | yes | `teams.home.leagueRecord.pct` |  |
| `teams_home_score` | int32 | yes | `teams.home.score` |  |
| `teams_home_is_winner` | bool | yes | `teams.home.isWinner` |  |
| `teams_home_probable_pitcher_id` | int32 | yes | `teams.home.probablePitcher.id` |  |
| `teams_home_probable_pitcher_full_name` | string | yes | `teams.home.probablePitcher.fullName` |  |
| `teams_home_probable_pitcher_link` | string | yes | `teams.home.probablePitcher.link` |  |
| `teams_home_split_squad` | bool | yes | `teams.home.splitSquad` |  |
| `teams_home_series_number` | int32 | yes | `teams.home.seriesNumber` |  |
| `teams_home_spring_league_id` | int32 | yes | `teams.home.springLeague.id` |  |
| `teams_home_spring_league_name` | string | yes | `teams.home.springLeague.name` |  |
| `teams_home_spring_league_link` | string | yes | `teams.home.springLeague.link` |  |
| `teams_home_spring_league_abbreviation` | string | yes | `teams.home.springLeague.abbreviation` |  |
| `linescore_current_inning` | int32 | yes | `linescore.currentInning` |  |
| `linescore_current_inning_ordinal` | string | yes | `linescore.currentInningOrdinal` |  |
| `linescore_inning_state` | string | yes | `linescore.inningState` |  |
| `linescore_inning_half` | string | yes | `linescore.inningHalf` |  |
| `linescore_is_top_inning` | bool | yes | `linescore.isTopInning` |  |
| `linescore_scheduled_innings` | int32 | yes | `linescore.scheduledInnings` |  |
| `linescore_innings` | string | yes | `linescore.innings` |  |
| `linescore_teams_home_runs` | int32 | yes | `linescore.teams.home.runs` |  |
| `linescore_teams_home_hits` | int32 | yes | `linescore.teams.home.hits` |  |
| `linescore_teams_home_errors` | int32 | yes | `linescore.teams.home.errors` |  |
| `linescore_teams_home_left_on_base` | int32 | yes | `linescore.teams.home.leftOnBase` |  |
| `linescore_teams_home_is_winner` | bool | yes | `linescore.teams.home.isWinner` |  |
| `linescore_teams_away_runs` | int32 | yes | `linescore.teams.away.runs` |  |
| `linescore_teams_away_hits` | int32 | yes | `linescore.teams.away.hits` |  |
| `linescore_teams_away_errors` | int32 | yes | `linescore.teams.away.errors` |  |
| `linescore_teams_away_left_on_base` | int32 | yes | `linescore.teams.away.leftOnBase` |  |
| `linescore_teams_away_is_winner` | bool | yes | `linescore.teams.away.isWinner` |  |
| `linescore_defense_pitcher_id` | int32 | yes | `linescore.defense.pitcher.id` |  |
| `linescore_defense_pitcher_full_name` | string | yes | `linescore.defense.pitcher.fullName` |  |
| `linescore_defense_pitcher_link` | string | yes | `linescore.defense.pitcher.link` |  |
| `linescore_defense_catcher_id` | int32 | yes | `linescore.defense.catcher.id` |  |
| `linescore_defense_catcher_full_name` | string | yes | `linescore.defense.catcher.fullName` |  |
| `linescore_defense_catcher_link` | string | yes | `linescore.defense.catcher.link` |  |
| `linescore_defense_first_id` | int32 | yes | `linescore.defense.first.id` |  |
| `linescore_defense_first_full_name` | string | yes | `linescore.defense.first.fullName` |  |
| `linescore_defense_first_link` | string | yes | `linescore.defense.first.link` |  |
| `linescore_defense_second_id` | int32 | yes | `linescore.defense.second.id` |  |
| `linescore_defense_second_full_name` | string | yes | `linescore.defense.second.fullName` |  |
| `linescore_defense_second_link` | string | yes | `linescore.defense.second.link` |  |
| `linescore_defense_third_id` | int32 | yes | `linescore.defense.third.id` |  |
| `linescore_defense_third_full_name` | string | yes | `linescore.defense.third.fullName` |  |
| `linescore_defense_third_link` | string | yes | `linescore.defense.third.link` |  |
| `linescore_defense_shortstop_id` | int32 | yes | `linescore.defense.shortstop.id` |  |
| `linescore_defense_shortstop_full_name` | string | yes | `linescore.defense.shortstop.fullName` |  |
| `linescore_defense_shortstop_link` | string | yes | `linescore.defense.shortstop.link` |  |
| `linescore_defense_left_id` | int32 | yes | `linescore.defense.left.id` |  |
| `linescore_defense_left_full_name` | string | yes | `linescore.defense.left.fullName` |  |
| `linescore_defense_left_link` | string | yes | `linescore.defense.left.link` |  |
| `linescore_defense_center_id` | int32 | yes | `linescore.defense.center.id` |  |
| `linescore_defense_center_full_name` | string | yes | `linescore.defense.center.fullName` |  |
| `linescore_defense_center_link` | string | yes | `linescore.defense.center.link` |  |
| `linescore_defense_right_id` | int32 | yes | `linescore.defense.right.id` |  |
| `linescore_defense_right_full_name` | string | yes | `linescore.defense.right.fullName` |  |
| `linescore_defense_right_link` | string | yes | `linescore.defense.right.link` |  |
| `linescore_defense_batter_id` | int32 | yes | `linescore.defense.batter.id` |  |
| `linescore_defense_batter_full_name` | string | yes | `linescore.defense.batter.fullName` |  |
| `linescore_defense_batter_link` | string | yes | `linescore.defense.batter.link` |  |
| `linescore_defense_on_deck_id` | int32 | yes | `linescore.defense.onDeck.id` |  |
| `linescore_defense_on_deck_full_name` | string | yes | `linescore.defense.onDeck.fullName` |  |
| `linescore_defense_on_deck_link` | string | yes | `linescore.defense.onDeck.link` |  |
| `linescore_defense_in_hole_id` | int32 | yes | `linescore.defense.inHole.id` |  |
| `linescore_defense_in_hole_full_name` | string | yes | `linescore.defense.inHole.fullName` |  |
| `linescore_defense_in_hole_link` | string | yes | `linescore.defense.inHole.link` |  |
| `linescore_defense_batting_order` | int32 | yes | `linescore.defense.battingOrder` |  |
| `linescore_defense_team_id` | int32 | yes | `linescore.defense.team.id` |  |
| `linescore_defense_team_name` | string | yes | `linescore.defense.team.name` |  |
| `linescore_defense_team_link` | string | yes | `linescore.defense.team.link` |  |
| `linescore_offense_batter_id` | int32 | yes | `linescore.offense.batter.id` |  |
| `linescore_offense_batter_full_name` | string | yes | `linescore.offense.batter.fullName` |  |
| `linescore_offense_batter_link` | string | yes | `linescore.offense.batter.link` |  |
| `linescore_offense_on_deck_id` | int32 | yes | `linescore.offense.onDeck.id` |  |
| `linescore_offense_on_deck_full_name` | string | yes | `linescore.offense.onDeck.fullName` |  |
| `linescore_offense_on_deck_link` | string | yes | `linescore.offense.onDeck.link` |  |
| `linescore_offense_in_hole_id` | int32 | yes | `linescore.offense.inHole.id` |  |
| `linescore_offense_in_hole_full_name` | string | yes | `linescore.offense.inHole.fullName` |  |
| `linescore_offense_in_hole_link` | string | yes | `linescore.offense.inHole.link` |  |
| `linescore_offense_pitcher_id` | int32 | yes | `linescore.offense.pitcher.id` |  |
| `linescore_offense_pitcher_full_name` | string | yes | `linescore.offense.pitcher.fullName` |  |
| `linescore_offense_pitcher_link` | string | yes | `linescore.offense.pitcher.link` |  |
| `linescore_offense_batting_order` | int32 | yes | `linescore.offense.battingOrder` |  |
| `linescore_offense_team_id` | int32 | yes | `linescore.offense.team.id` |  |
| `linescore_offense_team_name` | string | yes | `linescore.offense.team.name` |  |
| `linescore_offense_team_link` | string | yes | `linescore.offense.team.link` |  |
| `linescore_balls` | int32 | yes | `linescore.balls` |  |
| `linescore_strikes` | int32 | yes | `linescore.strikes` |  |
| `linescore_outs` | int32 | yes | `linescore.outs` |  |
| `decisions_winner_id` | int32 | yes | `decisions.winner.id` |  |
| `decisions_winner_full_name` | string | yes | `decisions.winner.fullName` |  |
| `decisions_winner_link` | string | yes | `decisions.winner.link` |  |
| `decisions_loser_id` | int32 | yes | `decisions.loser.id` |  |
| `decisions_loser_full_name` | string | yes | `decisions.loser.fullName` |  |
| `decisions_loser_link` | string | yes | `decisions.loser.link` |  |
| `venue_id` | int32 | yes | `venue.id` |  |
| `venue_name` | string | yes | `venue.name` |  |
| `venue_link` | string | yes | `venue.link` |  |
| `venue_active` | bool | yes | `venue.active` |  |
| `venue_season` | string | yes | `venue.season` |  |
| `broadcasts` | string | yes | — |  |
| `content_link` | string | yes | `content.link` |  |
| `is_tie` | bool | yes | `isTie` |  |
| `officials` | string | yes | — |  |
| `weather_condition` | string | yes | `weather.condition` |  |
| `weather_temp` | string | yes | `weather.temp` |  |
| `weather_wind` | string | yes | `weather.wind` |  |
| `game_number` | int32 | yes | `gameNumber` |  |
| `public_facing` | bool | yes | `publicFacing` |  |
| `double_header` | string | yes | `doubleHeader` |  |
| `gameday_type` | string | yes | `gamedayType` |  |
| `tiebreaker` | string | yes | — |  |
| `calendar_event_id` | string | yes | `calendarEventID` |  |
| `season_display` | string | yes | `seasonDisplay` |  |
| `day_night` | string | yes | `dayNight` |  |
| `scheduled_innings` | int32 | yes | `scheduledInnings` |  |
| `reverse_home_away_status` | bool | yes | `reverseHomeAwayStatus` |  |
| `inning_break_length` | int32 | yes | `inningBreakLength` |  |
| `games_in_series` | int32 | yes | `gamesInSeries` |  |
| `series_game_number` | int32 | yes | `seriesGameNumber` |  |
| `series_description` | string | yes | `seriesDescription` |  |
| `flags_no_hitter` | bool | yes | `flags.noHitter` |  |
| `flags_perfect_game` | bool | yes | `flags.perfectGame` |  |
| `flags_away_team_no_hitter` | bool | yes | `flags.awayTeamNoHitter` |  |
| `flags_away_team_perfect_game` | bool | yes | `flags.awayTeamPerfectGame` |  |
| `flags_home_team_no_hitter` | bool | yes | `flags.homeTeamNoHitter` |  |
| `flags_home_team_perfect_game` | bool | yes | `flags.homeTeamPerfectGame` |  |
| `record_source` | string | yes | `recordSource` |  |
| `if_necessary` | string | yes | `ifNecessary` |  |
| `if_necessary_description` | string | yes | `ifNecessaryDescription` |  |
| `teams_away_team_parent_org_name` | string | yes | `teams.away.team.parentOrgName` |  |
| `teams_away_team_parent_org_id` | int32 | yes | `teams.away.team.parentOrgId` |  |
| `linescore_note` | string | yes | `linescore.note` |  |
| `linescore_offense_first_id` | int32 | yes | `linescore.offense.first.id` |  |
| `linescore_offense_first_full_name` | string | yes | `linescore.offense.first.fullName` |  |
| `linescore_offense_first_link` | string | yes | `linescore.offense.first.link` |  |
| `decisions_save_id` | int32 | yes | `decisions.save.id` |  |
| `decisions_save_full_name` | string | yes | `decisions.save.fullName` |  |
| `decisions_save_link` | string | yes | `decisions.save.link` |  |
| `linescore_offense_second_id` | int32 | yes | `linescore.offense.second.id` |  |
| `linescore_offense_second_full_name` | string | yes | `linescore.offense.second.fullName` |  |
| `linescore_offense_second_link` | string | yes | `linescore.offense.second.link` |  |
| `linescore_offense_third_id` | int32 | yes | `linescore.offense.third.id` |  |
| `linescore_offense_third_full_name` | string | yes | `linescore.offense.third.fullName` |  |
| `linescore_offense_third_link` | string | yes | `linescore.offense.third.link` |  |
| `status_reason` | string | yes | `status.reason` |  |
| `description` | string | yes | — |  |
| `teams_home_team_parent_org_name` | string | yes | `teams.home.team.parentOrgName` |  |
| `teams_home_team_parent_org_id` | int32 | yes | `teams.home.team.parentOrgId` |  |
| `reschedule_date` | timestamp[us, tz=UTC] | yes | `rescheduleDate` |  |
| `reschedule_game_date` | date32[day] | yes | `rescheduleGameDate` |  |
| `rescheduled_from` | timestamp[us, tz=UTC] | yes | `rescheduledFrom` |  |
| `rescheduled_from_date` | date32[day] | yes | `rescheduledFromDate` |  |
| `resume_date` | timestamp[us, tz=UTC] | yes | `resumeDate` |  |
| `resume_game_date` | date32[day] | yes | `resumeGameDate` |  |
| `resumed_from` | timestamp[us, tz=UTC] | yes | `resumedFrom` |  |
| `resumed_from_date` | date32[day] | yes | `resumedFromDate` |  |
| `teams_home_team_conference_id` | int32 | yes | `teams.home.team.conference.id` |  |
| `teams_home_team_conference_name` | string | yes | `teams.home.team.conference.name` |  |
| `teams_home_team_conference_link` | string | yes | `teams.home.team.conference.link` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.schedule_hydrated -->

<!-- BEGIN GENERATED:mlb_api.schedule_postseason -->
### Dataset: schedule_postseason

Postseason games of a season.

- **View:** `mlb_schedule_postseason`
- **Processed path:** `processed/mlb_api/schedule_postseason/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `dates_date` | date32[day] | yes | `dates.date` |  |
| `dates_total_items` | int32 | yes | `dates.totalItems` |  |
| `dates_total_events` | int32 | yes | `dates.totalEvents` |  |
| `dates_total_games` | int32 | yes | `dates.totalGames` |  |
| `dates_total_games_in_progress` | int32 | yes | `dates.totalGamesInProgress` |  |
| `dates_events` | string | yes | `dates.events` |  |
| `game_pk` | int32 | yes | `gamePk` |  |
| `game_guid` | string | yes | `gameGuid` |  |
| `link` | string | yes | — |  |
| `game_type` | string | yes | `gameType` |  |
| `season` | string | yes | — |  |
| `game_date` | timestamp[us, tz=UTC] | yes | `gameDate` |  |
| `official_date` | date32[day] | yes | `officialDate` |  |
| `status_abstract_game_state` | string | yes | `status.abstractGameState` |  |
| `status_coded_game_state` | string | yes | `status.codedGameState` |  |
| `status_detailed_state` | string | yes | `status.detailedState` |  |
| `status_status_code` | string | yes | `status.statusCode` |  |
| `status_start_time_tbd` | bool | yes | `status.startTimeTBD` |  |
| `status_abstract_game_code` | string | yes | `status.abstractGameCode` |  |
| `teams_away_team_id` | int32 | yes | `teams.away.team.id` |  |
| `teams_away_team_name` | string | yes | `teams.away.team.name` |  |
| `teams_away_team_link` | string | yes | `teams.away.team.link` |  |
| `teams_away_league_record_wins` | int32 | yes | `teams.away.leagueRecord.wins` |  |
| `teams_away_league_record_losses` | int32 | yes | `teams.away.leagueRecord.losses` |  |
| `teams_away_league_record_ties` | int32 | yes | `teams.away.leagueRecord.ties` |  |
| `teams_away_league_record_pct` | string | yes | `teams.away.leagueRecord.pct` |  |
| `teams_away_score` | int32 | yes | `teams.away.score` |  |
| `teams_away_is_winner` | bool | yes | `teams.away.isWinner` |  |
| `teams_away_split_squad` | bool | yes | `teams.away.splitSquad` |  |
| `teams_away_series_number` | int32 | yes | `teams.away.seriesNumber` |  |
| `teams_home_team_id` | int32 | yes | `teams.home.team.id` |  |
| `teams_home_team_name` | string | yes | `teams.home.team.name` |  |
| `teams_home_team_link` | string | yes | `teams.home.team.link` |  |
| `teams_home_league_record_wins` | int32 | yes | `teams.home.leagueRecord.wins` |  |
| `teams_home_league_record_losses` | int32 | yes | `teams.home.leagueRecord.losses` |  |
| `teams_home_league_record_ties` | int32 | yes | `teams.home.leagueRecord.ties` |  |
| `teams_home_league_record_pct` | string | yes | `teams.home.leagueRecord.pct` |  |
| `teams_home_score` | int32 | yes | `teams.home.score` |  |
| `teams_home_is_winner` | bool | yes | `teams.home.isWinner` |  |
| `teams_home_split_squad` | bool | yes | `teams.home.splitSquad` |  |
| `teams_home_series_number` | int32 | yes | `teams.home.seriesNumber` |  |
| `venue_id` | int32 | yes | `venue.id` |  |
| `venue_name` | string | yes | `venue.name` |  |
| `venue_link` | string | yes | `venue.link` |  |
| `content_link` | string | yes | `content.link` |  |
| `is_tie` | bool | yes | `isTie` |  |
| `is_featured_game` | bool | yes | `isFeaturedGame` |  |
| `game_number` | int32 | yes | `gameNumber` |  |
| `public_facing` | bool | yes | `publicFacing` |  |
| `double_header` | string | yes | `doubleHeader` |  |
| `gameday_type` | string | yes | `gamedayType` |  |
| `tiebreaker` | string | yes | — |  |
| `calendar_event_id` | string | yes | `calendarEventID` |  |
| `season_display` | string | yes | `seasonDisplay` |  |
| `day_night` | string | yes | `dayNight` |  |
| `description` | string | yes | — |  |
| `scheduled_innings` | int32 | yes | `scheduledInnings` |  |
| `reverse_home_away_status` | bool | yes | `reverseHomeAwayStatus` |  |
| `inning_break_length` | int32 | yes | `inningBreakLength` |  |
| `games_in_series` | int32 | yes | `gamesInSeries` |  |
| `series_game_number` | int32 | yes | `seriesGameNumber` |  |
| `series_description` | string | yes | `seriesDescription` |  |
| `record_source` | string | yes | `recordSource` |  |
| `if_necessary` | string | yes | `ifNecessary` |  |
| `if_necessary_description` | string | yes | `ifNecessaryDescription` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.schedule_postseason -->

<!-- BEGIN GENERATED:mlb_api.schedule_postseason_series -->
### Dataset: schedule_postseason_series

Postseason series of a season.

- **View:** `mlb_schedule_postseason_series`
- **Processed path:** `processed/mlb_api/schedule_postseason_series/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `series_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `series_id` | string | yes | `series.id` |  |
| `series_sort_number` | int32 | yes | `series.sortNumber` |  |
| `series_is_default` | bool | yes | `series.isDefault` |  |
| `series_game_type` | string | yes | `series.gameType` |  |
| `total_items` | int32 | yes | `totalItems` |  |
| `total_games` | int32 | yes | `totalGames` |  |
| `total_games_in_progress` | int32 | yes | `totalGamesInProgress` |  |
| `games` | string | yes | — |  |
| `sort_order` | int32 | yes | `sortOrder` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.schedule_postseason_series -->

<!-- BEGIN GENERATED:mlb_api.seasons_all -->
### Dataset: seasons_all

Every season of a sport (calendar dates).

- **View:** `mlb_seasons_all`
- **Processed path:** `processed/mlb_api/seasons_all/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `season_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season_id` | string | yes | `seasonId` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `pre_season_start_date` | date32[day] | yes | `preSeasonStartDate` |  |
| `season_start_date` | date32[day] | yes | `seasonStartDate` |  |
| `regular_season_start_date` | date32[day] | yes | `regularSeasonStartDate` |  |
| `regular_season_end_date` | date32[day] | yes | `regularSeasonEndDate` |  |
| `season_end_date` | date32[day] | yes | `seasonEndDate` |  |
| `offseason_start_date` | date32[day] | yes | `offseasonStartDate` |  |
| `off_season_end_date` | date32[day] | yes | `offSeasonEndDate` |  |
| `season_level_gameday_type` | string | yes | `seasonLevelGamedayType` |  |
| `game_level_gameday_type` | string | yes | `gameLevelGamedayType` |  |
| `qualifier_plate_appearances` | double | yes | `qualifierPlateAppearances` |  |
| `qualifier_outs_pitched` | double | yes | `qualifierOutsPitched` |  |
| `post_season_start_date` | date32[day] | yes | `postSeasonStartDate` |  |
| `post_season_end_date` | date32[day] | yes | `postSeasonEndDate` |  |
| `last_date1st_half` | date32[day] | yes | `lastDate1stHalf` |  |
| `all_star_date` | date32[day] | yes | `allStarDate` |  |
| `first_date2nd_half` | date32[day] | yes | `firstDate2ndHalf` |  |
| `pre_season_end_date` | date32[day] | yes | `preSeasonEndDate` |  |
| `spring_start_date` | date32[day] | yes | `springStartDate` |  |
| `spring_end_date` | date32[day] | yes | `springEndDate` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.seasons_all -->

<!-- BEGIN GENERATED:mlb_api.standings_by_conference -->
### Dataset: standings_by_conference

Standings, type byConference.

- **View:** `mlb_standings_by_conference`
- **Processed path:** `processed/mlb_api/standings_by_conference/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_by_conference -->

<!-- BEGIN GENERATED:mlb_api.standings_by_division -->
### Dataset: standings_by_division

Standings, type byDivision.

- **View:** `mlb_standings_by_division`
- **Processed path:** `processed/mlb_api/standings_by_division/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_by_division -->

<!-- BEGIN GENERATED:mlb_api.standings_by_league -->
### Dataset: standings_by_league

Standings, type byLeague.

- **View:** `mlb_standings_by_league`
- **Processed path:** `processed/mlb_api/standings_by_league/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_by_league -->

<!-- BEGIN GENERATED:mlb_api.standings_by_organization -->
### Dataset: standings_by_organization

Standings, type byOrganization.

- **View:** `mlb_standings_by_organization`
- **Processed path:** `processed/mlb_api/standings_by_organization/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_name` | string | yes | `records.league.name` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_organization_id` | int32 | yes | `records.organization.id` |  |
| `records_organization_name` | string | yes | `records.organization.name` |  |
| `records_organization_link` | string | yes | `records.organization.link` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `records_aggregate_record_games_played` | int32 | yes | `records.aggregateRecord.gamesPlayed` |  |
| `records_aggregate_record_wild_card_games_back` | string | yes | `records.aggregateRecord.wildCardGamesBack` |  |
| `records_aggregate_record_league_games_back` | string | yes | `records.aggregateRecord.leagueGamesBack` |  |
| `records_aggregate_record_spring_league_games_back` | string | yes | `records.aggregateRecord.springLeagueGamesBack` |  |
| `records_aggregate_record_sport_games_back` | string | yes | `records.aggregateRecord.sportGamesBack` |  |
| `records_aggregate_record_division_games_back` | string | yes | `records.aggregateRecord.divisionGamesBack` |  |
| `records_aggregate_record_conference_games_back` | string | yes | `records.aggregateRecord.conferenceGamesBack` |  |
| `records_aggregate_record_league_record_wins` | int32 | yes | `records.aggregateRecord.leagueRecord.wins` |  |
| `records_aggregate_record_league_record_losses` | int32 | yes | `records.aggregateRecord.leagueRecord.losses` |  |
| `records_aggregate_record_league_record_pct` | string | yes | `records.aggregateRecord.leagueRecord.pct` |  |
| `records_aggregate_record_records_split_records` | string | yes | `records.aggregateRecord.records.splitRecords` |  |
| `records_aggregate_record_records_overall_records` | string | yes | `records.aggregateRecord.records.overallRecords` |  |
| `records_aggregate_record_runs_allowed` | int32 | yes | `records.aggregateRecord.runsAllowed` |  |
| `records_aggregate_record_runs_scored` | int32 | yes | `records.aggregateRecord.runsScored` |  |
| `records_aggregate_record_wins` | int32 | yes | `records.aggregateRecord.wins` |  |
| `records_aggregate_record_losses` | int32 | yes | `records.aggregateRecord.losses` |  |
| `records_aggregate_record_run_differential` | int32 | yes | `records.aggregateRecord.runDifferential` |  |
| `records_aggregate_record_winning_percentage` | string | yes | `records.aggregateRecord.winningPercentage` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `team_parent_org_name` | string | yes | `team.parentOrgName` |  |
| `team_parent_org_id` | int32 | yes | `team.parentOrgId` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `conference_rank` | string | yes | `conferenceRank` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_by_organization -->

<!-- BEGIN GENERATED:mlb_api.standings_division_leaders -->
### Dataset: standings_division_leaders

Standings, type divisionLeaders.

- **View:** `mlb_standings_division_leaders`
- **Processed path:** `processed/mlb_api/standings_division_leaders/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_division_leaders -->

<!-- BEGIN GENERATED:mlb_api.standings_regular_season -->
### Dataset: standings_regular_season

Standings, type regularSeason.

- **View:** `mlb_standings_regular_season`
- **Processed path:** `processed/mlb_api/standings_regular_season/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_regular_season -->

<!-- BEGIN GENERATED:mlb_api.standings_spring_training -->
### Dataset: standings_spring_training

Standings, type springTraining.

- **View:** `mlb_standings_spring_training`
- **Processed path:** `processed/mlb_api/standings_spring_training/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_spring_league_id` | int32 | yes | `team.springLeague.id` |  |
| `team_spring_league_name` | string | yes | `team.springLeague.name` |  |
| `team_spring_league_link` | string | yes | `team.springLeague.link` |  |
| `team_spring_league_abbreviation` | string | yes | `team.springLeague.abbreviation` |  |
| `team_all_star_status` | string | yes | `team.allStarStatus` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `team_season` | int32 | yes | `team.season` |  |
| `team_venue_id` | int32 | yes | `team.venue.id` |  |
| `team_venue_name` | string | yes | `team.venue.name` |  |
| `team_venue_link` | string | yes | `team.venue.link` |  |
| `team_spring_venue_id` | int32 | yes | `team.springVenue.id` |  |
| `team_spring_venue_link` | string | yes | `team.springVenue.link` |  |
| `team_team_code` | string | yes | `team.teamCode` |  |
| `team_file_code` | string | yes | `team.fileCode` |  |
| `team_abbreviation` | string | yes | `team.abbreviation` |  |
| `team_team_name` | string | yes | `team.teamName` |  |
| `team_location_name` | string | yes | `team.locationName` |  |
| `team_first_year_of_play` | string | yes | `team.firstYearOfPlay` |  |
| `team_league_id` | int32 | yes | `team.league.id` |  |
| `team_league_name` | string | yes | `team.league.name` |  |
| `team_league_link` | string | yes | `team.league.link` |  |
| `team_division_id` | int32 | yes | `team.division.id` |  |
| `team_division_name` | string | yes | `team.division.name` |  |
| `team_division_link` | string | yes | `team.division.link` |  |
| `team_sport_id` | int32 | yes | `team.sport.id` |  |
| `team_sport_link` | string | yes | `team.sport.link` |  |
| `team_sport_name` | string | yes | `team.sport.name` |  |
| `team_short_name` | string | yes | `team.shortName` |  |
| `team_franchise_name` | string | yes | `team.franchiseName` |  |
| `team_club_name` | string | yes | `team.clubName` |  |
| `team_active` | bool | yes | `team.active` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `spring_league_rank` | string | yes | `springLeagueRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_spring_training -->

<!-- BEGIN GENERATED:mlb_api.standings_wild_card -->
### Dataset: standings_wild_card

Standings, type wildCard.

- **View:** `mlb_standings_wild_card`
- **Processed path:** `processed/mlb_api/standings_wild_card/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_wild_card -->

<!-- BEGIN GENERATED:mlb_api.standings_wild_card_with_leaders -->
### Dataset: standings_wild_card_with_leaders

Standings, type wildCardWithLeaders.

- **View:** `mlb_standings_wild_card_with_leaders`
- **Processed path:** `processed/mlb_api/standings_wild_card_with_leaders/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `records_standings_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `records_standings_type` | string | yes | `records.standingsType` |  |
| `records_league_id` | int32 | yes | `records.league.id` |  |
| `records_league_link` | string | yes | `records.league.link` |  |
| `records_division_id` | int32 | yes | `records.division.id` |  |
| `records_division_link` | string | yes | `records.division.link` |  |
| `records_last_updated` | timestamp[us, tz=UTC] | yes | `records.lastUpdated` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `season` | string | yes | — |  |
| `streak_streak_code` | string | yes | `streak.streakCode` |  |
| `streak_streak_type` | string | yes | `streak.streakType` |  |
| `streak_streak_number` | int32 | yes | `streak.streakNumber` |  |
| `clinch_indicator` | string | yes | `clinchIndicator` |  |
| `division_rank` | string | yes | `divisionRank` |  |
| `league_rank` | string | yes | `leagueRank` |  |
| `wild_card_rank` | string | yes | `wildCardRank` |  |
| `sport_rank` | string | yes | `sportRank` |  |
| `games_played` | int32 | yes | `gamesPlayed` |  |
| `games_back` | string | yes | `gamesBack` |  |
| `wild_card_games_back` | string | yes | `wildCardGamesBack` |  |
| `league_games_back` | string | yes | `leagueGamesBack` |  |
| `spring_league_games_back` | string | yes | `springLeagueGamesBack` |  |
| `sport_games_back` | string | yes | `sportGamesBack` |  |
| `division_games_back` | string | yes | `divisionGamesBack` |  |
| `conference_games_back` | string | yes | `conferenceGamesBack` |  |
| `league_record_wins` | int32 | yes | `leagueRecord.wins` |  |
| `league_record_losses` | int32 | yes | `leagueRecord.losses` |  |
| `league_record_ties` | int32 | yes | `leagueRecord.ties` |  |
| `league_record_pct` | string | yes | `leagueRecord.pct` |  |
| `last_updated` | timestamp[us, tz=UTC] | yes | `lastUpdated` |  |
| `records_split_records` | string | yes | `records.splitRecords` |  |
| `records_division_records` | string | yes | `records.divisionRecords` |  |
| `records_overall_records` | string | yes | `records.overallRecords` |  |
| `records_league_records` | string | yes | `records.leagueRecords` |  |
| `records_expected_records` | string | yes | `records.expectedRecords` |  |
| `runs_allowed` | int32 | yes | `runsAllowed` |  |
| `runs_scored` | int32 | yes | `runsScored` |  |
| `division_champ` | bool | yes | `divisionChamp` |  |
| `division_leader` | bool | yes | `divisionLeader` |  |
| `wild_card_leader` | bool | yes | `wildCardLeader` |  |
| `has_wildcard` | bool | yes | `hasWildcard` |  |
| `clinched` | bool | yes | — |  |
| `elimination_number` | string | yes | `eliminationNumber` |  |
| `elimination_number_sport` | string | yes | `eliminationNumberSport` |  |
| `elimination_number_league` | string | yes | `eliminationNumberLeague` |  |
| `elimination_number_division` | string | yes | `eliminationNumberDivision` |  |
| `elimination_number_conference` | string | yes | `eliminationNumberConference` |  |
| `wild_card_elimination_number` | string | yes | `wildCardEliminationNumber` |  |
| `wins` | int32 | yes | — |  |
| `losses` | int32 | yes | — |  |
| `run_differential` | int32 | yes | `runDifferential` |  |
| `winning_percentage` | string | yes | `winningPercentage` |  |
| `records_sport_id` | int32 | yes | `records.sport.id` |  |
| `records_sport_link` | string | yes | `records.sport.link` |  |
| `records_round_robin_status` | string | yes | `records.roundRobin.status` |  |
| `magic_number` | string | yes | `magicNumber` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.standings_wild_card_with_leaders -->

<!-- BEGIN GENERATED:mlb_api.stats_career_advanced_catching -->
### Dataset: stats_career_advanced_catching

League-wide catching stats, type careerAdvanced (player pool ALL).

- **View:** `mlb_stats_career_advanced_catching`
- **Processed path:** `processed/mlb_api/stats_career_advanced_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_advanced_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_career_advanced_fielding -->
### Dataset: stats_career_advanced_fielding

League-wide fielding stats, type careerAdvanced (player pool ALL).

- **View:** `mlb_stats_career_advanced_fielding`
- **Processed path:** `processed/mlb_api/stats_career_advanced_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_advanced_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_career_advanced_hitting -->
### Dataset: stats_career_advanced_hitting

League-wide hitting stats, type careerAdvanced (player pool ALL).

- **View:** `mlb_stats_career_advanced_hitting`
- **Processed path:** `processed/mlb_api/stats_career_advanced_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_extra_base_hits` | int32 | yes | `stat.extraBaseHits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `team_name` | string | yes | `team.name` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_reached_on_error` | int32 | yes | `stat.reachedOnError` |  |
| `stat_walk_offs` | int32 | yes | `stat.walkOffs` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_advanced_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_career_advanced_pitching -->
### Dataset: stats_career_advanced_pitching

League-wide pitching stats, type careerAdvanced (player pool ALL).

- **View:** `mlb_stats_career_advanced_pitching`
- **Processed path:** `processed/mlb_api/stats_career_advanced_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_winning_percentage` | string | yes | `stat.winningPercentage` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_strikeouts_per9` | string | yes | `stat.strikeoutsPer9` |  |
| `stat_base_on_balls_per9` | string | yes | `stat.baseOnBallsPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_hits_per9` | string | yes | `stat.hitsPer9` |  |
| `stat_strikesouts_to_walks` | string | yes | `stat.strikesoutsToWalks` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_bequeathed_runners` | int32 | yes | `stat.bequeathedRunners` |  |
| `stat_bequeathed_runners_scored` | int32 | yes | `stat.bequeathedRunnersScored` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_quality_starts` | int32 | yes | `stat.qualityStarts` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_strikeouts_minus_walks_percentage` | string | yes | `stat.strikeoutsMinusWalksPercentage` |  |
| `stat_gidp_percentage` | string | yes | `stat.gidpPercentage` |  |
| `stat_batters_faced_per_game` | string | yes | `stat.battersFacedPerGame` |  |
| `stat_innings_pitched_per_game` | string | yes | `stat.inningsPitchedPerGame` |  |
| `stat_bunts_failed` | int32 | yes | `stat.buntsFailed` |  |
| `stat_bunts_missed_tipped` | int32 | yes | `stat.buntsMissedTipped` |  |
| `stat_whiff_percentage` | string | yes | `stat.whiffPercentage` |  |
| `stat_fly_ball_percentage` | string | yes | `stat.flyBallPercentage` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_run_support` | int32 | yes | `stat.runSupport` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_advanced_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_career_catching -->
### Dataset: stats_career_catching

League-wide catching stats, type career (player pool ALL).

- **View:** `mlb_stats_career_catching`
- **Processed path:** `processed/mlb_api/stats_career_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_career_fielding -->
### Dataset: stats_career_fielding

League-wide fielding stats, type career (player pool ALL).

- **View:** `mlb_stats_career_fielding`
- **Processed path:** `processed/mlb_api/stats_career_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_career_hitting -->
### Dataset: stats_career_hitting

League-wide hitting stats, type career (player pool ALL).

- **View:** `mlb_stats_career_hitting`
- **Processed path:** `processed/mlb_api/stats_career_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_career_pitching -->
### Dataset: stats_career_pitching

League-wide pitching stats, type career (player pool ALL).

- **View:** `mlb_stats_career_pitching`
- **Processed path:** `processed/mlb_api/stats_career_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_career_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_expected_statistics_hitting -->
### Dataset: stats_expected_statistics_hitting

League-wide hitting stats, type expectedStatistics (player pool ALL).

- **View:** `mlb_stats_expected_statistics_hitting`
- **Processed path:** `processed/mlb_api/stats_expected_statistics_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_woba` | string | yes | `stat.woba` |  |
| `stat_woba_con` | string | yes | `stat.wobaCon` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_expected_statistics_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_expected_statistics_pitching -->
### Dataset: stats_expected_statistics_pitching

League-wide pitching stats, type expectedStatistics (player pool ALL).

- **View:** `mlb_stats_expected_statistics_pitching`
- **Processed path:** `processed/mlb_api/stats_expected_statistics_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `sport_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_woba` | string | yes | `stat.woba` |  |
| `stat_woba_con` | string | yes | `stat.wobaCon` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_expected_statistics_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_last_x_games_fielding -->
### Dataset: stats_last_x_games_fielding

League-wide fielding stats, type lastXGames (player pool ALL).

- **View:** `mlb_stats_last_x_games_fielding`
- **Processed path:** `processed/mlb_api/stats_last_x_games_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_position_code` | string | yes | `stat.position.code` |  |
| `stat_position_name` | string | yes | `stat.position.name` |  |
| `stat_position_type` | string | yes | `stat.position.type` |  |
| `stat_position_abbreviation` | string | yes | `stat.position.abbreviation` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_catcher_era` | string | yes | `stat.catcherERA` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_last_x_games_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_last_x_games_hitting -->
### Dataset: stats_last_x_games_hitting

League-wide hitting stats, type lastXGames (player pool ALL).

- **View:** `mlb_stats_last_x_games_hitting`
- **Processed path:** `processed/mlb_api/stats_last_x_games_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_ground_into_triple_play` | int32 | yes | `stat.groundIntoTriplePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_last_x_games_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_last_x_games_pitching -->
### Dataset: stats_last_x_games_pitching

League-wide pitching stats, type lastXGames (player pool ALL).

- **View:** `mlb_stats_last_x_games_pitching`
- **Processed path:** `processed/mlb_api/stats_last_x_games_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_last_x_games_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_leaders -->
### Dataset: stats_leaders

League leaders for every category of a season (ties repeat a rank, so the key is not unique).

- **View:** `mlb_stats_leaders`
- **Processed path:** `processed/mlb_api/stats_leaders/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `league_leaders_leader_category`, `league_leaders_stat_group`, `rank`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `league_leaders_leader_category` | string | yes | `leagueLeaders.leaderCategory` |  |
| `league_leaders_season` | string | yes | `leagueLeaders.season` |  |
| `league_leaders_game_type_id` | string | yes | `leagueLeaders.gameType.id` |  |
| `league_leaders_game_type_description` | string | yes | `leagueLeaders.gameType.description` |  |
| `league_leaders_stat_group` | string | yes | `leagueLeaders.statGroup` |  |
| `league_leaders_total_splits` | int32 | yes | `leagueLeaders.totalSplits` |  |
| `rank` | int32 | yes | — |  |
| `value` | string | yes | — |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `person_first_name` | string | yes | `person.firstName` |  |
| `person_last_name` | string | yes | `person.lastName` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `season` | string | yes | — |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_leaders -->

<!-- BEGIN GENERATED:mlb_api.stats_outs_above_average_catching -->
### Dataset: stats_outs_above_average_catching

League-wide catching stats, type outsAboveAverage (player pool ALL).

- **View:** `mlb_stats_outs_above_average_catching`
- **Processed path:** `processed/mlb_api/stats_outs_above_average_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `stat_attempts` | int32 | yes | `stat.attempts` |  |
| `stat_total_outs_above_average` | int32 | yes | `stat.totalOutsAboveAverage` |  |
| `stat_total_outs_above_average_unrounded` | double | yes | `stat.totalOutsAboveAverageUnrounded` |  |
| `stat_total_outs_above_average_back` | int32 | yes | `stat.totalOutsAboveAverageBack` |  |
| `stat_total_outs_above_average_back_unrounded` | double | yes | `stat.totalOutsAboveAverageBackUnrounded` |  |
| `stat_outs_above_average_back_straight` | int32 | yes | `stat.outsAboveAverageBackStraight` |  |
| `stat_outs_above_average_back_straight_unrounded` | double | yes | `stat.outsAboveAverageBackStraightUnrounded` |  |
| `stat_outs_above_average_back_left` | int32 | yes | `stat.outsAboveAverageBackLeft` |  |
| `stat_outs_above_average_back_left_unrounded` | double | yes | `stat.outsAboveAverageBackLeftUnrounded` |  |
| `stat_outs_above_average_back_right` | int32 | yes | `stat.outsAboveAverageBackRight` |  |
| `stat_outs_above_average_back_right_unrounded` | double | yes | `stat.outsAboveAverageBackRightUnrounded` |  |
| `stat_total_outs_above_average_in` | int32 | yes | `stat.totalOutsAboveAverageIn` |  |
| `stat_total_outs_above_average_in_unrounded` | double | yes | `stat.totalOutsAboveAverageInUnrounded` |  |
| `stat_outs_above_average_in_straight` | int32 | yes | `stat.outsAboveAverageInStraight` |  |
| `stat_outs_above_average_in_straight_unrounded` | double | yes | `stat.outsAboveAverageInStraightUnrounded` |  |
| `stat_outs_above_average_in_left` | int32 | yes | `stat.outsAboveAverageInLeft` |  |
| `stat_outs_above_average_in_left_unrounded` | double | yes | `stat.outsAboveAverageInLeftUnrounded` |  |
| `stat_outs_above_average_in_right` | int32 | yes | `stat.outsAboveAverageInRight` |  |
| `stat_outs_above_average_in_right_unrounded` | double | yes | `stat.outsAboveAverageInRightUnrounded` |  |
| `stat_fielding_runs_prevented` | int32 | yes | `stat.fieldingRunsPrevented` |  |
| `stat_fielding_runs_prevented_unrounded` | double | yes | `stat.fieldingRunsPreventedUnrounded` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_outs_above_average_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_outs_above_average_fielding -->
### Dataset: stats_outs_above_average_fielding

League-wide fielding stats, type outsAboveAverage (player pool ALL).

- **View:** `mlb_stats_outs_above_average_fielding`
- **Processed path:** `processed/mlb_api/stats_outs_above_average_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `stat_attempts` | int32 | yes | `stat.attempts` |  |
| `stat_total_outs_above_average` | int32 | yes | `stat.totalOutsAboveAverage` |  |
| `stat_total_outs_above_average_unrounded` | double | yes | `stat.totalOutsAboveAverageUnrounded` |  |
| `stat_total_outs_above_average_back` | int32 | yes | `stat.totalOutsAboveAverageBack` |  |
| `stat_total_outs_above_average_back_unrounded` | double | yes | `stat.totalOutsAboveAverageBackUnrounded` |  |
| `stat_outs_above_average_back_straight` | int32 | yes | `stat.outsAboveAverageBackStraight` |  |
| `stat_outs_above_average_back_straight_unrounded` | double | yes | `stat.outsAboveAverageBackStraightUnrounded` |  |
| `stat_outs_above_average_back_left` | int32 | yes | `stat.outsAboveAverageBackLeft` |  |
| `stat_outs_above_average_back_left_unrounded` | double | yes | `stat.outsAboveAverageBackLeftUnrounded` |  |
| `stat_outs_above_average_back_right` | int32 | yes | `stat.outsAboveAverageBackRight` |  |
| `stat_outs_above_average_back_right_unrounded` | double | yes | `stat.outsAboveAverageBackRightUnrounded` |  |
| `stat_total_outs_above_average_in` | int32 | yes | `stat.totalOutsAboveAverageIn` |  |
| `stat_total_outs_above_average_in_unrounded` | double | yes | `stat.totalOutsAboveAverageInUnrounded` |  |
| `stat_outs_above_average_in_straight` | int32 | yes | `stat.outsAboveAverageInStraight` |  |
| `stat_outs_above_average_in_straight_unrounded` | double | yes | `stat.outsAboveAverageInStraightUnrounded` |  |
| `stat_outs_above_average_in_left` | int32 | yes | `stat.outsAboveAverageInLeft` |  |
| `stat_outs_above_average_in_left_unrounded` | double | yes | `stat.outsAboveAverageInLeftUnrounded` |  |
| `stat_outs_above_average_in_right` | int32 | yes | `stat.outsAboveAverageInRight` |  |
| `stat_outs_above_average_in_right_unrounded` | double | yes | `stat.outsAboveAverageInRightUnrounded` |  |
| `stat_fielding_runs_prevented` | int32 | yes | `stat.fieldingRunsPrevented` |  |
| `stat_fielding_runs_prevented_unrounded` | double | yes | `stat.fieldingRunsPreventedUnrounded` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_outs_above_average_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_outs_above_average_hitting -->
### Dataset: stats_outs_above_average_hitting

League-wide hitting stats, type outsAboveAverage (player pool ALL).

- **View:** `mlb_stats_outs_above_average_hitting`
- **Processed path:** `processed/mlb_api/stats_outs_above_average_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `stat_attempts` | int32 | yes | `stat.attempts` |  |
| `stat_total_outs_above_average` | int32 | yes | `stat.totalOutsAboveAverage` |  |
| `stat_total_outs_above_average_unrounded` | double | yes | `stat.totalOutsAboveAverageUnrounded` |  |
| `stat_total_outs_above_average_back` | int32 | yes | `stat.totalOutsAboveAverageBack` |  |
| `stat_total_outs_above_average_back_unrounded` | double | yes | `stat.totalOutsAboveAverageBackUnrounded` |  |
| `stat_outs_above_average_back_straight` | int32 | yes | `stat.outsAboveAverageBackStraight` |  |
| `stat_outs_above_average_back_straight_unrounded` | double | yes | `stat.outsAboveAverageBackStraightUnrounded` |  |
| `stat_outs_above_average_back_left` | int32 | yes | `stat.outsAboveAverageBackLeft` |  |
| `stat_outs_above_average_back_left_unrounded` | double | yes | `stat.outsAboveAverageBackLeftUnrounded` |  |
| `stat_outs_above_average_back_right` | int32 | yes | `stat.outsAboveAverageBackRight` |  |
| `stat_outs_above_average_back_right_unrounded` | double | yes | `stat.outsAboveAverageBackRightUnrounded` |  |
| `stat_total_outs_above_average_in` | int32 | yes | `stat.totalOutsAboveAverageIn` |  |
| `stat_total_outs_above_average_in_unrounded` | double | yes | `stat.totalOutsAboveAverageInUnrounded` |  |
| `stat_outs_above_average_in_straight` | int32 | yes | `stat.outsAboveAverageInStraight` |  |
| `stat_outs_above_average_in_straight_unrounded` | double | yes | `stat.outsAboveAverageInStraightUnrounded` |  |
| `stat_outs_above_average_in_left` | int32 | yes | `stat.outsAboveAverageInLeft` |  |
| `stat_outs_above_average_in_left_unrounded` | double | yes | `stat.outsAboveAverageInLeftUnrounded` |  |
| `stat_outs_above_average_in_right` | int32 | yes | `stat.outsAboveAverageInRight` |  |
| `stat_outs_above_average_in_right_unrounded` | double | yes | `stat.outsAboveAverageInRightUnrounded` |  |
| `stat_fielding_runs_prevented` | int32 | yes | `stat.fieldingRunsPrevented` |  |
| `stat_fielding_runs_prevented_unrounded` | double | yes | `stat.fieldingRunsPreventedUnrounded` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_outs_above_average_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_outs_above_average_pitching -->
### Dataset: stats_outs_above_average_pitching

League-wide pitching stats, type outsAboveAverage (player pool ALL).

- **View:** `mlb_stats_outs_above_average_pitching`
- **Processed path:** `processed/mlb_api/stats_outs_above_average_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `stat_attempts` | int32 | yes | `stat.attempts` |  |
| `stat_total_outs_above_average` | int32 | yes | `stat.totalOutsAboveAverage` |  |
| `stat_total_outs_above_average_unrounded` | double | yes | `stat.totalOutsAboveAverageUnrounded` |  |
| `stat_total_outs_above_average_back` | int32 | yes | `stat.totalOutsAboveAverageBack` |  |
| `stat_total_outs_above_average_back_unrounded` | double | yes | `stat.totalOutsAboveAverageBackUnrounded` |  |
| `stat_outs_above_average_back_straight` | int32 | yes | `stat.outsAboveAverageBackStraight` |  |
| `stat_outs_above_average_back_straight_unrounded` | double | yes | `stat.outsAboveAverageBackStraightUnrounded` |  |
| `stat_outs_above_average_back_left` | int32 | yes | `stat.outsAboveAverageBackLeft` |  |
| `stat_outs_above_average_back_left_unrounded` | double | yes | `stat.outsAboveAverageBackLeftUnrounded` |  |
| `stat_outs_above_average_back_right` | int32 | yes | `stat.outsAboveAverageBackRight` |  |
| `stat_outs_above_average_back_right_unrounded` | double | yes | `stat.outsAboveAverageBackRightUnrounded` |  |
| `stat_total_outs_above_average_in` | int32 | yes | `stat.totalOutsAboveAverageIn` |  |
| `stat_total_outs_above_average_in_unrounded` | double | yes | `stat.totalOutsAboveAverageInUnrounded` |  |
| `stat_outs_above_average_in_straight` | int32 | yes | `stat.outsAboveAverageInStraight` |  |
| `stat_outs_above_average_in_straight_unrounded` | double | yes | `stat.outsAboveAverageInStraightUnrounded` |  |
| `stat_outs_above_average_in_left` | int32 | yes | `stat.outsAboveAverageInLeft` |  |
| `stat_outs_above_average_in_left_unrounded` | double | yes | `stat.outsAboveAverageInLeftUnrounded` |  |
| `stat_outs_above_average_in_right` | int32 | yes | `stat.outsAboveAverageInRight` |  |
| `stat_outs_above_average_in_right_unrounded` | double | yes | `stat.outsAboveAverageInRightUnrounded` |  |
| `stat_fielding_runs_prevented` | int32 | yes | `stat.fieldingRunsPrevented` |  |
| `stat_fielding_runs_prevented_unrounded` | double | yes | `stat.fieldingRunsPreventedUnrounded` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_outs_above_average_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_outs_above_average_running -->
### Dataset: stats_outs_above_average_running

League-wide running stats, type outsAboveAverage (player pool ALL).

- **View:** `mlb_stats_outs_above_average_running`
- **Processed path:** `processed/mlb_api/stats_outs_above_average_running/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `stat_attempts` | int32 | yes | `stat.attempts` |  |
| `stat_total_outs_above_average` | int32 | yes | `stat.totalOutsAboveAverage` |  |
| `stat_total_outs_above_average_unrounded` | double | yes | `stat.totalOutsAboveAverageUnrounded` |  |
| `stat_total_outs_above_average_back` | int32 | yes | `stat.totalOutsAboveAverageBack` |  |
| `stat_total_outs_above_average_back_unrounded` | double | yes | `stat.totalOutsAboveAverageBackUnrounded` |  |
| `stat_outs_above_average_back_straight` | int32 | yes | `stat.outsAboveAverageBackStraight` |  |
| `stat_outs_above_average_back_straight_unrounded` | double | yes | `stat.outsAboveAverageBackStraightUnrounded` |  |
| `stat_outs_above_average_back_left` | int32 | yes | `stat.outsAboveAverageBackLeft` |  |
| `stat_outs_above_average_back_left_unrounded` | double | yes | `stat.outsAboveAverageBackLeftUnrounded` |  |
| `stat_outs_above_average_back_right` | int32 | yes | `stat.outsAboveAverageBackRight` |  |
| `stat_outs_above_average_back_right_unrounded` | double | yes | `stat.outsAboveAverageBackRightUnrounded` |  |
| `stat_total_outs_above_average_in` | int32 | yes | `stat.totalOutsAboveAverageIn` |  |
| `stat_total_outs_above_average_in_unrounded` | double | yes | `stat.totalOutsAboveAverageInUnrounded` |  |
| `stat_outs_above_average_in_straight` | int32 | yes | `stat.outsAboveAverageInStraight` |  |
| `stat_outs_above_average_in_straight_unrounded` | double | yes | `stat.outsAboveAverageInStraightUnrounded` |  |
| `stat_outs_above_average_in_left` | int32 | yes | `stat.outsAboveAverageInLeft` |  |
| `stat_outs_above_average_in_left_unrounded` | double | yes | `stat.outsAboveAverageInLeftUnrounded` |  |
| `stat_outs_above_average_in_right` | int32 | yes | `stat.outsAboveAverageInRight` |  |
| `stat_outs_above_average_in_right_unrounded` | double | yes | `stat.outsAboveAverageInRightUnrounded` |  |
| `stat_fielding_runs_prevented` | int32 | yes | `stat.fieldingRunsPrevented` |  |
| `stat_fielding_runs_prevented_unrounded` | double | yes | `stat.fieldingRunsPreventedUnrounded` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_outs_above_average_running -->

<!-- BEGIN GENERATED:mlb_api.stats_projected_hitting -->
### Dataset: stats_projected_hitting

League-wide hitting stats, type projected (player pool ALL).

- **View:** `mlb_stats_projected_hitting`
- **Processed path:** `processed/mlb_api/stats_projected_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `stat_woba` | double | yes | `stat.woba` |  |
| `stat_w_raa` | double | yes | `stat.wRaa` |  |
| `stat_w_rc` | double | yes | `stat.wRc` |  |
| `stat_w_rc_plus` | double | yes | `stat.wRcPlus` |  |
| `stat_rar` | double | yes | `stat.rar` |  |
| `stat_war` | double | yes | `stat.war` |  |
| `stat_batting` | double | yes | `stat.batting` |  |
| `stat_fielding` | double | yes | `stat.fielding` |  |
| `stat_base_running` | double | yes | `stat.baseRunning` |  |
| `stat_positional` | double | yes | `stat.positional` |  |
| `stat_replacement` | double | yes | `stat.replacement` |  |
| `stat_spd` | double | yes | `stat.spd` |  |
| `stat_ubr` | double | yes | `stat.ubr` |  |
| `stat_w_sb` | double | yes | `stat.wSb` |  |
| `stat_strikeout_percent` | double | yes | `stat.strikeoutPercent` |  |
| `stat_walk_percent` | double | yes | `stat.walkPercent` |  |
| `stat_ratio_bbso` | double | yes | `stat.ratioBBSO` |  |
| `stat_iso` | double | yes | `stat.iso` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_projected_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_projected_pitching -->
### Dataset: stats_projected_pitching

League-wide pitching stats, type projected (player pool ALL).

- **View:** `mlb_stats_projected_pitching`
- **Processed path:** `processed/mlb_api/stats_projected_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | double | yes | `stat.avg` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_fip` | double | yes | `stat.fip` |  |
| `stat_ra9_war` | double | yes | `stat.ra9War` |  |
| `stat_rar` | double | yes | `stat.rar` |  |
| `stat_war` | double | yes | `stat.war` |  |
| `stat_lob_wins` | double | yes | `stat.lobWins` |  |
| `stat_bip_wins` | double | yes | `stat.bipWins` |  |
| `stat_fdp_wins` | double | yes | `stat.fdpWins` |  |
| `stat_strikeout_percent` | double | yes | `stat.strikeoutPercent` |  |
| `stat_walk_percent` | double | yes | `stat.walkPercent` |  |
| `stat_babip` | double | yes | `stat.babip` |  |
| `stat_lob_percent` | double | yes | `stat.lobPercent` |  |
| `stat_quality_starts` | int32 | yes | `stat.qualityStarts` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_projected_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_sabermetrics_fielding -->
### Dataset: stats_sabermetrics_fielding

League-wide fielding stats, type sabermetrics (player pool ALL).

- **View:** `mlb_stats_sabermetrics_fielding`
- **Processed path:** `processed/mlb_api/stats_sabermetrics_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_position_code` | string | yes | `stat.position.code` |  |
| `stat_position_name` | string | yes | `stat.position.name` |  |
| `stat_position_type` | string | yes | `stat.position.type` |  |
| `stat_position_abbreviation` | string | yes | `stat.position.abbreviation` |  |
| `stat_uzr` | double | yes | `stat.uzr` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_sabermetrics_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_sabermetrics_hitting -->
### Dataset: stats_sabermetrics_hitting

League-wide hitting stats, type sabermetrics (player pool ALL).

- **View:** `mlb_stats_sabermetrics_hitting`
- **Processed path:** `processed/mlb_api/stats_sabermetrics_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_woba` | double | yes | `stat.woba` |  |
| `stat_w_raa` | double | yes | `stat.wRaa` |  |
| `stat_w_rc` | double | yes | `stat.wRc` |  |
| `stat_w_rc_plus` | double | yes | `stat.wRcPlus` |  |
| `stat_rar` | double | yes | `stat.rar` |  |
| `stat_war` | double | yes | `stat.war` |  |
| `stat_batting` | double | yes | `stat.batting` |  |
| `stat_fielding` | double | yes | `stat.fielding` |  |
| `stat_base_running` | double | yes | `stat.baseRunning` |  |
| `stat_positional` | double | yes | `stat.positional` |  |
| `stat_w_league` | double | yes | `stat.wLeague` |  |
| `stat_replacement` | double | yes | `stat.replacement` |  |
| `stat_spd` | double | yes | `stat.spd` |  |
| `stat_ubr` | double | yes | `stat.ubr` |  |
| `stat_w_gdp` | double | yes | `stat.wGdp` |  |
| `stat_w_sb` | double | yes | `stat.wSb` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_sabermetrics_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_sabermetrics_pitching -->
### Dataset: stats_sabermetrics_pitching

League-wide pitching stats, type sabermetrics (player pool ALL).

- **View:** `mlb_stats_sabermetrics_pitching`
- **Processed path:** `processed/mlb_api/stats_sabermetrics_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_fip` | double | yes | `stat.fip` |  |
| `stat_xfip` | double | yes | `stat.xfip` |  |
| `stat_fip_minus` | double | yes | `stat.fipMinus` |  |
| `stat_ra9_war` | double | yes | `stat.ra9War` |  |
| `stat_rar` | double | yes | `stat.rar` |  |
| `stat_war` | double | yes | `stat.war` |  |
| `stat_sd` | double | yes | `stat.sd` |  |
| `stat_md` | double | yes | `stat.md` |  |
| `stat_pli` | double | yes | `stat.pli` |  |
| `stat_inli` | double | yes | `stat.inli` |  |
| `stat_gmli` | double | yes | `stat.gmli` |  |
| `stat_exli` | double | yes | `stat.exli` |  |
| `stat_era_minus` | double | yes | `stat.eraMinus` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_sabermetrics_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_season_advanced_catching -->
### Dataset: stats_season_advanced_catching

League-wide catching stats, type seasonAdvanced (player pool ALL).

- **View:** `mlb_stats_season_advanced_catching`
- **Processed path:** `processed/mlb_api/stats_season_advanced_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_pickoff_attempts` | int32 | yes | `stat.pickoffAttempts` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_advanced_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_season_advanced_fielding -->
### Dataset: stats_season_advanced_fielding

League-wide fielding stats, type seasonAdvanced (player pool ALL).

- **View:** `mlb_stats_season_advanced_fielding`
- **Processed path:** `processed/mlb_api/stats_season_advanced_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_catcher_era` | string | yes | `stat.catcherERA` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_advanced_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_season_advanced_hitting -->
### Dataset: stats_season_advanced_hitting

League-wide hitting stats, type seasonAdvanced (player pool ALL).

- **View:** `mlb_stats_season_advanced_hitting`
- **Processed path:** `processed/mlb_api/stats_season_advanced_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_extra_base_hits` | int32 | yes | `stat.extraBaseHits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_reached_on_error` | int32 | yes | `stat.reachedOnError` |  |
| `stat_walk_offs` | int32 | yes | `stat.walkOffs` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_advanced_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_season_advanced_pitching -->
### Dataset: stats_season_advanced_pitching

League-wide pitching stats, type seasonAdvanced (player pool ALL).

- **View:** `mlb_stats_season_advanced_pitching`
- **Processed path:** `processed/mlb_api/stats_season_advanced_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_winning_percentage` | string | yes | `stat.winningPercentage` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_strikeouts_per9` | string | yes | `stat.strikeoutsPer9` |  |
| `stat_base_on_balls_per9` | string | yes | `stat.baseOnBallsPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_hits_per9` | string | yes | `stat.hitsPer9` |  |
| `stat_strikesouts_to_walks` | string | yes | `stat.strikesoutsToWalks` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_bequeathed_runners` | int32 | yes | `stat.bequeathedRunners` |  |
| `stat_bequeathed_runners_scored` | int32 | yes | `stat.bequeathedRunnersScored` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_quality_starts` | int32 | yes | `stat.qualityStarts` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_strikeouts_minus_walks_percentage` | string | yes | `stat.strikeoutsMinusWalksPercentage` |  |
| `stat_gidp_percentage` | string | yes | `stat.gidpPercentage` |  |
| `stat_batters_faced_per_game` | string | yes | `stat.battersFacedPerGame` |  |
| `stat_innings_pitched_per_game` | string | yes | `stat.inningsPitchedPerGame` |  |
| `stat_bunts_failed` | int32 | yes | `stat.buntsFailed` |  |
| `stat_bunts_missed_tipped` | int32 | yes | `stat.buntsMissedTipped` |  |
| `stat_whiff_percentage` | string | yes | `stat.whiffPercentage` |  |
| `stat_fly_ball_percentage` | string | yes | `stat.flyBallPercentage` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_run_support` | int32 | yes | `stat.runSupport` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_advanced_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_season_catching -->
### Dataset: stats_season_catching

League-wide catching stats, type season (player pool ALL).

- **View:** `mlb_stats_season_catching`
- **Processed path:** `processed/mlb_api/stats_season_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_pickoff_attempts` | int32 | yes | `stat.pickoffAttempts` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_season_fielding -->
### Dataset: stats_season_fielding

League-wide fielding stats, type season (player pool ALL).

- **View:** `mlb_stats_season_fielding`
- **Processed path:** `processed/mlb_api/stats_season_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_catcher_era` | string | yes | `stat.catcherERA` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_season_hitting -->
### Dataset: stats_season_hitting

League-wide hitting stats, type season (player pool ALL).

- **View:** `mlb_stats_season_hitting`
- **Processed path:** `processed/mlb_api/stats_season_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_season_pitching -->
### Dataset: stats_season_pitching

League-wide pitching stats, type season (player pool ALL).

- **View:** `mlb_stats_season_pitching`
- **Processed path:** `processed/mlb_api/stats_season_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stats_player_pool` | string | yes | `stats.playerPool` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_season_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_advanced_catching -->
### Dataset: stats_stats_single_season_advanced_catching

League-wide catching stats, type statsSingleSeasonAdvanced (player pool ALL).

- **View:** `mlb_stats_stats_single_season_advanced_catching`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_advanced_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_advanced_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_advanced_fielding -->
### Dataset: stats_stats_single_season_advanced_fielding

League-wide fielding stats, type statsSingleSeasonAdvanced (player pool ALL).

- **View:** `mlb_stats_stats_single_season_advanced_fielding`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_advanced_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_advanced_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_advanced_hitting -->
### Dataset: stats_stats_single_season_advanced_hitting

League-wide hitting stats, type statsSingleSeasonAdvanced (player pool ALL).

- **View:** `mlb_stats_stats_single_season_advanced_hitting`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_advanced_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_extra_base_hits` | int32 | yes | `stat.extraBaseHits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_reached_on_error` | int32 | yes | `stat.reachedOnError` |  |
| `stat_walk_offs` | int32 | yes | `stat.walkOffs` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_advanced_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_advanced_pitching -->
### Dataset: stats_stats_single_season_advanced_pitching

League-wide pitching stats, type statsSingleSeasonAdvanced (player pool ALL).

- **View:** `mlb_stats_stats_single_season_advanced_pitching`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_advanced_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_winning_percentage` | string | yes | `stat.winningPercentage` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_strikeouts_per9` | string | yes | `stat.strikeoutsPer9` |  |
| `stat_base_on_balls_per9` | string | yes | `stat.baseOnBallsPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_hits_per9` | string | yes | `stat.hitsPer9` |  |
| `stat_strikesouts_to_walks` | string | yes | `stat.strikesoutsToWalks` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_strikeouts_minus_walks_percentage` | string | yes | `stat.strikeoutsMinusWalksPercentage` |  |
| `stat_batters_faced_per_game` | string | yes | `stat.battersFacedPerGame` |  |
| `stat_innings_pitched_per_game` | string | yes | `stat.inningsPitchedPerGame` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_bequeathed_runners` | int32 | yes | `stat.bequeathedRunners` |  |
| `stat_bequeathed_runners_scored` | int32 | yes | `stat.bequeathedRunnersScored` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_quality_starts` | int32 | yes | `stat.qualityStarts` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_gidp_percentage` | string | yes | `stat.gidpPercentage` |  |
| `stat_bunts_failed` | int32 | yes | `stat.buntsFailed` |  |
| `stat_bunts_missed_tipped` | int32 | yes | `stat.buntsMissedTipped` |  |
| `stat_whiff_percentage` | string | yes | `stat.whiffPercentage` |  |
| `stat_fly_ball_percentage` | string | yes | `stat.flyBallPercentage` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_run_support` | int32 | yes | `stat.runSupport` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_advanced_pitching -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_catching -->
### Dataset: stats_stats_single_season_catching

League-wide catching stats, type statsSingleSeason (player pool ALL).

- **View:** `mlb_stats_stats_single_season_catching`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_catching -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_fielding -->
### Dataset: stats_stats_single_season_fielding

League-wide fielding stats, type statsSingleSeason (player pool ALL).

- **View:** `mlb_stats_stats_single_season_fielding`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`, `position_abbreviation`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_fielding -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_hitting -->
### Dataset: stats_stats_single_season_hitting

League-wide hitting stats, type statsSingleSeason (player pool ALL).

- **View:** `mlb_stats_stats_single_season_hitting`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_hitting -->

<!-- BEGIN GENERATED:mlb_api.stats_stats_single_season_pitching -->
### Dataset: stats_stats_single_season_pitching

League-wide pitching stats, type statsSingleSeason (player pool ALL).

- **View:** `mlb_stats_stats_single_season_pitching`
- **Processed path:** `processed/mlb_api/stats_stats_single_season_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_id`, `team_id`, `sport_id`, `league_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_age` | int32 | yes | `stat.age` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.stats_stats_single_season_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_affiliates -->
### Dataset: team_affiliates

Minor-league affiliates of every MLB club.

- **View:** `mlb_team_affiliates`
- **Processed path:** `processed/mlb_api/team_affiliates/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`, `parent_org_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `all_star_status` | string | yes | `allStarStatus` |  |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `link` | string | yes | — |  |
| `season` | int32 | yes | — |  |
| `venue_id` | int32 | yes | `venue.id` |  |
| `venue_name` | string | yes | `venue.name` |  |
| `venue_link` | string | yes | `venue.link` |  |
| `team_code` | string | yes | `teamCode` |  |
| `file_code` | string | yes | `fileCode` |  |
| `abbreviation` | string | yes | — |  |
| `team_name` | string | yes | `teamName` |  |
| `location_name` | string | yes | `locationName` |  |
| `first_year_of_play` | string | yes | `firstYearOfPlay` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `division_id` | int32 | yes | `division.id` |  |
| `division_name` | string | yes | `division.name` |  |
| `division_link` | string | yes | `division.link` |  |
| `sport_id` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `short_name` | string | yes | `shortName` |  |
| `parent_org_name` | string | yes | `parentOrgName` |  |
| `parent_org_id` | int32 | yes | `parentOrgId` |  |
| `franchise_name` | string | yes | `franchiseName` |  |
| `club_name` | string | yes | `clubName` |  |
| `active` | bool | yes | — |  |
| `spring_league_id` | int32 | yes | `springLeague.id` |  |
| `spring_league_name` | string | yes | `springLeague.name` |  |
| `spring_league_link` | string | yes | `springLeague.link` |  |
| `spring_league_abbreviation` | string | yes | `springLeague.abbreviation` |  |
| `spring_venue_id` | int32 | yes | `springVenue.id` |  |
| `spring_venue_link` | string | yes | `springVenue.link` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_affiliates -->

<!-- BEGIN GENERATED:mlb_api.team_alumni -->
### Dataset: team_alumni

Club alumni (hitting) of a season.

- **View:** `mlb_team_alumni`
- **Processed path:** `processed/mlb_api/team_alumni/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `id` | int32 | yes | — |  |
| `full_name` | string | yes | `fullName` |  |
| `link` | string | yes | — |  |
| `first_name` | string | yes | `firstName` |  |
| `last_name` | string | yes | `lastName` |  |
| `primary_number` | string | yes | `primaryNumber` |  |
| `birth_date` | date32[day] | yes | `birthDate` |  |
| `current_age` | int32 | yes | `currentAge` |  |
| `birth_city` | string | yes | `birthCity` |  |
| `birth_country` | string | yes | `birthCountry` |  |
| `height` | string | yes | — |  |
| `weight` | int32 | yes | — |  |
| `active` | bool | yes | — |  |
| `primary_position_code` | string | yes | `primaryPosition.code` |  |
| `primary_position_name` | string | yes | `primaryPosition.name` |  |
| `primary_position_type` | string | yes | `primaryPosition.type` |  |
| `primary_position_abbreviation` | string | yes | `primaryPosition.abbreviation` |  |
| `use_name` | string | yes | `useName` |  |
| `use_last_name` | string | yes | `useLastName` |  |
| `middle_name` | string | yes | `middleName` |  |
| `boxscore_name` | string | yes | `boxscoreName` |  |
| `nick_name` | string | yes | `nickName` |  |
| `gender` | string | yes | — |  |
| `is_player` | bool | yes | `isPlayer` |  |
| `is_verified` | bool | yes | `isVerified` |  |
| `pronunciation` | string | yes | — |  |
| `mlb_debut_date` | date32[day] | yes | `mlbDebutDate` |  |
| `bat_side_code` | string | yes | `batSide.code` |  |
| `bat_side_description` | string | yes | `batSide.description` |  |
| `pitch_hand_code` | string | yes | `pitchHand.code` |  |
| `pitch_hand_description` | string | yes | `pitchHand.description` |  |
| `name_first_last` | string | yes | `nameFirstLast` |  |
| `name_slug` | string | yes | `nameSlug` |  |
| `first_last_name` | string | yes | `firstLastName` |  |
| `last_first_name` | string | yes | `lastFirstName` |  |
| `last_init_name` | string | yes | `lastInitName` |  |
| `init_last_name` | string | yes | `initLastName` |  |
| `full_fml_name` | string | yes | `fullFMLName` |  |
| `full_lfm_name` | string | yes | `fullLFMName` |  |
| `strike_zone_top` | double | yes | `strikeZoneTop` |  |
| `strike_zone_bottom` | double | yes | `strikeZoneBottom` |  |
| `alumni_last_season` | string | yes | `alumniLastSeason` |  |
| `birth_state_province` | string | yes | `birthStateProvince` |  |
| `draft_year` | int32 | yes | `draftYear` |  |
| `last_played_date` | date32[day] | yes | `lastPlayedDate` |  |
| `name_matrilineal` | string | yes | `nameMatrilineal` |  |
| `name_title` | string | yes | `nameTitle` |  |
| `name_suffix` | string | yes | `nameSuffix` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_alumni -->

<!-- BEGIN GENERATED:mlb_api.team_coaches -->
### Dataset: team_coaches

Coaching staff of a club-season.

- **View:** `mlb_team_coaches`
- **Processed path:** `processed/mlb_api/team_coaches/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `job`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `job` | string | yes | — |  |
| `job_id` | string | yes | `jobId` |  |
| `title` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_coaches -->

<!-- BEGIN GENERATED:mlb_api.team_history -->
### Dataset: team_history

Franchise history (names/locations by season).

- **View:** `mlb_team_history`
- **Processed path:** `processed/mlb_api/team_history/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `all_star_status` | string | yes | `allStarStatus` |  |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `link` | string | yes | — |  |
| `season` | int32 | yes | — |  |
| `venue_id` | int32 | yes | `venue.id` |  |
| `venue_name` | string | yes | `venue.name` |  |
| `venue_link` | string | yes | `venue.link` |  |
| `spring_venue_id` | int32 | yes | `springVenue.id` |  |
| `spring_venue_link` | string | yes | `springVenue.link` |  |
| `team_code` | string | yes | `teamCode` |  |
| `file_code` | string | yes | `fileCode` |  |
| `abbreviation` | string | yes | — |  |
| `team_name` | string | yes | `teamName` |  |
| `location_name` | string | yes | `locationName` |  |
| `first_year_of_play` | string | yes | `firstYearOfPlay` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `sport_id` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `short_name` | string | yes | `shortName` |  |
| `franchise_name` | string | yes | `franchiseName` |  |
| `club_name` | string | yes | `clubName` |  |
| `active` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_history -->

<!-- BEGIN GENERATED:mlb_api.team_personnel -->
### Dataset: team_personnel

Non-playing personnel of a club-season.

- **View:** `mlb_team_personnel`
- **Processed path:** `processed/mlb_api/team_personnel/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `job`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `job` | string | yes | — |  |
| `job_id` | string | yes | `jobId` |  |
| `title` | string | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_personnel -->

<!-- BEGIN GENERATED:mlb_api.team_roster_40_man -->
### Dataset: team_roster_40_man

Team roster, type 40Man.

- **View:** `mlb_team_roster_40_man`
- **Processed path:** `processed/mlb_api/team_roster_40_man/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `position_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `status_code` | string | yes | `status.code` |  |
| `status_description` | string | yes | `status.description` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_roster_40_man -->

<!-- BEGIN GENERATED:mlb_api.team_roster_active -->
### Dataset: team_roster_active

Team roster, type active.

- **View:** `mlb_team_roster_active`
- **Processed path:** `processed/mlb_api/team_roster_active/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `position_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `status_code` | string | yes | `status.code` |  |
| `status_description` | string | yes | `status.description` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_roster_active -->

<!-- BEGIN GENERATED:mlb_api.team_roster_depth_chart -->
### Dataset: team_roster_depth_chart

Team roster, type depthChart.

- **View:** `mlb_team_roster_depth_chart`
- **Processed path:** `processed/mlb_api/team_roster_depth_chart/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `position_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `status_code` | string | yes | `status.code` |  |
| `status_description` | string | yes | `status.description` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_roster_depth_chart -->

<!-- BEGIN GENERATED:mlb_api.team_roster_full_roster -->
### Dataset: team_roster_full_roster

Team roster, type fullRoster.

- **View:** `mlb_team_roster_full_roster`
- **Processed path:** `processed/mlb_api/team_roster_full_roster/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `position_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `status_code` | string | yes | `status.code` |  |
| `status_description` | string | yes | `status.description` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_roster_full_roster -->

<!-- BEGIN GENERATED:mlb_api.team_roster_full_season -->
### Dataset: team_roster_full_season

Team roster, type fullSeason.

- **View:** `mlb_team_roster_full_season`
- **Processed path:** `processed/mlb_api/team_roster_full_season/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `position_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `status_code` | string | yes | `status.code` |  |
| `status_description` | string | yes | `status.description` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_roster_full_season -->

<!-- BEGIN GENERATED:mlb_api.team_roster_non_roster_invitees -->
### Dataset: team_roster_non_roster_invitees

Team roster, type nonRosterInvitees.

- **View:** `mlb_team_roster_non_roster_invitees`
- **Processed path:** `processed/mlb_api/team_roster_non_roster_invitees/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `person_id`, `position_code`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | int32 | yes | — |  |
| `person_id` | int32 | yes | `person.id` |  |
| `person_full_name` | string | yes | `person.fullName` |  |
| `person_link` | string | yes | `person.link` |  |
| `jersey_number` | string | yes | `jerseyNumber` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `status_code` | string | yes | `status.code` |  |
| `status_description` | string | yes | `status.description` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_roster_non_roster_invitees -->

<!-- BEGIN GENERATED:mlb_api.team_stats_at_game_start_catching -->
### Dataset: team_stats_at_game_start_catching

Team catching stats, type atGameStart.

- **View:** `mlb_team_stats_at_game_start_catching`
- **Processed path:** `processed/mlb_api/team_stats_at_game_start_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`, `opponent_id`, `game_game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_at_game_start_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_at_game_start_fielding -->
### Dataset: team_stats_at_game_start_fielding

Team fielding stats, type atGameStart.

- **View:** `mlb_team_stats_at_game_start_fielding`
- **Processed path:** `processed/mlb_api/team_stats_at_game_start_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`, `game_game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_at_game_start_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_at_game_start_hitting -->
### Dataset: team_stats_at_game_start_hitting

Team hitting stats, type atGameStart.

- **View:** `mlb_team_stats_at_game_start_hitting`
- **Processed path:** `processed/mlb_api/team_stats_at_game_start_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_at_game_start_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_at_game_start_pitching -->
### Dataset: team_stats_at_game_start_pitching

Team pitching stats, type atGameStart.

- **View:** `mlb_team_stats_at_game_start_pitching`
- **Processed path:** `processed/mlb_api/team_stats_at_game_start_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`, `game_game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_ties` | int32 | yes | `stat.ties` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_at_game_start_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_by_date_range_catching -->
### Dataset: team_stats_by_date_range_catching

Team catching stats, type byDateRange.

- **View:** `mlb_team_stats_by_date_range_catching`
- **Processed path:** `processed/mlb_api/team_stats_by_date_range_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_by_date_range_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_by_date_range_fielding -->
### Dataset: team_stats_by_date_range_fielding

Team fielding stats, type byDateRange.

- **View:** `mlb_team_stats_by_date_range_fielding`
- **Processed path:** `processed/mlb_api/team_stats_by_date_range_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_by_date_range_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_by_date_range_hitting -->
### Dataset: team_stats_by_date_range_hitting

Team hitting stats, type byDateRange.

- **View:** `mlb_team_stats_by_date_range_hitting`
- **Processed path:** `processed/mlb_api/team_stats_by_date_range_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_by_date_range_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_by_date_range_pitching -->
### Dataset: team_stats_by_date_range_pitching

Team pitching stats, type byDateRange.

- **View:** `mlb_team_stats_by_date_range_pitching`
- **Processed path:** `processed/mlb_api/team_stats_by_date_range_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_ties` | int32 | yes | `stat.ties` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_by_date_range_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_advanced_catching -->
### Dataset: team_stats_career_advanced_catching

Team catching stats, type careerAdvanced.

- **View:** `mlb_team_stats_career_advanced_catching`
- **Processed path:** `processed/mlb_api/team_stats_career_advanced_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_advanced_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_advanced_fielding -->
### Dataset: team_stats_career_advanced_fielding

Team fielding stats, type careerAdvanced.

- **View:** `mlb_team_stats_career_advanced_fielding`
- **Processed path:** `processed/mlb_api/team_stats_career_advanced_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_advanced_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_advanced_hitting -->
### Dataset: team_stats_career_advanced_hitting

Team hitting stats, type careerAdvanced.

- **View:** `mlb_team_stats_career_advanced_hitting`
- **Processed path:** `processed/mlb_api/team_stats_career_advanced_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_extra_base_hits` | int32 | yes | `stat.extraBaseHits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_reached_on_error` | int32 | yes | `stat.reachedOnError` |  |
| `stat_walk_offs` | int32 | yes | `stat.walkOffs` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_advanced_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_advanced_pitching -->
### Dataset: team_stats_career_advanced_pitching

Team pitching stats, type careerAdvanced.

- **View:** `mlb_team_stats_career_advanced_pitching`
- **Processed path:** `processed/mlb_api/team_stats_career_advanced_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_winning_percentage` | string | yes | `stat.winningPercentage` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_strikeouts_per9` | string | yes | `stat.strikeoutsPer9` |  |
| `stat_base_on_balls_per9` | string | yes | `stat.baseOnBallsPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_hits_per9` | string | yes | `stat.hitsPer9` |  |
| `stat_strikesouts_to_walks` | string | yes | `stat.strikesoutsToWalks` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_quality_starts` | int32 | yes | `stat.qualityStarts` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_strikeouts_minus_walks_percentage` | string | yes | `stat.strikeoutsMinusWalksPercentage` |  |
| `stat_gidp_percentage` | string | yes | `stat.gidpPercentage` |  |
| `stat_batters_faced_per_game` | string | yes | `stat.battersFacedPerGame` |  |
| `stat_innings_pitched_per_game` | string | yes | `stat.inningsPitchedPerGame` |  |
| `stat_bunts_failed` | int32 | yes | `stat.buntsFailed` |  |
| `stat_bunts_missed_tipped` | int32 | yes | `stat.buntsMissedTipped` |  |
| `stat_whiff_percentage` | string | yes | `stat.whiffPercentage` |  |
| `stat_fly_ball_percentage` | string | yes | `stat.flyBallPercentage` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_run_support` | int32 | yes | `stat.runSupport` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_advanced_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_catching -->
### Dataset: team_stats_career_catching

Team catching stats, type career.

- **View:** `mlb_team_stats_career_catching`
- **Processed path:** `processed/mlb_api/team_stats_career_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_fielding -->
### Dataset: team_stats_career_fielding

Team fielding stats, type career.

- **View:** `mlb_team_stats_career_fielding`
- **Processed path:** `processed/mlb_api/team_stats_career_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_hitting -->
### Dataset: team_stats_career_hitting

Team hitting stats, type career.

- **View:** `mlb_team_stats_career_hitting`
- **Processed path:** `processed/mlb_api/team_stats_career_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_pitching -->
### Dataset: team_stats_career_pitching

Team pitching stats, type career.

- **View:** `mlb_team_stats_career_pitching`
- **Processed path:** `processed/mlb_api/team_stats_career_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_playoffs_catching -->
### Dataset: team_stats_career_playoffs_catching

Team catching stats, type careerPlayoffs.

- **View:** `mlb_team_stats_career_playoffs_catching`
- **Processed path:** `processed/mlb_api/team_stats_career_playoffs_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_playoffs_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_playoffs_fielding -->
### Dataset: team_stats_career_playoffs_fielding

Team fielding stats, type careerPlayoffs.

- **View:** `mlb_team_stats_career_playoffs_fielding`
- **Processed path:** `processed/mlb_api/team_stats_career_playoffs_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_playoffs_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_playoffs_hitting -->
### Dataset: team_stats_career_playoffs_hitting

Team hitting stats, type careerPlayoffs.

- **View:** `mlb_team_stats_career_playoffs_hitting`
- **Processed path:** `processed/mlb_api/team_stats_career_playoffs_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_playoffs_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_playoffs_pitching -->
### Dataset: team_stats_career_playoffs_pitching

Team pitching stats, type careerPlayoffs.

- **View:** `mlb_team_stats_career_playoffs_pitching`
- **Processed path:** `processed/mlb_api/team_stats_career_playoffs_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_playoffs_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_regular_season_catching -->
### Dataset: team_stats_career_regular_season_catching

Team catching stats, type careerRegularSeason.

- **View:** `mlb_team_stats_career_regular_season_catching`
- **Processed path:** `processed/mlb_api/team_stats_career_regular_season_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_regular_season_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_regular_season_fielding -->
### Dataset: team_stats_career_regular_season_fielding

Team fielding stats, type careerRegularSeason.

- **View:** `mlb_team_stats_career_regular_season_fielding`
- **Processed path:** `processed/mlb_api/team_stats_career_regular_season_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_regular_season_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_regular_season_hitting -->
### Dataset: team_stats_career_regular_season_hitting

Team hitting stats, type careerRegularSeason.

- **View:** `mlb_team_stats_career_regular_season_hitting`
- **Processed path:** `processed/mlb_api/team_stats_career_regular_season_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_regular_season_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_career_regular_season_pitching -->
### Dataset: team_stats_career_regular_season_pitching

Team pitching stats, type careerRegularSeason.

- **View:** `mlb_team_stats_career_regular_season_pitching`
- **Processed path:** `processed/mlb_api/team_stats_career_regular_season_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_career_regular_season_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_expected_statistics_hitting -->
### Dataset: team_stats_expected_statistics_hitting

Team hitting stats, type expectedStatistics.

- **View:** `mlb_team_stats_expected_statistics_hitting`
- **Processed path:** `processed/mlb_api/team_stats_expected_statistics_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_woba` | string | yes | `stat.woba` |  |
| `stat_woba_con` | string | yes | `stat.wobaCon` |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_full_name` | string | yes | `player.fullName` |  |
| `player_link` | string | yes | `player.link` |  |
| `player_first_name` | string | yes | `player.firstName` |  |
| `player_last_name` | string | yes | `player.lastName` |  |
| `player_primary_position_code` | string | yes | `player.primaryPosition.code` |  |
| `player_primary_position_name` | string | yes | `player.primaryPosition.name` |  |
| `player_primary_position_type` | string | yes | `player.primaryPosition.type` |  |
| `player_primary_position_abbreviation` | string | yes | `player.primaryPosition.abbreviation` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `game_type` | string | yes | `gameType` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_expected_statistics_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_game_log_catching -->
### Dataset: team_stats_game_log_catching

Team catching stats, type gameLog.

- **View:** `mlb_team_stats_game_log_catching`
- **Processed path:** `processed/mlb_api/team_stats_game_log_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`, `opponent_id`, `game_game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_game_log_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_game_log_fielding -->
### Dataset: team_stats_game_log_fielding

Team fielding stats, type gameLog.

- **View:** `mlb_team_stats_game_log_fielding`
- **Processed path:** `processed/mlb_api/team_stats_game_log_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`, `game_game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_game_log_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_game_log_hitting -->
### Dataset: team_stats_game_log_hitting

Team hitting stats, type gameLog.

- **View:** `mlb_team_stats_game_log_hitting`
- **Processed path:** `processed/mlb_api/team_stats_game_log_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_game_log_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_game_log_pitching -->
### Dataset: team_stats_game_log_pitching

Team pitching stats, type gameLog.

- **View:** `mlb_team_stats_game_log_pitching`
- **Processed path:** `processed/mlb_api/team_stats_game_log_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`, `date`, `game_game_pk`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_ties` | int32 | yes | `stat.ties` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `opponent_id` | int32 | yes | `opponent.id` |  |
| `opponent_link` | string | yes | `opponent.link` |  |
| `date` | date32[day] | yes | — |  |
| `is_home` | bool | yes | `isHome` |  |
| `is_win` | bool | yes | `isWin` |  |
| `rank` | int32 | yes | — |  |
| `game_game_pk` | int32 | yes | `game.gamePk` |  |
| `game_link` | string | yes | `game.link` |  |
| `game_content_link` | string | yes | `game.content.link` |  |
| `game_game_number` | int32 | yes | `game.gameNumber` |  |
| `game_day_night` | string | yes | `game.dayNight` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_game_log_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_last_x_games_catching -->
### Dataset: team_stats_last_x_games_catching

Team catching stats, type lastXGames.

- **View:** `mlb_team_stats_last_x_games_catching`
- **Processed path:** `processed/mlb_api/team_stats_last_x_games_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_last_x_games_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_last_x_games_fielding -->
### Dataset: team_stats_last_x_games_fielding

Team fielding stats, type lastXGames.

- **View:** `mlb_team_stats_last_x_games_fielding`
- **Processed path:** `processed/mlb_api/team_stats_last_x_games_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_last_x_games_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_last_x_games_hitting -->
### Dataset: team_stats_last_x_games_hitting

Team hitting stats, type lastXGames.

- **View:** `mlb_team_stats_last_x_games_hitting`
- **Processed path:** `processed/mlb_api/team_stats_last_x_games_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_last_x_games_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_last_x_games_pitching -->
### Dataset: team_stats_last_x_games_pitching

Team pitching stats, type lastXGames.

- **View:** `mlb_team_stats_last_x_games_pitching`
- **Processed path:** `processed/mlb_api/team_stats_last_x_games_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_ties` | int32 | yes | `stat.ties` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `num_teams` | int32 | yes | `numTeams` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_last_x_games_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_advanced_catching -->
### Dataset: team_stats_season_advanced_catching

Team catching stats, type seasonAdvanced.

- **View:** `mlb_team_stats_season_advanced_catching`
- **Processed path:** `processed/mlb_api/team_stats_season_advanced_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_pickoff_attempts` | int32 | yes | `stat.pickoffAttempts` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_advanced_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_advanced_fielding -->
### Dataset: team_stats_season_advanced_fielding

Team fielding stats, type seasonAdvanced.

- **View:** `mlb_team_stats_season_advanced_fielding`
- **Processed path:** `processed/mlb_api/team_stats_season_advanced_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_advanced_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_advanced_hitting -->
### Dataset: team_stats_season_advanced_hitting

Team hitting stats, type seasonAdvanced.

- **View:** `mlb_team_stats_season_advanced_hitting`
- **Processed path:** `processed/mlb_api/team_stats_season_advanced_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_extra_base_hits` | int32 | yes | `stat.extraBaseHits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_reached_on_error` | int32 | yes | `stat.reachedOnError` |  |
| `stat_walk_offs` | int32 | yes | `stat.walkOffs` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_advanced_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_advanced_pitching -->
### Dataset: team_stats_season_advanced_pitching

Team pitching stats, type seasonAdvanced.

- **View:** `mlb_team_stats_season_advanced_pitching`
- **Processed path:** `processed/mlb_api/team_stats_season_advanced_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_winning_percentage` | string | yes | `stat.winningPercentage` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_strikeouts_per9` | string | yes | `stat.strikeoutsPer9` |  |
| `stat_base_on_balls_per9` | string | yes | `stat.baseOnBallsPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_hits_per9` | string | yes | `stat.hitsPer9` |  |
| `stat_strikesouts_to_walks` | string | yes | `stat.strikesoutsToWalks` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_quality_starts` | int32 | yes | `stat.qualityStarts` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `stat_gidp_opp` | int32 | yes | `stat.gidpOpp` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_swings` | int32 | yes | `stat.totalSwings` |  |
| `stat_swing_and_misses` | int32 | yes | `stat.swingAndMisses` |  |
| `stat_strikeouts_minus_walks_percentage` | string | yes | `stat.strikeoutsMinusWalksPercentage` |  |
| `stat_gidp_percentage` | string | yes | `stat.gidpPercentage` |  |
| `stat_batters_faced_per_game` | string | yes | `stat.battersFacedPerGame` |  |
| `stat_innings_pitched_per_game` | string | yes | `stat.inningsPitchedPerGame` |  |
| `stat_bunts_failed` | int32 | yes | `stat.buntsFailed` |  |
| `stat_bunts_missed_tipped` | int32 | yes | `stat.buntsMissedTipped` |  |
| `stat_whiff_percentage` | string | yes | `stat.whiffPercentage` |  |
| `stat_fly_ball_percentage` | string | yes | `stat.flyBallPercentage` |  |
| `stat_balls_in_play` | int32 | yes | `stat.ballsInPlay` |  |
| `stat_run_support` | int32 | yes | `stat.runSupport` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_pitches_per_plate_appearance` | string | yes | `stat.pitchesPerPlateAppearance` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `stat_fly_outs` | int32 | yes | `stat.flyOuts` |  |
| `stat_pop_outs` | int32 | yes | `stat.popOuts` |  |
| `stat_line_outs` | int32 | yes | `stat.lineOuts` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_fly_hits` | int32 | yes | `stat.flyHits` |  |
| `stat_pop_hits` | int32 | yes | `stat.popHits` |  |
| `stat_line_hits` | int32 | yes | `stat.lineHits` |  |
| `stat_ground_hits` | int32 | yes | `stat.groundHits` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_advanced_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_catching -->
### Dataset: team_stats_season_catching

Team catching stats, type season.

- **View:** `mlb_team_stats_season_catching`
- **Processed path:** `processed/mlb_api/team_stats_season_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_pickoff_attempts` | int32 | yes | `stat.pickoffAttempts` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_fielding -->
### Dataset: team_stats_season_fielding

Team fielding stats, type season.

- **View:** `mlb_team_stats_season_fielding`
- **Processed path:** `processed/mlb_api/team_stats_season_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_passed_ball` | int32 | yes | `stat.passedBall` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_hitting -->
### Dataset: team_stats_season_hitting

Team hitting stats, type season.

- **View:** `mlb_team_stats_season_hitting`
- **Processed path:** `processed/mlb_api/team_stats_season_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_season_pitching -->
### Dataset: team_stats_season_pitching

Team pitching stats, type season.

- **View:** `mlb_team_stats_season_pitching`
- **Processed path:** `processed/mlb_api/team_stats_season_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_season_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_vs_opponents_fielding -->
### Dataset: team_stats_vs_opponents_fielding

Team fielding stats, type vsOpponents.

- **View:** `mlb_team_stats_vs_opponents_fielding`
- **Processed path:** `processed/mlb_api/team_stats_vs_opponents_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_vs_opponents_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_vs_opponents_hitting -->
### Dataset: team_stats_vs_opponents_hitting

Team hitting stats, type vsOpponents.

- **View:** `mlb_team_stats_vs_opponents_hitting`
- **Processed path:** `processed/mlb_api/team_stats_vs_opponents_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_ground_into_triple_play` | int32 | yes | `stat.groundIntoTriplePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_vs_opponents_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_vs_opponents_pitching -->
### Dataset: team_stats_vs_opponents_pitching

Team pitching stats, type vsOpponents.

- **View:** `mlb_team_stats_vs_opponents_pitching`
- **Processed path:** `processed/mlb_api/team_stats_vs_opponents_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_ground_outs` | int32 | yes | `stat.groundOuts` |  |
| `stat_air_outs` | int32 | yes | `stat.airOuts` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `stat_number_of_pitches` | int32 | yes | `stat.numberOfPitches` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_outs_pitched` | int32 | yes | `stat.outsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_save_opportunities` | int32 | yes | `stat.saveOpportunities` |  |
| `stat_holds` | int32 | yes | `stat.holds` |  |
| `stat_blown_saves` | int32 | yes | `stat.blownSaves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_balls` | int32 | yes | `stat.balls` |  |
| `stat_strikes` | int32 | yes | `stat.strikes` |  |
| `stat_strike_percentage` | string | yes | `stat.strikePercentage` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_ground_outs_to_airouts` | string | yes | `stat.groundOutsToAirouts` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_pitches_per_inning` | string | yes | `stat.pitchesPerInning` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_inherited_runners` | int32 | yes | `stat.inheritedRunners` |  |
| `stat_inherited_runners_scored` | int32 | yes | `stat.inheritedRunnersScored` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_name` | string | yes | `team.name` |  |
| `team_link` | string | yes | `team.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `sport_abbreviation` | string | yes | `sport.abbreviation` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_vs_opponents_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_advanced_catching -->
### Dataset: team_stats_year_by_year_advanced_catching

Team catching stats, type yearByYearAdvanced.

- **View:** `mlb_team_stats_year_by_year_advanced_catching`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_advanced_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_advanced_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_advanced_fielding -->
### Dataset: team_stats_year_by_year_advanced_fielding

Team fielding stats, type yearByYearAdvanced.

- **View:** `mlb_team_stats_year_by_year_advanced_fielding`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_advanced_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_advanced_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_advanced_hitting -->
### Dataset: team_stats_year_by_year_advanced_hitting

Team hitting stats, type yearByYearAdvanced.

- **View:** `mlb_team_stats_year_by_year_advanced_hitting`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_advanced_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_extra_base_hits` | int32 | yes | `stat.extraBaseHits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `stat_iso` | string | yes | `stat.iso` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_walk_offs` | int32 | yes | `stat.walkOffs` |  |
| `stat_gidp` | int32 | yes | `stat.gidp` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_advanced_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_advanced_pitching -->
### Dataset: team_stats_year_by_year_advanced_pitching

Team pitching stats, type yearByYearAdvanced.

- **View:** `mlb_team_stats_year_by_year_advanced_pitching`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_advanced_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_winning_percentage` | string | yes | `stat.winningPercentage` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_strikeouts_per9` | string | yes | `stat.strikeoutsPer9` |  |
| `stat_base_on_balls_per9` | string | yes | `stat.baseOnBallsPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `stat_hits_per9` | string | yes | `stat.hitsPer9` |  |
| `stat_strikesouts_to_walks` | string | yes | `stat.strikesoutsToWalks` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_strikeouts_minus_walks_percentage` | string | yes | `stat.strikeoutsMinusWalksPercentage` |  |
| `stat_batters_faced_per_game` | string | yes | `stat.battersFacedPerGame` |  |
| `stat_innings_pitched_per_game` | string | yes | `stat.inningsPitchedPerGame` |  |
| `stat_walks_per_plate_appearance` | string | yes | `stat.walksPerPlateAppearance` |  |
| `stat_strikeouts_per_plate_appearance` | string | yes | `stat.strikeoutsPerPlateAppearance` |  |
| `stat_home_runs_per_plate_appearance` | string | yes | `stat.homeRunsPerPlateAppearance` |  |
| `stat_walks_per_strikeout` | string | yes | `stat.walksPerStrikeout` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_advanced_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_catching -->
### Dataset: team_stats_year_by_year_catching

Team catching stats, type yearByYear.

- **View:** `mlb_team_stats_year_by_year_catching`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_fielding -->
### Dataset: team_stats_year_by_year_fielding

Team fielding stats, type yearByYear.

- **View:** `mlb_team_stats_year_by_year_fielding`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_hitting -->
### Dataset: team_stats_year_by_year_hitting

Team hitting stats, type yearByYear.

- **View:** `mlb_team_stats_year_by_year_hitting`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_pitching -->
### Dataset: team_stats_year_by_year_pitching

Team pitching stats, type yearByYear.

- **View:** `mlb_team_stats_year_by_year_pitching`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_pitching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_playoffs_catching -->
### Dataset: team_stats_year_by_year_playoffs_catching

Team catching stats, type yearByYearPlayoffs.

- **View:** `mlb_team_stats_year_by_year_playoffs_catching`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_playoffs_catching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_intentional_walks` | int32 | yes | `stat.intentionalWalks` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_pickoffs` | int32 | yes | `stat.pickoffs` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_catchers_interference` | int32 | yes | `stat.catchersInterference` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_sac_flies` | int32 | yes | `stat.sacFlies` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_playoffs_catching -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_playoffs_fielding -->
### Dataset: team_stats_year_by_year_playoffs_fielding

Team fielding stats, type yearByYearPlayoffs.

- **View:** `mlb_team_stats_year_by_year_playoffs_fielding`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_playoffs_fielding/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_assists` | int32 | yes | `stat.assists` |  |
| `stat_put_outs` | int32 | yes | `stat.putOuts` |  |
| `stat_errors` | int32 | yes | `stat.errors` |  |
| `stat_chances` | int32 | yes | `stat.chances` |  |
| `stat_fielding` | string | yes | `stat.fielding` |  |
| `stat_range_factor_per_game` | string | yes | `stat.rangeFactorPerGame` |  |
| `stat_range_factor_per9_inn` | string | yes | `stat.rangeFactorPer9Inn` |  |
| `stat_innings` | string | yes | `stat.innings` |  |
| `stat_games` | int32 | yes | `stat.games` |  |
| `stat_double_plays` | int32 | yes | `stat.doublePlays` |  |
| `stat_triple_plays` | int32 | yes | `stat.triplePlays` |  |
| `stat_throwing_errors` | int32 | yes | `stat.throwingErrors` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_playoffs_fielding -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_playoffs_hitting -->
### Dataset: team_stats_year_by_year_playoffs_hitting

Team hitting stats, type yearByYearPlayoffs.

- **View:** `mlb_team_stats_year_by_year_playoffs_hitting`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_playoffs_hitting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_doubles` | int32 | yes | `stat.doubles` |  |
| `stat_triples` | int32 | yes | `stat.triples` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_slg` | string | yes | `stat.slg` |  |
| `stat_ops` | string | yes | `stat.ops` |  |
| `stat_stolen_bases` | int32 | yes | `stat.stolenBases` |  |
| `stat_plate_appearances` | int32 | yes | `stat.plateAppearances` |  |
| `stat_total_bases` | int32 | yes | `stat.totalBases` |  |
| `stat_rbi` | int32 | yes | `stat.rbi` |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `stat_babip` | string | yes | `stat.babip` |  |
| `stat_at_bats_per_home_run` | string | yes | `stat.atBatsPerHomeRun` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_left_on_base` | int32 | yes | `stat.leftOnBase` |  |
| `stat_caught_stealing` | int32 | yes | `stat.caughtStealing` |  |
| `stat_stolen_base_percentage` | string | yes | `stat.stolenBasePercentage` |  |
| `stat_caught_stealing_percentage` | string | yes | `stat.caughtStealingPercentage` |  |
| `stat_ground_into_double_play` | int32 | yes | `stat.groundIntoDoublePlay` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_playoffs_hitting -->

<!-- BEGIN GENERATED:mlb_api.team_stats_year_by_year_playoffs_pitching -->
### Dataset: team_stats_year_by_year_playoffs_pitching

Team pitching stats, type yearByYearPlayoffs.

- **View:** `mlb_team_stats_year_by_year_playoffs_pitching`
- **Processed path:** `processed/mlb_api/team_stats_year_by_year_playoffs_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `team_id`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `stats_type_display_name` | string | yes | `stats.type.displayName` |  |
| `stats_group_display_name` | string | yes | `stats.group.displayName` |  |
| `stats_total_splits` | int32 | yes | `stats.totalSplits` |  |
| `stats_exemptions` | string | yes | `stats.exemptions` |  |
| `stats_splits_tied_with_offset` | string | yes | `stats.splitsTiedWithOffset` |  |
| `stats_splits_tied_with_limit` | string | yes | `stats.splitsTiedWithLimit` |  |
| `season` | string | yes | — |  |
| `stat_games_played` | int32 | yes | `stat.gamesPlayed` |  |
| `stat_games_started` | int32 | yes | `stat.gamesStarted` |  |
| `stat_runs` | int32 | yes | `stat.runs` |  |
| `stat_home_runs` | int32 | yes | `stat.homeRuns` |  |
| `stat_strike_outs` | int32 | yes | `stat.strikeOuts` |  |
| `stat_base_on_balls` | int32 | yes | `stat.baseOnBalls` |  |
| `stat_hits` | int32 | yes | `stat.hits` |  |
| `stat_hit_by_pitch` | int32 | yes | `stat.hitByPitch` |  |
| `stat_avg` | string | yes | `stat.avg` |  |
| `stat_at_bats` | int32 | yes | `stat.atBats` |  |
| `stat_obp` | string | yes | `stat.obp` |  |
| `stat_era` | string | yes | `stat.era` |  |
| `stat_innings_pitched` | string | yes | `stat.inningsPitched` |  |
| `stat_wins` | int32 | yes | `stat.wins` |  |
| `stat_losses` | int32 | yes | `stat.losses` |  |
| `stat_saves` | int32 | yes | `stat.saves` |  |
| `stat_earned_runs` | int32 | yes | `stat.earnedRuns` |  |
| `stat_whip` | string | yes | `stat.whip` |  |
| `stat_batters_faced` | int32 | yes | `stat.battersFaced` |  |
| `stat_outs` | int32 | yes | `stat.outs` |  |
| `stat_games_pitched` | int32 | yes | `stat.gamesPitched` |  |
| `stat_complete_games` | int32 | yes | `stat.completeGames` |  |
| `stat_shutouts` | int32 | yes | `stat.shutouts` |  |
| `stat_hit_batsmen` | int32 | yes | `stat.hitBatsmen` |  |
| `stat_balks` | int32 | yes | `stat.balks` |  |
| `stat_wild_pitches` | int32 | yes | `stat.wildPitches` |  |
| `stat_win_percentage` | string | yes | `stat.winPercentage` |  |
| `stat_games_finished` | int32 | yes | `stat.gamesFinished` |  |
| `stat_strikeout_walk_ratio` | string | yes | `stat.strikeoutWalkRatio` |  |
| `stat_strikeouts_per9_inn` | string | yes | `stat.strikeoutsPer9Inn` |  |
| `stat_walks_per9_inn` | string | yes | `stat.walksPer9Inn` |  |
| `stat_hits_per9_inn` | string | yes | `stat.hitsPer9Inn` |  |
| `stat_runs_scored_per9` | string | yes | `stat.runsScoredPer9` |  |
| `stat_home_runs_per9` | string | yes | `stat.homeRunsPer9` |  |
| `team_id` | int32 | yes | `team.id` |  |
| `team_link` | string | yes | `team.link` |  |
| `rank` | int32 | yes | — |  |
| `stat_sac_bunts` | int32 | yes | `stat.sacBunts` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.team_stats_year_by_year_playoffs_pitching -->

<!-- BEGIN GENERATED:mlb_api.teams_season -->
### Dataset: teams_season

Teams of a season (sport 1 = MLB).

- **View:** `mlb_teams_season`
- **Processed path:** `processed/mlb_api/teams_season/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `sport_id` | int32 | yes | — |  |
| `spring_league_id` | int32 | yes | `springLeague.id` |  |
| `spring_league_name` | string | yes | `springLeague.name` |  |
| `spring_league_link` | string | yes | `springLeague.link` |  |
| `spring_league_abbreviation` | string | yes | `springLeague.abbreviation` |  |
| `all_star_status` | string | yes | `allStarStatus` |  |
| `id` | int32 | yes | — |  |
| `name` | string | yes | — |  |
| `link` | string | yes | — |  |
| `season` | int32 | yes | — |  |
| `venue_id` | int32 | yes | `venue.id` |  |
| `venue_name` | string | yes | `venue.name` |  |
| `venue_link` | string | yes | `venue.link` |  |
| `spring_venue_id` | int32 | yes | `springVenue.id` |  |
| `spring_venue_link` | string | yes | `springVenue.link` |  |
| `team_code` | string | yes | `teamCode` |  |
| `file_code` | string | yes | `fileCode` |  |
| `abbreviation` | string | yes | — |  |
| `team_name` | string | yes | `teamName` |  |
| `location_name` | string | yes | `locationName` |  |
| `first_year_of_play` | string | yes | `firstYearOfPlay` |  |
| `league_id` | int32 | yes | `league.id` |  |
| `league_name` | string | yes | `league.name` |  |
| `league_link` | string | yes | `league.link` |  |
| `division_id` | int32 | yes | `division.id` |  |
| `division_name` | string | yes | `division.name` |  |
| `division_link` | string | yes | `division.link` |  |
| `sport_id_2` | int32 | yes | `sport.id` |  |
| `sport_link` | string | yes | `sport.link` |  |
| `sport_name` | string | yes | `sport.name` |  |
| `short_name` | string | yes | `shortName` |  |
| `franchise_name` | string | yes | `franchiseName` |  |
| `club_name` | string | yes | `clubName` |  |
| `active` | bool | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.teams_season -->

<!-- BEGIN GENERATED:mlb_api.game_feed_linescore_innings -->
### Dataset: game_feed_linescore_innings

Inning-by-inning linescore from the live feed.

- **View:** `mlb_game_feed_linescore_innings`
- **Processed path:** `processed/mlb_api/game_feed_linescore_innings/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `num`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `num` | int32 | yes | — |  |
| `ordinal_num` | string | yes | `ordinalNum` |  |
| `home_runs` | int32 | yes | `home.runs` |  |
| `home_hits` | int32 | yes | `home.hits` |  |
| `home_errors` | int32 | yes | `home.errors` |  |
| `home_left_on_base` | int32 | yes | `home.leftOnBase` |  |
| `away_runs` | int32 | yes | `away.runs` |  |
| `away_hits` | int32 | yes | `away.hits` |  |
| `away_errors` | int32 | yes | `away.errors` |  |
| `away_left_on_base` | int32 | yes | `away.leftOnBase` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_feed_linescore_innings -->

<!-- BEGIN GENERATED:mlb_api.game_feed_officials -->
### Dataset: game_feed_officials

Umpires of a final game from the live feed.

- **View:** `mlb_game_feed_officials`
- **Processed path:** `processed/mlb_api/game_feed_officials/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `official_type`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `official_id` | int32 | yes | `official.id` |  |
| `official_full_name` | string | yes | `official.fullName` |  |
| `official_link` | string | yes | `official.link` |  |
| `official_type` | string | yes | `officialType` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_feed_officials -->

<!-- BEGIN GENERATED:mlb_api.game_feed_play_events -->
### Dataset: game_feed_play_events

Every pitch/action event of a final game (pitchData, hitData, details, count) with its plate appearance's context.

- **View:** `mlb_game_feed_play_events`
- **Processed path:** `processed/mlb_api/game_feed_play_events/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `all_plays_about_at_bat_index`, `index`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `all_plays_result_type` | string | yes | `allPlays.result.type` |  |
| `all_plays_result_event` | string | yes | `allPlays.result.event` |  |
| `all_plays_result_event_type` | string | yes | `allPlays.result.eventType` |  |
| `all_plays_result_description` | string | yes | `allPlays.result.description` |  |
| `all_plays_result_rbi` | int32 | yes | `allPlays.result.rbi` |  |
| `all_plays_result_away_score` | int32 | yes | `allPlays.result.awayScore` |  |
| `all_plays_result_home_score` | int32 | yes | `allPlays.result.homeScore` |  |
| `all_plays_result_is_out` | bool | yes | `allPlays.result.isOut` |  |
| `all_plays_about_at_bat_index` | int32 | yes | `allPlays.about.atBatIndex` |  |
| `all_plays_about_half_inning` | string | yes | `allPlays.about.halfInning` |  |
| `all_plays_about_is_top_inning` | bool | yes | `allPlays.about.isTopInning` |  |
| `all_plays_about_inning` | int32 | yes | `allPlays.about.inning` |  |
| `all_plays_about_start_time` | timestamp[us, tz=UTC] | yes | `allPlays.about.startTime` |  |
| `all_plays_about_end_time` | timestamp[us, tz=UTC] | yes | `allPlays.about.endTime` |  |
| `all_plays_about_is_complete` | bool | yes | `allPlays.about.isComplete` |  |
| `all_plays_about_is_scoring_play` | bool | yes | `allPlays.about.isScoringPlay` |  |
| `all_plays_about_has_review` | bool | yes | `allPlays.about.hasReview` |  |
| `all_plays_about_has_out` | bool | yes | `allPlays.about.hasOut` |  |
| `all_plays_about_captivating_index` | int32 | yes | `allPlays.about.captivatingIndex` |  |
| `all_plays_count_balls` | int32 | yes | `allPlays.count.balls` |  |
| `all_plays_count_strikes` | int32 | yes | `allPlays.count.strikes` |  |
| `all_plays_count_outs` | int32 | yes | `allPlays.count.outs` |  |
| `all_plays_matchup_batter_id` | int32 | yes | `allPlays.matchup.batter.id` |  |
| `all_plays_matchup_batter_full_name` | string | yes | `allPlays.matchup.batter.fullName` |  |
| `all_plays_matchup_batter_link` | string | yes | `allPlays.matchup.batter.link` |  |
| `all_plays_matchup_bat_side_code` | string | yes | `allPlays.matchup.batSide.code` |  |
| `all_plays_matchup_bat_side_description` | string | yes | `allPlays.matchup.batSide.description` |  |
| `all_plays_matchup_pitcher_id` | int32 | yes | `allPlays.matchup.pitcher.id` |  |
| `all_plays_matchup_pitcher_full_name` | string | yes | `allPlays.matchup.pitcher.fullName` |  |
| `all_plays_matchup_pitcher_link` | string | yes | `allPlays.matchup.pitcher.link` |  |
| `all_plays_matchup_pitch_hand_code` | string | yes | `allPlays.matchup.pitchHand.code` |  |
| `all_plays_matchup_pitch_hand_description` | string | yes | `allPlays.matchup.pitchHand.description` |  |
| `all_plays_matchup_batter_hot_cold_zones` | string | yes | `allPlays.matchup.batterHotColdZones` |  |
| `all_plays_matchup_pitcher_hot_cold_zones` | string | yes | `allPlays.matchup.pitcherHotColdZones` |  |
| `all_plays_matchup_splits_batter` | string | yes | `allPlays.matchup.splits.batter` |  |
| `all_plays_matchup_splits_pitcher` | string | yes | `allPlays.matchup.splits.pitcher` |  |
| `all_plays_matchup_splits_men_on_base` | string | yes | `allPlays.matchup.splits.menOnBase` |  |
| `all_plays_pitch_index` | string | yes | `allPlays.pitchIndex` |  |
| `all_plays_action_index` | string | yes | `allPlays.actionIndex` |  |
| `all_plays_runner_index` | string | yes | `allPlays.runnerIndex` |  |
| `all_plays_runners` | string | yes | `allPlays.runners` |  |
| `all_plays_play_end_time` | timestamp[us, tz=UTC] | yes | `allPlays.playEndTime` |  |
| `all_plays_at_bat_index` | int32 | yes | `allPlays.atBatIndex` |  |
| `details_description` | string | yes | `details.description` |  |
| `details_event` | string | yes | `details.event` |  |
| `details_event_type` | string | yes | `details.eventType` |  |
| `details_away_score` | int32 | yes | `details.awayScore` |  |
| `details_home_score` | int32 | yes | `details.homeScore` |  |
| `details_is_scoring_play` | bool | yes | `details.isScoringPlay` |  |
| `details_is_out` | bool | yes | `details.isOut` |  |
| `details_has_review` | bool | yes | `details.hasReview` |  |
| `count_balls` | int32 | yes | `count.balls` |  |
| `count_strikes` | int32 | yes | `count.strikes` |  |
| `count_outs` | int32 | yes | `count.outs` |  |
| `index` | int32 | yes | — |  |
| `start_time` | timestamp[us, tz=UTC] | yes | `startTime` |  |
| `end_time` | timestamp[us, tz=UTC] | yes | `endTime` |  |
| `is_pitch` | bool | yes | `isPitch` |  |
| `type` | string | yes | — |  |
| `player_id` | int32 | yes | `player.id` |  |
| `player_link` | string | yes | `player.link` |  |
| `details_call_code` | string | yes | `details.call.code` |  |
| `details_call_description` | string | yes | `details.call.description` |  |
| `details_code` | string | yes | `details.code` |  |
| `details_ball_color` | string | yes | `details.ballColor` |  |
| `details_trail_color` | string | yes | `details.trailColor` |  |
| `details_is_in_play` | bool | yes | `details.isInPlay` |  |
| `details_is_strike` | bool | yes | `details.isStrike` |  |
| `details_is_ball` | bool | yes | `details.isBall` |  |
| `details_type_code` | string | yes | `details.type.code` |  |
| `details_type_description` | string | yes | `details.type.description` |  |
| `pitch_data_start_speed` | double | yes | `pitchData.startSpeed` |  |
| `pitch_data_end_speed` | double | yes | `pitchData.endSpeed` |  |
| `pitch_data_strike_zone_top` | double | yes | `pitchData.strikeZoneTop` |  |
| `pitch_data_strike_zone_bottom` | double | yes | `pitchData.strikeZoneBottom` |  |
| `pitch_data_coordinates_a_y` | double | yes | `pitchData.coordinates.aY` |  |
| `pitch_data_coordinates_a_z` | double | yes | `pitchData.coordinates.aZ` |  |
| `pitch_data_coordinates_pfx_x` | double | yes | `pitchData.coordinates.pfxX` |  |
| `pitch_data_coordinates_pfx_z` | double | yes | `pitchData.coordinates.pfxZ` |  |
| `pitch_data_coordinates_p_x` | double | yes | `pitchData.coordinates.pX` |  |
| `pitch_data_coordinates_p_z` | double | yes | `pitchData.coordinates.pZ` |  |
| `pitch_data_coordinates_v_x0` | double | yes | `pitchData.coordinates.vX0` |  |
| `pitch_data_coordinates_v_y0` | double | yes | `pitchData.coordinates.vY0` |  |
| `pitch_data_coordinates_v_z0` | double | yes | `pitchData.coordinates.vZ0` |  |
| `pitch_data_coordinates_x` | double | yes | `pitchData.coordinates.x` |  |
| `pitch_data_coordinates_y` | double | yes | `pitchData.coordinates.y` |  |
| `pitch_data_coordinates_x0` | double | yes | `pitchData.coordinates.x0` |  |
| `pitch_data_coordinates_y0` | double | yes | `pitchData.coordinates.y0` |  |
| `pitch_data_coordinates_z0` | double | yes | `pitchData.coordinates.z0` |  |
| `pitch_data_coordinates_a_x` | double | yes | `pitchData.coordinates.aX` |  |
| `pitch_data_breaks_break_angle` | double | yes | `pitchData.breaks.breakAngle` |  |
| `pitch_data_breaks_break_length` | double | yes | `pitchData.breaks.breakLength` |  |
| `pitch_data_breaks_break_y` | double | yes | `pitchData.breaks.breakY` |  |
| `pitch_data_breaks_break_vertical` | double | yes | `pitchData.breaks.breakVertical` |  |
| `pitch_data_breaks_break_vertical_induced` | double | yes | `pitchData.breaks.breakVerticalInduced` |  |
| `pitch_data_breaks_break_horizontal` | double | yes | `pitchData.breaks.breakHorizontal` |  |
| `pitch_data_breaks_spin_rate` | int32 | yes | `pitchData.breaks.spinRate` |  |
| `pitch_data_breaks_spin_direction` | int32 | yes | `pitchData.breaks.spinDirection` |  |
| `pitch_data_zone` | int32 | yes | `pitchData.zone` |  |
| `pitch_data_type_confidence` | double | yes | `pitchData.typeConfidence` |  |
| `pitch_data_plate_time` | double | yes | `pitchData.plateTime` |  |
| `pitch_data_extension` | double | yes | `pitchData.extension` |  |
| `play_id` | string | yes | `playId` |  |
| `pitch_number` | int32 | yes | `pitchNumber` |  |
| `hit_data_launch_speed` | double | yes | `hitData.launchSpeed` |  |
| `hit_data_launch_angle` | double | yes | `hitData.launchAngle` |  |
| `hit_data_total_distance` | double | yes | `hitData.totalDistance` |  |
| `hit_data_trajectory` | string | yes | `hitData.trajectory` |  |
| `hit_data_hardness` | string | yes | `hitData.hardness` |  |
| `hit_data_location` | string | yes | `hitData.location` |  |
| `hit_data_coordinates_coord_x` | double | yes | `hitData.coordinates.coordX` |  |
| `hit_data_coordinates_coord_y` | double | yes | `hitData.coordinates.coordY` |  |
| `all_plays_matchup_post_on_second_id` | int32 | yes | `allPlays.matchup.postOnSecond.id` |  |
| `all_plays_matchup_post_on_second_full_name` | string | yes | `allPlays.matchup.postOnSecond.fullName` |  |
| `all_plays_matchup_post_on_second_link` | string | yes | `allPlays.matchup.postOnSecond.link` |  |
| `all_plays_matchup_post_on_first_id` | int32 | yes | `allPlays.matchup.postOnFirst.id` |  |
| `all_plays_matchup_post_on_first_full_name` | string | yes | `allPlays.matchup.postOnFirst.fullName` |  |
| `all_plays_matchup_post_on_first_link` | string | yes | `allPlays.matchup.postOnFirst.link` |  |
| `details_runner_going` | bool | yes | `details.runnerGoing` |  |
| `details_from_catcher` | bool | yes | `details.fromCatcher` |  |
| `details_disengagement_num` | int32 | yes | `details.disengagementNum` |  |
| `all_plays_matchup_post_on_third_id` | int32 | yes | `allPlays.matchup.postOnThird.id` |  |
| `all_plays_matchup_post_on_third_full_name` | string | yes | `allPlays.matchup.postOnThird.fullName` |  |
| `all_plays_matchup_post_on_third_link` | string | yes | `allPlays.matchup.postOnThird.link` |  |
| `action_play_id` | string | yes | `actionPlayId` |  |
| `is_base_running_play` | bool | yes | `isBaseRunningPlay` |  |
| `is_substitution` | bool | yes | `isSubstitution` |  |
| `position_code` | string | yes | `position.code` |  |
| `position_name` | string | yes | `position.name` |  |
| `position_type` | string | yes | `position.type` |  |
| `position_abbreviation` | string | yes | `position.abbreviation` |  |
| `all_plays_review_details_is_overturned` | bool | yes | `allPlays.reviewDetails.isOverturned` |  |
| `all_plays_review_details_in_progress` | bool | yes | `allPlays.reviewDetails.inProgress` |  |
| `all_plays_review_details_review_type` | string | yes | `allPlays.reviewDetails.reviewType` |  |
| `all_plays_review_details_challenge_team_id` | int32 | yes | `allPlays.reviewDetails.challengeTeamId` |  |
| `batting_order` | string | yes | `battingOrder` |  |
| `replaced_player_id` | int32 | yes | `replacedPlayer.id` |  |
| `replaced_player_link` | string | yes | `replacedPlayer.link` |  |
| `base` | int32 | yes | — |  |
| `details_violation_type` | string | yes | `details.violation.type` |  |
| `details_violation_description` | string | yes | `details.violation.description` |  |
| `details_violation_player_id` | int32 | yes | `details.violation.player.id` |  |
| `details_violation_player_full_name` | string | yes | `details.violation.player.fullName` |  |
| `pfx_id` | string | yes | `pfxId` |  |
| `umpire_id` | int32 | yes | `umpire.id` |  |
| `umpire_link` | string | yes | `umpire.link` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_feed_play_events -->

<!-- BEGIN GENERATED:mlb_api.game_feed_plays -->
### Dataset: game_feed_plays

Every plate appearance of a final game from the live feed (result, about, count, matchup).

- **View:** `mlb_game_feed_plays`
- **Processed path:** `processed/mlb_api/game_feed_plays/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_pk`, `about_at_bat_index`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_pk` | int32 | yes | — |  |
| `result_type` | string | yes | `result.type` |  |
| `result_event` | string | yes | `result.event` |  |
| `result_event_type` | string | yes | `result.eventType` |  |
| `result_description` | string | yes | `result.description` |  |
| `result_rbi` | int32 | yes | `result.rbi` |  |
| `result_away_score` | int32 | yes | `result.awayScore` |  |
| `result_home_score` | int32 | yes | `result.homeScore` |  |
| `result_is_out` | bool | yes | `result.isOut` |  |
| `about_at_bat_index` | int32 | yes | `about.atBatIndex` |  |
| `about_half_inning` | string | yes | `about.halfInning` |  |
| `about_is_top_inning` | bool | yes | `about.isTopInning` |  |
| `about_inning` | int32 | yes | `about.inning` |  |
| `about_start_time` | timestamp[us, tz=UTC] | yes | `about.startTime` |  |
| `about_end_time` | timestamp[us, tz=UTC] | yes | `about.endTime` |  |
| `about_is_complete` | bool | yes | `about.isComplete` |  |
| `about_is_scoring_play` | bool | yes | `about.isScoringPlay` |  |
| `about_has_review` | bool | yes | `about.hasReview` |  |
| `about_has_out` | bool | yes | `about.hasOut` |  |
| `about_captivating_index` | int32 | yes | `about.captivatingIndex` |  |
| `count_balls` | int32 | yes | `count.balls` |  |
| `count_strikes` | int32 | yes | `count.strikes` |  |
| `count_outs` | int32 | yes | `count.outs` |  |
| `matchup_batter_id` | int32 | yes | `matchup.batter.id` |  |
| `matchup_batter_full_name` | string | yes | `matchup.batter.fullName` |  |
| `matchup_batter_link` | string | yes | `matchup.batter.link` |  |
| `matchup_bat_side_code` | string | yes | `matchup.batSide.code` |  |
| `matchup_bat_side_description` | string | yes | `matchup.batSide.description` |  |
| `matchup_pitcher_id` | int32 | yes | `matchup.pitcher.id` |  |
| `matchup_pitcher_full_name` | string | yes | `matchup.pitcher.fullName` |  |
| `matchup_pitcher_link` | string | yes | `matchup.pitcher.link` |  |
| `matchup_pitch_hand_code` | string | yes | `matchup.pitchHand.code` |  |
| `matchup_pitch_hand_description` | string | yes | `matchup.pitchHand.description` |  |
| `matchup_batter_hot_cold_zones` | string | yes | `matchup.batterHotColdZones` |  |
| `matchup_pitcher_hot_cold_zones` | string | yes | `matchup.pitcherHotColdZones` |  |
| `matchup_splits_batter` | string | yes | `matchup.splits.batter` |  |
| `matchup_splits_pitcher` | string | yes | `matchup.splits.pitcher` |  |
| `matchup_splits_men_on_base` | string | yes | `matchup.splits.menOnBase` |  |
| `pitch_index` | string | yes | `pitchIndex` |  |
| `action_index` | string | yes | `actionIndex` |  |
| `runner_index` | string | yes | `runnerIndex` |  |
| `runners` | string | yes | — |  |
| `play_events` | string | yes | `playEvents` |  |
| `play_end_time` | timestamp[us, tz=UTC] | yes | `playEndTime` |  |
| `at_bat_index` | int32 | yes | `atBatIndex` |  |
| `matchup_post_on_second_id` | int32 | yes | `matchup.postOnSecond.id` |  |
| `matchup_post_on_second_full_name` | string | yes | `matchup.postOnSecond.fullName` |  |
| `matchup_post_on_second_link` | string | yes | `matchup.postOnSecond.link` |  |
| `matchup_post_on_first_id` | int32 | yes | `matchup.postOnFirst.id` |  |
| `matchup_post_on_first_full_name` | string | yes | `matchup.postOnFirst.fullName` |  |
| `matchup_post_on_first_link` | string | yes | `matchup.postOnFirst.link` |  |
| `matchup_post_on_third_id` | int32 | yes | `matchup.postOnThird.id` |  |
| `matchup_post_on_third_full_name` | string | yes | `matchup.postOnThird.fullName` |  |
| `matchup_post_on_third_link` | string | yes | `matchup.postOnThird.link` |  |
| `review_details_is_overturned` | bool | yes | `reviewDetails.isOverturned` |  |
| `review_details_in_progress` | bool | yes | `reviewDetails.inProgress` |  |
| `review_details_review_type` | string | yes | `reviewDetails.reviewType` |  |
| `review_details_challenge_team_id` | int32 | yes | `reviewDetails.challengeTeamId` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:mlb_api.game_feed_plays -->
