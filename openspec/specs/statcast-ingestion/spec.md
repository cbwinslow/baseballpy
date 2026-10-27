# Statcast Ingestion Specification

## 1. Overview
The Statcast Ingestion Engine extracts, chunks, normalizes, and caches pitch-by-pitch tracking datasets and 11 analytical leaderboards from Baseball Savant (`https://baseballsavant.mlb.com`).

---

## 2. Ingestion Modes
1. **Granular Pitch Tracking (`/statcast_search/csv`):**
   - Ingests all 94 available fields per pitch, including exit velocity, launch angle, trajectory coordinates, spin rates, and 2024+ bat tracking metrics (`bat_speed`, `swing_length`).
   - Automatically splits date intervals into consecutive windows of at most 5 days (`split_date_range`).
2. **Analytical Leaderboards (`/leaderboard/*`):**
   - `expected_statistics` (xBA, xSLG, xwOBA, xOBP)
   - `statcast` (Exit Velocity & Barrels)
   - `sprint_speed` (Sprint Speed & 90-ft splits)
   - `bat-tracking` (Bat Speed, Swing Length, Squared Up %, Blasts)
   - `outs_above_average` (OAA & Defensive Runs Prevented)
   - `arm-strength` (Max and average throwing velocity)
   - `poptime` (Catcher Pop Time & Exchange Time)
   - `catcher-framing` (Runs Extra Strikes & Shadow Zone Strike Rate)
   - `pitch-arsenals` (Pitch mix & average velocities)
   - `pitch-movement` (Horizontal and vertical break)
   - `abs-challenges` (Automated ball-strike challenge results)

---

## 3. Rate Limiting & Concurrency
- Outbound requests to `baseballsavant.mlb.com` route through an `aiolimiter.AsyncLimiter` strictly bounded to at most 2.5 requests/second.
- Concurrency bounded via `asyncio.Semaphore` (default 4 workers).
- Transient errors (HTTP 429, 500, 502, 503, 504, timeouts) wrapped in jittered exponential backoff via `tenacity`.

---

## 4. Two-Phase Atomic Writes & Checkpointing
- All Parquet writes execute via `atomic_write_parquet()` writing to `.part` files and renaming atomically.
- Partition chunk status recorded in `manifest.json`.

---

## 5. Coverage (complete-source-coverage, verified live 2026-10-27)

### Requirement: Pitch Search Completeness
The pitch schema MUST cover every column Savant exports (119 in every era from 2008, era-specific ones nullable); columns that appear later MUST be preserved in a trailing `_extras` JSON column (never per-file inferred types), and uncastable cells MUST be quarantined. Windows hitting the 25,000-row cap MUST be bisected; a capped single day MUST raise `TruncatedResultError` and MUST NOT be cached.

#### Scenario: Filtered query
- **GIVEN** `StatcastQuery(team="NYY")` or `game_types=("R",)`
- **THEN** the rows are returned but never written to `statcast.pitches` (it would duplicate pitches).

### Requirement: Leaderboard Registry
Every supported leaderboard *variant* MUST be a registered dataset with a schema generated from live headers (`scripts/gen_savant_schemas.py`), a documented key verified unique per season, the widest `min` qualifier and the first season with data. Types MUST NOT be inferred from column-name substrings. Routes that offer no CSV, answer 4xx, or ignore the season MUST stay listed with an `unsupported` reason or be modelled as a flat snapshot. A request that deviates from the canonical parameters MUST NOT be persisted into the registered dataset. The `StatcastLeaderboard` enum MUST equal the registry's supported slugs.

#### Scenario: Wrong season parameter
- **GIVEN** a route that ignores `year=` and returns the current season for every year
- **THEN** the probe detects identical payloads across seasons and the variant uses the route's real parameter (`season_start/season_end`, `seasonStart/seasonEnd`, `season`) or is a flat snapshot.

### Requirement: Season Ingest
`ingest_season(year)` MUST cover spring training through the postseason using the MLB season calendar, resume via the manifest (empty windows included), and report surplus duplicate `(game_pk, at_bat_number, pitch_number)` keys. `ingest_all(start=2008)` iterates seasons.

### Requirement: Game Feed
The per-game `/gf` JSON MAY be fetched on demand and stored raw (sha256); it MUST NOT be bulk-ingested and no typed table is derived from it.
