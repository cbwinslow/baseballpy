# Design: Crosswalk Suite

## Context & Motivation
Baseballpy ingests data from 9 disparate sources (Statcast, Retrosheet, Lahman, Chadwick, MLB API, BRef, FanGraphs, Kalshi, Polymarket). Each provider uses independent entity identifiers.
While `v_player_crosswalk` unifies player identities across Chadwick, MLBAM, Retrosheet, BRef, FanGraphs, and Lahman, game-, team-, and venue-level crosswalks were missing.

## Crosswalk Views Specification

### 1. `v_game_crosswalk`
Joins `mlb_schedule_hydrated` with `retrosheet_box_games` (when present) to map:
- `game_pk`: MLBAM game ID (numeric, primary key for Statcast & MLB API)
- `retro_game_id`: Retrosheet game ID (alphanumeric, primary key for Retrosheet)
- `game_date`: Official contest date (`DATE`)
- `season`: Contest season (`SMALLINT`)
- `game_number`: 1 for single games or game 1 of doubleheader, 2 for game 2 (`TINYINT`)
- `game_type`: Contest type (`R` regular, `P` postseason, `S` spring)
- `home_team_id_mlb`: MLBAM numeric home team ID
- `home_team_retro`: Retrosheet uppercase team code (e.g. `BOS`, `NYA`, `LAN`)
- `home_team_name`: Official display name
- `away_team_id_mlb`: MLBAM numeric away team ID
- `away_team_retro`: Retrosheet uppercase team code
- `away_team_name`: Official display name
- `venue_id`: MLBAM numeric venue ID
- `venue_name`: Official venue name

Join logic:
`mlb_schedule_hydrated.official_date = retrosheet_box_games.date`
AND `upper(mlb_schedule_hydrated.teams_home_team_team_code) = retrosheet_box_games.hometeam`
AND `mlb_schedule_hydrated.game_number = (CASE WHEN right(retrosheet_box_games.game_id, 1) = '0' THEN 1 ELSE cast(right(retrosheet_box_games.game_id, 1) as INT) END)`

### 2. `v_team_crosswalk`
Unifies team franchise identities across systems:
- `team_id_mlb`: MLBAM numeric team ID
- `team_abbr_mlb`: MLBAM abbreviation (e.g. `NYY`)
- `team_code_retro`: Retrosheet team code (e.g. `NYA`)
- `team_name`: Official franchise display name
- `league_id_mlb`: MLBAM league ID
- `division_id_mlb`: MLBAM division ID
- `active`: Current active status

### 3. `v_venue_crosswalk`
Unifies ballpark identities and physical specifications:
- `venue_id`: MLBAM numeric venue ID
- `venue_name`: Ballpark name
- `park_id_retro`: Retrosheet ballpark identifier (from `retrosheet_reference_ballparks` / `xref_ids`)
- `city`, `state`, `country`: Geographic location
- `latitude`, `longitude`, `elevation`: Physical coordinates and altitude
- `roof_type`, `turf_type`: Environmental characteristics
- `capacity`: Seating capacity
- `field_left_line`, `field_center`, `field_right_line`: Outfield fence distances

## Python Accessors in `baseballpy`
Expose zero-copy, highly ergonomic convenience functions:
- `bb.players() -> pl.DataFrame`: Returns `v_player_crosswalk`
- `bb.games(season: int | None = None) -> pl.DataFrame`: Returns `v_game_crosswalk` filtered by season
- `bb.teams() -> pl.DataFrame`: Returns `v_team_crosswalk`
- `bb.venues() -> pl.DataFrame`: Returns `v_venue_crosswalk`
- `bb.crosswalk(id_value, from_type, to_type) -> Any | None`: Top-level re-export of Chadwick ID translation
