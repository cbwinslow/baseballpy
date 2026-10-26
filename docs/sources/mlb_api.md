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
