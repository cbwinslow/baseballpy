# Crosswalk Suite: Unified Identity and Cross-Source Linking

## Why
Baseball data is fragmented across multiple naming and identifier conventions:
- Players have different IDs in MLBAM (Statcast/MLB API), Retrosheet, Baseball-Reference, FanGraphs, and Lahman.
- Games are identified by numeric `game_pk` in MLBAM/Statcast, but by alphanumeric code (e.g. `BOS202404090`) in Retrosheet.
- Teams and franchises have differing abbreviations across systems (e.g. `NYY` vs `NYA`, `CHW` vs `CHA`).
- Venues have MLBAM numeric IDs and Retrosheet park codes (`PARKID`).

While `baseballpy` previously provided `v_player_crosswalk` in DuckDB and `crosswalk()` inside the `chadwick` source package, cross-source game, team, and venue linking remained ad-hoc. Users and downstream packages (like `sabermetricspy`) should be able to instantly join data across any two systems without writing complex regex or string joins.

## What Changes
1. **Catalog Identity Views in DuckDB:**
   - `v_player_crosswalk`: existing player ID crosswalk from Chadwick.
   - `v_game_crosswalk`: unified game crosswalk linking MLBAM `game_pk` to Retrosheet `game_id`, game date, season, game number (for doubleheaders), game type, home/away team identifiers, and venue.
   - `v_team_crosswalk`: multi-system team crosswalk linking MLBAM team ID/abbreviation, Retrosheet team ID, BRef team ID, and Lahman `teamID`/`franchID`.
   - `v_venue_crosswalk`: venue crosswalk linking MLBAM `venue_id` to Retrosheet ballpark code, name, geographic coordinates, elevation, roof type, and turf type.
2. **Top-Level Python Accessors:**
   - Expose `baseballpy.games(season=None)`, `baseballpy.players()`, `baseballpy.teams()`, and `baseballpy.venues()` returning zero-copy DataFrames (Polars by default, PyArrow configurable).
   - Re-export `baseballpy.crosswalk(id_value, from_type, to_type)` at the root package.
3. **Strict Decoupling:**
   - Pure metadata transformation using DuckDB views over existing Parquet lake tiers; zero network calls and zero file duplication.
