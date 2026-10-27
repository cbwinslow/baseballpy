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
