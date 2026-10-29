# caching-and-invalidation Specification

## Purpose
Defines directory layout, source-based partitioning, hash-based invalidation mechanics, and two-phase atomic write gates across all baseball data sources.

## Requirements

### Requirement: Four-Tier Local Layout
All persisted data MUST live under `$BASEBALLPY_HOME` (default `~/.baseballpy/`) in `raw/`, `processed/`, `quarantine/`, `cache/http/`, `databases/` and `logs/`, with a `VERSION` file holding the layout version (2). Datasets MUST live only in `raw/` and `processed/`: `raw/<source>/<dataset>/[season=YYYY/]` holds immutable upstream bytes and `processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet` holds typed Parquet, one dataset per directory. Path helpers MUST NOT create directories; writers create them on write. Locations are configurable with `BASEBALLPY_HOME` and the per-tier `BASEBALLPY_*_OVERRIDE` settings of `LakeConfig`.

#### Scenario: Cache deletion is safe
- **GIVEN** a populated lake
- **WHEN** `cache/` is deleted
- **THEN** no dataset is lost and all DuckDB views still resolve.
- Verified by `tests/test_database.py::test_deleting_the_cache_loses_no_dataset_and_every_view_still_resolves`.

#### Scenario: Datasets do not share partitions
- **GIVEN** Retrosheet regular-season and postseason events for 2023
- **THEN** they are stored in `processed/retrosheet/events/season=2023/` and `processed/retrosheet/events_postseason/season=2023/` respectively
- **AND** `SELECT count(*) FROM retrosheet_events` equals the regular-season row count only.
- Verified by `tests/test_database.py::test_events_and_postseason_are_separate_views` and `tests/test_lake.py::test_regular_and_postseason_events_are_distinct_datasets`.

#### Scenario: Path helpers are read-only
- **WHEN** `LakeConfig.raw_dir(...)`/`processed_dir(...)` are evaluated on an empty home
- **THEN** no directory is created.
- Verified by `tests/test_config.py::test_lake_config_never_creates_directories_on_read`.

### Requirement: Dataset Registry and Views
Every dataset MUST be described by a `DatasetSpec` (schema, keys, partitioning, view name, documentation anchor) in the registry; the DuckDB catalog MUST create one view per dataset with data, reading only `processed/`, with a single `season` column for season-partitioned data. Read-only connections MUST NOT create views and MUST raise `DatabaseReadOnlyError` naming `baseballpy db sync` when views are missing.

#### Scenario: Every dataset with data gets a view
- **WHEN** `sync_database` runs on a lake holding registered datasets
- **THEN** each dataset with data has one view over `processed/`
- Verified by `tests/test_database.py::test_every_registered_dataset_with_data_gets_a_view`.

#### Scenario: Read-only connections do not create views
- **WHEN** a read-only connection is opened before views exist
- **THEN** `DatabaseReadOnlyError` names `baseballpy db sync`, and after a sync the read-only connection works
- Verified by `tests/test_database.py::test_read_only_requires_views_then_works and ::test_read_only_sync_is_refused`.

### Requirement: Layout Migration
`baseballpy migrate-layout` MUST convert a v1 tree to v2 idempotently, verify checksums and row counts, carry v1 manifest entries over, report (never move) unknown files, never delete v1 data unless `--delete-old` is passed, and write `VERSION` last. A detected v1 tree MUST only produce a one-time warning; nothing is moved automatically.

#### Scenario: Migration is idempotent and keeps v1
- **WHEN** `migrate-layout` runs twice, without `--delete-old`
- **THEN** the second run changes nothing and the v1 data is still present
- Verified by `tests/test_migrate.py::test_migration_is_idempotent and ::test_v1_data_is_never_deleted_unless_requested`.

#### Scenario: Corrupt copy aborts before the version stamp
- **WHEN** a copied file fails the checksum or row-count check
- **THEN** the migration aborts and `VERSION` is not written
- Verified by `tests/test_migrate.py::test_corrupt_copy_aborts_without_version_stamp`.

### Requirement: Reproducible Source Refs
GitHub-hosted sources MUST be fetched at a pinned commit SHA recorded in `core/sources_lock.json` (overridable per source by environment) and in each manifest entry's `source_ref`; a chunk recorded at a different ref MUST be refetched. `baseballpy refs update` MUST resolve the latest SHAs through the shared HTTP client.

#### Scenario: Chunk fetched at another ref is refetched
- **GIVEN** a chunk recorded at a different `source_ref` than the pinned one
- **WHEN** it is requested
- **THEN** it is fetched again at the pinned ref
- Verified by `tests/test_sources_lock.py::test_lahman_chunk_fetched_at_other_ref_is_refetched`.

#### Scenario: Refs update resolves latest SHAs
- **WHEN** `baseballpy refs update` runs
- **THEN** the latest SHAs are resolved through the shared client and written to the lake-level lock (`--dry-run` writes nothing)
- Verified by `tests/test_sources_lock.py::test_update_lock_resolves_latest_shas_and_writes_lake_lock and ::test_cli_refs_update_dry_run`.

### Requirement: Two-Phase Atomic Writing (`.part` to Target)
Every network download and columnar Parquet write MUST write to `{target_path}.part` and execute atomic `os.replace()` only after verifying record boundary and footer integrity.
If an operation is interrupted or raises an exception, the `.part` file MUST be cleaned up, preventing corrupted or partial files from polluting the cache.

#### Scenario: Interrupted write cleanup
- **GIVEN** an active download that fails or is terminated midway
- **WHEN** the exception occurs
- **THEN** the `.part` file is deleted and the target cache file is not created or altered.
- Verified by `tests/test_hardening.py::test_atomic_write_cleans_up_on_keyboard_interrupt` and `tests/test_lake.py::test_put_stream_failure_leaves_no_part_or_final_file`.

### Requirement: Manifest Checkpoint Tracking
Every partitioned source MUST maintain a `manifest.json` tracking chunk completion status (`COMPLETED`, `FAILED`), record counts, and remote ETags.

#### Scenario: Checkpoint inspection skips existing partitions
- **GIVEN** a multi-season or multi-week query
- **WHEN** scheduled for execution
- **THEN** chunks marked `COMPLETED` in the manifest are read directly from local Parquet cache without outbound HTTP requests.
- Verified by `tests/test_statcast_pitches.py::test_ingest_season_is_resumable_and_checks_pitch_keys and ::test_empty_windows_are_recorded_and_not_refetched`.

### Requirement: Freshness Policy
Cached datasets MUST be revalidated per a `CachePolicy`. Completed historical seasons are immutable; current-season and reference datasets expire by TTL.

#### Scenario: Current-season schedule expires
- **GIVEN** a current-season schedule cached 20 minutes ago with TTL 15 minutes
- **WHEN** requested without `refresh`
- **THEN** it is re-fetched.
- Verified by `tests/test_sources_hardening.py::test_mlb_current_season_schedule_expires_but_past_season_does_not`.

#### Scenario: In-progress boxscore not frozen
- **GIVEN** a boxscore cached while the game was in progress
- **WHEN** requested later
- **THEN** it is re-fetched; once the game is final it is cached as immutable.
- Verified by `tests/test_sources_hardening.py::test_mlb_boxscore_cached_forever_only_after_final`.

### Requirement: Manifest Integrity
Manifests MUST be safe under concurrent writers and MUST NOT silently discard corrupt state.

#### Scenario: Concurrent writers
- **GIVEN** two writers completing different chunks of one manifest
- **THEN** both chunks are present after both save.
- Verified by `tests/test_hardening.py::test_manifest_concurrent_writers_do_not_lose_chunks`.

#### Scenario: Corrupt manifest
- **WHEN** `manifest.json` is invalid JSON
- **THEN** it is preserved as `manifest.json.corrupt-<ts>` and an error is logged.
- Verified by `tests/test_hardening.py::test_corrupt_manifest_is_preserved_and_logged`.

### Requirement: Dead-Letter Quarantine
Rows failing coercion MUST be written to `quarantine/<source>/<date>/` with reason and context, and a structured warning MUST be logged.

#### Scenario: Bad cell is quarantined with its reason
- **WHEN** a cell fails coercion
- **THEN** a dead-letter file under `quarantine/<source>/<date>/` records the reason and context, and only the bad cell becomes NULL
- Verified by `tests/test_hardening.py::test_quarantine_writes_dead_letters and ::test_checked_cast_nulls_only_bad_cells_and_quarantines`.

### Requirement: Upstream Fingerprints
Every raw file MUST record, with its sha256, the provider's fingerprint of the downloaded version when the provider offers one (git blob or commit SHA, ETag, Last-Modified), in its manifest entry.

#### Scenario: Fingerprints are recorded with the hash
- **WHEN** a raw file is stored with an upstream fingerprint, or with only an ETag
- **THEN** the manifest entry has the sha256 and the fingerprint (the ETag becomes an ETag fingerprint)
- Verified by `tests/test_upstream.py::test_raw_store_records_the_upstream_fingerprint_with_the_sha256`.

#### Scenario: Git sources store the file's blob fingerprint
- **WHEN** the Chadwick register is downloaded from a git tree
- **THEN** each file's entry holds its git blob SHA and origin, and the commit chunk holds the commit
- Verified by `tests/test_chadwick_coverage.py::test_downloaded_files_record_their_git_blob_fingerprint`.

### Requirement: One Currency Rule
Whether a cached copy can be served MUST be decided by one shared function: not current on refresh or an unfinished entry; an expected upstream fingerprint decides alone; otherwise the copy is current within its time-to-live (past seasons never expire); after that upstream is asked once and a matching answer is current, a different one is stale, and no answer serves the copy with a warning.

#### Scenario: Expected fingerprint decides without a timer
- **GIVEN** a stored fingerprint and an expected one
- **WHEN** they match or differ, however old the copy is
- **THEN** the copy is current exactly when they match
- Verified by `tests/test_upstream.py::test_expected_fingerprint_decides_without_any_time_to_live`.

#### Scenario: A fresh copy costs no request and an expired one asks once
- **WHEN** the copy is within its time-to-live, and when it is not
- **THEN** no probe runs in the first case; in the second a matching probe is current (and renews the timestamp), a different one is stale, and an unreachable upstream serves the copy with a warning
- Verified by `tests/test_upstream.py::test_time_to_live_serves_fresh_copies_without_asking_upstream`, `tests/test_upstream.py::test_expired_copy_asks_upstream_and_compares` and `tests/test_upstream.py::test_unreachable_upstream_serves_the_copy_and_says_so`.

### Requirement: Cache Check Command
`baseballpy cache check` MUST verify every raw file against its recorded sha256 and exit 1 when one is missing or corrupt; with `--upstream` it MUST compare the stored git fingerprints with the latest tree of each repository (one tree per repository) and report changed, removed and unfingerprinted files without failing.

#### Scenario: Integrity and exit code
- **WHEN** a raw file is tampered with or deleted
- **THEN** it is reported corrupt or missing and the command exits 1; a clean lake exits 0
- Verified by `tests/test_cache_check.py::test_integrity_finds_corrupt_and_missing_files` and `tests/test_cache_check.py::test_cli_exit_codes_and_output`.

#### Scenario: Upstream comparison
- **WHEN** `--upstream` runs against a latest tree where some files changed or were removed
- **THEN** each file is reported current, changed, removed or without fingerprint, with one tree lookup per repository, and an unreachable repository is reported and not raised
- Verified by `tests/test_cache_check.py::test_upstream_comparison_reports_current_changed_removed_and_unfingerprinted` and `tests/test_cache_check.py::test_unreachable_upstream_is_reported_not_raised`.

### Requirement: Cached Jobs Are Logged As Cache Hits
An ingest job that served everything from the cache MUST be recorded in the audit log with `cache_hit` true.

#### Scenario: Cached rerun
- **WHEN** a job reports `cache_hit` and the runner records it
- **THEN** the audit event has `cache_hit` true
- Verified by `tests/test_ingest_runner.py::test_a_job_that_served_everything_from_the_cache_logs_a_cache_hit` and `tests/test_ingest_adapters.py::test_chadwick_adapter`.
