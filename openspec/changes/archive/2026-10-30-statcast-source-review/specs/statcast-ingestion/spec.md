## ADDED Requirements

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
