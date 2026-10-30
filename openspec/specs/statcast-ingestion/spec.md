# Statcast Ingestion Specification

## Purpose
The Statcast Ingestion Engine extracts, chunks, normalizes, and caches pitch-by-pitch tracking datasets, the registered Savant leaderboard variants (see section 5 and `docs/sources/statcast.md`) and, on demand, the per-game `/gf` feed from Baseball Savant (`https://baseballsavant.mlb.com`).

---

## 2. Ingestion Modes
1. **Granular Pitch Tracking (`/statcast_search/csv`):**
   - Ingests every column Savant exports (119 in every era from 2008; era-specific columns are empty before they existed) plus `_extras` for columns that appear later.
   - Splits date intervals into windows of at most 5 days (`split_date_range`) and bisects any window that reaches the 25,000-row cap.
2. **Analytical Leaderboards (`/leaderboard/*`):** one registered dataset per variant (every supported variant, e.g. `expected_statistics_batter`, `exit_velocity_batter_team`, `bat_tracking`, `outs_above_average`, `fielding_run_value`, `rolling`, `park_factors`); the authoritative list, routes, parameters, first seasons and unsupported routes are in `docs/sources/statcast.md` and `statcast/lb_catalog.py`.
3. **Game feed (`/gf?game_pk=`):** raw JSON per game, on demand or per season (`StatcastGameFeed.ingest_season`).

---

## 3. Rate Limiting & Concurrency
- Outbound requests to `baseballsavant.mlb.com` go through the shared `HttpClient` (`core/http.py`), whose host limiter is bounded to at most 2.5 requests/second.
- Concurrency is bounded by the client's semaphore (default 4).
- Transient errors are retried with jittered exponential backoff by the same client (see `concurrency-and-rate-limiting`).

---

## 4. Two-Phase Atomic Writes & Checkpointing
- All Parquet writes execute via `atomic_write_parquet()` writing to `.part` files and renaming atomically.
- Partition chunk status recorded in `manifest.json`.

---

## Requirements

### Requirement: Pitch Search Completeness
The pitch schema MUST cover every column Savant exports (119 in every era from 2008, era-specific ones nullable); columns that appear later MUST be preserved in a trailing `_extras` JSON column (never per-file inferred types), and uncastable cells MUST be quarantined. Windows hitting the 25,000-row cap MUST be bisected; a capped single day MUST raise `TruncatedResultError` and MUST NOT be cached.

#### Scenario: Filtered query
- **GIVEN** `StatcastQuery(team="NYY")` or `game_types=("R",)`
- **THEN** the rows are returned but never written to `statcast.pitches` (it would duplicate pitches).
- Verified by `tests/test_statcast_pitches.py::test_filtered_queries_return_rows_but_never_touch_the_lake`.

### Requirement: Leaderboard Registry
Every supported leaderboard *variant* MUST be a registered dataset with a schema generated from live headers (`scripts/gen_savant_schemas.py`), a documented key verified unique per season, the widest `min` qualifier and the first season with data. Types MUST NOT be inferred from column-name substrings. Routes that offer no CSV, answer 4xx, or ignore the season MUST stay listed with an `unsupported` reason or be modelled as a flat snapshot. A request that deviates from the canonical parameters MUST NOT be persisted into the registered dataset. The `StatcastLeaderboard` enum MUST equal the registry's supported slugs.

#### Scenario: Wrong season parameter
- **GIVEN** a route that ignores `year=` and returns the current season for every year
- **THEN** the probe detects identical payloads across seasons and the variant uses the route's real parameter (`season_start/season_end`, `seasonStart/seasonEnd`, `season`) or is a flat snapshot.
- Verified by `tests/test_savant_probe.py::test_identical_payloads_across_seasons_are_reported` and `tests/test_statcast_coverage.py::test_request_params_per_year_style`.

### Requirement: Season Ingest
`ingest_season(year)` MUST cover spring training through the postseason using the MLB season calendar, resume via the manifest (empty windows included), and report surplus duplicate `(game_pk, at_bat_number, pitch_number)` keys. `ingest_all(start=2008)` iterates seasons.

#### Scenario: Resumable season from the MLB calendar
- **WHEN** `ingest_season(year)` runs twice
- **THEN** the window comes from the MLB calendar, finished windows are not refetched, empty windows are recorded, and duplicate pitch keys are reported
- Verified by `tests/test_statcast_pitches.py::test_season_window_comes_from_the_mlb_calendar_and_is_cached, ::test_ingest_season_is_resumable_and_checks_pitch_keys and ::test_empty_windows_are_recorded_and_not_refetched`.

### Requirement: Game Feed
The per-game `/gf` JSON MAY be fetched on demand and stored raw (sha256); it is not part of the default `ingest` selection, and no typed table is derived from it. `StatcastGameFeed.ingest_season` is the explicit opt-in for a whole season (next requirement).

#### Scenario: Feed is raw only and cached when final
- **WHEN** a game feed is fetched
- **THEN** the raw JSON is stored with its sha256, cached as immutable only once final, and no typed table is derived
- Verified by `tests/test_statcast_coverage.py::test_game_feed_is_raw_only_cached_when_final_and_validated`.

### Requirement: Embedded-Page Leaderboards and Snapshots
Leaderboards without a CSV download MUST be ingested from the JSON value embedded in the page (`var/const/let <name>`, a list of rows or a dict of such lists) and a page without that value MUST raise. Pages that ignore the season parameter (`abs_challenges`, `rolling`) MUST be flat, unpartitioned snapshots of the current data.

#### Scenario: Embedded array required, snapshots are flat
- **WHEN** a leaderboard page has no embedded array
- **THEN** parsing raises; pages ignoring the season are flat unpartitioned snapshots
- Verified by `tests/test_statcast_coverage.py::test_html_json_requires_the_embedded_array and ::test_html_json_variant_and_flat_snapshot`.

### Requirement: Season Game Feeds
`StatcastGameFeed.ingest_season(season, max_games)` MUST fetch the feed of every final game of the season (MLB schedule), skip games already stored, and keep the immutable raw response with its sha256.

#### Scenario: Season feed ingest resumes
- **WHEN** `StatcastGameFeed.ingest_season` runs again
- **THEN** games already stored are skipped
- Verified by `tests/test_statcast_coverage.py::test_game_feed_season_ingest_is_resumable`.

### Requirement: Minor-League Pitches
The system MUST ingest Savant's minor-league pitch export (`statcast_search/csv` with `minors=true`) into the dataset `statcast.pitches_minors` with the same strict schema and key as `pitches`, partitioned by season, for every season with data (2021 onwards). The unfiltered minors population is persisted; an `hfLevel` filter (valid only with `minors=true`) is returned but never persisted. Minor-league and MLB pitches MUST NOT share a dataset; seasons before 2021 are skipped with a recorded reason and no request.

#### Scenario: Own dataset, filter never persisted, pre-2021 skipped
- **WHEN** minor-league pitches are ingested
- **THEN** they go to `pitches_minors`, an `hfLevel` filter is returned but not persisted, and seasons before 2021 are skipped without a request
- Verified by `tests/test_statcast_minors.py::test_minor_league_population_goes_to_its_own_dataset, ::test_level_filter_is_returned_but_never_persisted and ::test_seasons_before_minor_league_tracking_are_skipped_without_requests`.

### Requirement: Aligned Windows
Persisted pitch windows MUST lie on a fixed per-year grid (block k = January 1 + k x chunk_days, clipped at December 31) independent of the caller's request, so overlapping, nested or adjacent requests never store the same pitch twice. A request MUST return exactly the pitches of its requested `game_date` range.

#### Scenario: Overlapping requests leave no duplicates
- **WHEN** overlapping, nested and adjacent requests are persisted
- **THEN** windows lie on the January-first grid and no pitch is stored twice
- Verified by `tests/test_statcast_grid.py::test_grid_windows_are_anchored_to_january_first and ::test_overlapping_nested_and_adjacent_requests_leave_no_duplicates`.

### Requirement: Verified `unsupported` Verdicts
A Savant route may be recorded as `unsupported` only after the bare route and each documented parameter were tried one at a time; the entry MUST record `verified_on` and `tried`, and the audit MUST re-probe it with default parameters and report REVIVED when it answers.

#### Scenario: Entries record evidence and revive when they answer
- **WHEN** the audit runs
- **THEN** every `unsupported` entry records `verified_on` and `tried`, and one that now answers is reported REVIVED
- Verified by `tests/test_audit.py::test_every_unsupported_entry_records_when_and_what_was_tried and ::test_unsupported_leaderboard_that_answers_is_revived`.

### Requirement: Every Operation Is Audit-Logged and Timed
Every Statcast operation that downloads or stores data (pitch search windows, leaderboards, game-feed fetches and game-feed season ingests) MUST write one structured audit event (operation, endpoint, destination, records, duration, cache hit, status), and a failure MUST be logged with status FAILURE and re-raised.

#### Scenario: Game feeds leave a trail
- **WHEN** a game feed is fetched by a season ingest and the season is ingested again
- **THEN** the log holds one fetch event and two season events, the second one a cache hit
- Verified by `tests/test_statcast_coverage.py::test_game_feed_fetches_and_season_ingests_are_audit_logged`.

### Requirement: Raw Files Record an Upstream Fingerprint
Every raw Statcast file (pitch search windows, leaderboards, game feeds) MUST record an upstream fingerprint in its manifest entry: the provider's ETag when the response carries one, else the sha256 of the payload (`content_sha256`).

#### Scenario: Fingerprints are recorded
- **WHEN** a game feed, a leaderboard and a set of pitch windows are stored, with and without an ETag
- **THEN** each manifest entry holds the fingerprint of the right kind
- Verified by `tests/test_statcast_coverage.py::test_every_raw_file_records_an_upstream_fingerprint`, `tests/test_statcast_coverage.py::test_get_leaderboard_persists_strict_season_partition` and `tests/test_statcast_pitches.py::test_ingest_season_is_resumable_and_checks_pitch_keys`.

### Requirement: Stored Chunks Follow the Schema
A stored pitch window or leaderboard chunk MUST NOT be served when its recorded schema digest differs from the dataset's current schema (ADR 49) or, for a dataset with a parser revision, carries none (ADR 51); it is fetched and stored again without `--refresh`.

#### Scenario: A schema change refetches
- **WHEN** a stored chunk's schema digest differs from the dataset's
- **THEN** the next ingest fetches the window or leaderboard again
- Verified by `tests/test_statcast_pitches.py::test_pitch_chunks_written_under_another_schema_are_refetched` and `tests/test_statcast_coverage.py::test_a_leaderboard_written_under_another_schema_is_fetched_again`.

### Requirement: Provider Documentation Is Kept
`ingest statcast` MUST keep Savant's data dictionary page (`csv-docs`) under `raw/statcast/documents/` with its sha256 and an upstream fingerprint, download it once, and never let a failed download block the data.

#### Scenario: The data dictionary is kept once
- **WHEN** the documents job runs twice and then with refresh
- **THEN** the page is stored on the first run, not downloaded on the second, and fetched again on refresh; the planner adds exactly one documents job per run
- Verified by `tests/test_statcast_coverage.py::test_the_data_dictionary_page_is_kept_once_with_a_fingerprint` and `tests/test_statcast_coverage.py::test_the_planner_adds_one_documents_job_per_run`.

### Requirement: Every Dataset Is Reachable From Python
`baseballpy.sources.statcast.table(name, season)` MUST return any registered Statcast dataset by its registry name (fetching and storing it first when needed), `datasets()` MUST list exactly the registered names, and an unknown name MUST raise an error that lists the valid ones.

#### Scenario: Names resolve
- **WHEN** a leaderboard and a season of pitches are requested by name and an unknown name is requested
- **THEN** the tables come back with the registered schemas and the unknown name raises
- Verified by `tests/test_statcast_coverage.py::test_table_reaches_every_registered_dataset_by_name` and `tests/test_statcast_pitches.py::test_table_ingests_a_season_of_pitches_and_returns_it`.
