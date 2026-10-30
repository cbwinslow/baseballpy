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
