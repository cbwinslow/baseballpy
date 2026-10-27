# Statcast Ingestion Specification

## 1. Overview
The Statcast Ingestion Engine extracts, chunks, normalizes, and caches pitch-by-pitch tracking datasets, the registered Savant leaderboard variants (see section 5 and `docs/sources/statcast.md`) and, on demand, the per-game `/gf` feed from Baseball Savant (`https://baseballsavant.mlb.com`).

---

## 2. Ingestion Modes
1. **Granular Pitch Tracking (`/statcast_search/csv`):**
   - Ingests every column Savant exports (119 in every era from 2008; era-specific columns are empty before they existed) plus `_extras` for columns that appear later.
   - Splits date intervals into windows of at most 5 days (`split_date_range`) and bisects any window that reaches the 25,000-row cap.
2. **Analytical Leaderboards (`/leaderboard/*`):** one registered dataset per variant (34 supported variants, e.g. `expected_statistics_batter`, `exit_velocity_batter_team`, `bat_tracking`, `outs_above_average`, `fielding_run_value`, `rolling`, `park_factors`); the authoritative list, routes, parameters, first seasons and unsupported routes are in `docs/sources/statcast.md` and `statcast/lb_catalog.py`.
3. **Game feed (`/gf?game_pk=`):** raw JSON per game, on demand or per season (`StatcastGameFeed.ingest_season`).

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

### Requirement: Embedded-Page Leaderboards and Snapshots
Leaderboards without a CSV download MUST be ingested from the JSON value embedded in the page (`var/const/let <name>`, a list of rows or a dict of such lists) and a page without that value MUST raise. Pages that ignore the season parameter (`abs_challenges`, `rolling`) MUST be flat, unpartitioned snapshots of the current data.

### Requirement: Season Game Feeds
`StatcastGameFeed.ingest_season(season, max_games)` MUST fetch the feed of every final game of the season (MLB schedule), skip games already stored, and keep the immutable raw response with its sha256.


### Requirement: Minor-League Pitches
The system MUST ingest Savant's minor-league pitch export (`statcast_search/csv` with `minors=true`) into the dataset `statcast.pitches_minors` with the same strict schema and key as `pitches`, partitioned by season, for every season with data (2021 onwards). The unfiltered minors population is persisted; an `hfLevel` filter (valid only with `minors=true`) is returned but never persisted. Minor-league and MLB pitches MUST NOT share a dataset; seasons before 2021 are skipped with a recorded reason and no request.

### Requirement: Aligned Windows
Persisted pitch windows MUST lie on a fixed per-year grid (block k = January 1 + k x chunk_days, clipped at December 31) independent of the caller's request, so overlapping, nested or adjacent requests never store the same pitch twice. A request MUST return exactly the pitches of its requested `game_date` range.

### Requirement: Verified `unsupported` Verdicts
A Savant route may be recorded as `unsupported` only after the bare route and each documented parameter were tried one at a time; the entry MUST record `verified_on` and `tried`, and the audit MUST re-probe it with default parameters and report REVIVED when it answers.
