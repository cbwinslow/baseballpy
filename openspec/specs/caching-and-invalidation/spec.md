# caching-and-invalidation Specification

## Purpose
Defines directory layout, source-based partitioning, hash-based invalidation mechanics, and two-phase atomic write gates across all baseball data sources.

## Requirements

### Requirement: Four-Tier Local Layout
All persisted data MUST live under `$BASEBALLPY_HOME` (default `.baseballpy/` in the nearest project folder, else `~/.baseballpy/`; ADR 62) in `raw/`, `processed/`, `quarantine/`, `cache/http/`, `databases/` and `logs/`, with a `VERSION` file holding the layout version (2). Datasets MUST live only in `raw/` and `processed/`: `raw/<source>/<dataset>/[season=YYYY/]` holds immutable upstream bytes and `processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet` holds typed Parquet, one dataset per directory. Path helpers MUST NOT create directories; writers create them on write. Locations are configurable with `BASEBALLPY_HOME` and the per-tier `BASEBALLPY_*_OVERRIDE` settings of `LakeConfig`.

#### Scenario: The default data folder lives in the project
- **GIVEN** `BASEBALLPY_HOME` is not set and the working directory is inside a folder with `pyproject.toml` or `.git`
- **THEN** the data folder is `.baseballpy/` in the nearest such folder, and outside any project it is `~/.baseballpy/`
- **AND** `BASEBALLPY_HOME` still wins when set.
- Verified by `tests/test_default_home.py::test_default_is_dot_baseballpy_in_the_nearest_project_folder`, `tests/test_default_home.py::test_outside_any_project_the_home_folder_is_used` and `tests/test_default_home.py::test_environment_variables_still_win`.

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
Every partitioned source MUST maintain a `_manifest.json` tracking chunk completion status (`COMPLETED`, `FAILED`), record counts, and remote ETags.

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

#### Scenario: A big manifest with many busy writers
- **GIVEN** a manifest of 3,000 entries and 30 threads each completing eight more chunks
- **THEN** no save times out on the lock and every chunk is present afterwards (saves use the fast JSON encoder, one field per line, no indent).
- Verified by `tests/test_hardening.py::test_a_big_manifest_with_many_busy_writers_never_times_out`.

#### Scenario: Corrupt manifest
- **WHEN** `_manifest.json` is invalid JSON
- **THEN** it is preserved as `_manifest.json.corrupt-<ts>` and an error is logged.
- Verified by `tests/test_hardening.py::test_corrupt_manifest_is_preserved_and_logged`.

### Requirement: Manifest Lock Is An Operating-System Lock
A manifest save MUST hold an operating-system file lock (`<manifest>.lock`) that waits for its turn, is freed by the operating system when its holder ends and is never broken because of its age.

#### Scenario: A holder is killed
- **GIVEN** a process killed while it holds the manifest lock
- **THEN** the next process takes the lock at once, without waiting for any stale limit.
- Verified by `tests/test_manifest_oslock.py::test_a_process_killed_holding_the_lock_does_not_block_the_next`.

#### Scenario: A slow save keeps its lock
- **GIVEN** a process that holds the lock for longer than the old 60-second stale limit
- **THEN** a second process waits and enters only after the release, and times out with "could not acquire manifest lock" if it waits too long.
- Verified by `tests/test_manifest_oslock.py::test_a_lock_held_longer_than_the_old_stale_limit_is_not_broken`.

#### Scenario: Threads and processes save together
- **GIVEN** four threads and two processes saving different chunk keys of one manifest
- **THEN** every key is present afterwards.
- Verified by `tests/test_manifest_oslock.py::test_threads_and_processes_saving_different_chunks_lose_no_entry`.

### Requirement: Manifests Are Read And Written As Compact UTF-8 JSON
A `ManifestTracker` MUST decode its manifest from the file's bytes and write it as compact UTF-8 JSON in one atomic write using only the standard library (a native JSON encoder crashed the process, ADR 88 as amended), with extra memory for a save staying under three times the file size. A manifest that is not valid JSON, not valid UTF-8 or not an object with a `chunks` mapping MUST be preserved as `*.corrupt-<timestamp>` and treated as absent.

#### Scenario: Large and damaged manifests
- **WHEN** a manifest of 20,000 chunks is saved, and a manifest with bytes that are not UTF-8 is read
- **THEN** the extra memory of the save stays under three times the file size, and the damaged file is preserved and treated as absent
- Verified by `tests/test_atomic.py::test_saving_a_large_manifest_does_not_build_a_big_string`, `tests/test_atomic.py::test_a_manifest_that_is_not_utf8_is_preserved_not_lost` and `tests/test_atomic.py::test_manifest_large_entry_msgspec_roundtrip`.


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

### Requirement: Cache Check Says When Nothing Was Compared
When `baseballpy cache check --upstream` finds no file it can compare with upstream (no git fingerprint), it MUST say so; without `--upstream` it MUST say that upstream was not checked.

#### Scenario: Nothing comparable
- **WHEN** `--upstream` runs over files without a git fingerprint, and without the flag
- **THEN** the first run says nothing could be compared and the second says to add `--upstream`
- Verified by `tests/test_cache_check.py::test_upstream_run_with_nothing_comparable_says_so`.

### Requirement: A Schema Change Invalidates Stored Chunks
Every processed chunk MUST record a digest of the dataset schema it was written under (`schema_sha256` in its manifest entry), and a chunk whose recorded digest differs from the dataset's current schema MUST NOT be served as current, so it is rebuilt on the next run without `--refresh`. A chunk written before the digest existed carries none and is trusted.

#### Scenario: A column is added
- **WHEN** a chunk was stored, the dataset's schema then gains a column, and the dataset is requested again
- **THEN** the chunk is treated as stale and rebuilt, and the new manifest entry carries the new digest
- Verified by `tests/test_lake.py::test_a_schema_change_makes_a_stored_chunk_stale_without_refresh and tests/test_retrosheet_currency.py::test_a_chunk_written_under_another_schema_is_rebuilt_without_refresh`.

### Requirement: A Parser Revision Replaces Older Chunks
A dataset MAY declare a `revision`; it MUST be part of the digest stored with each chunk, and a chunk written under another revision, or carrying no digest when the dataset has a revision above 0, MUST be rebuilt on the next run without `--refresh`.

#### Scenario: A value fix keeps the columns
- **WHEN** a dataset's parser output changes but its columns do not, and its revision is raised
- **THEN** chunks written before the change are treated as stale and rebuilt
- Verified by `tests/test_lake.py::test_a_parser_revision_replaces_chunks_written_by_an_older_parser`.

### Requirement: Short Part Names and a Hidden Manifest
A processed part file MUST be named `part-<chunk>.parquet` where `<chunk>` is the chunk id without a leading `<dataset>_` and without the season token (`part-data.parquet` when nothing is left), so file names do not repeat what the folders say; two different chunks MUST never share one file name. The manifest file MUST be named `_manifest.json` (a pre-ADR-63 `manifest.json` is renamed on first use) so pandas and pyarrow folder reads skip it.

#### Scenario: Names drop the dataset and the season
- **WHEN** the chunk `award_recipients_2024_ALMVP` of `mlb_api/award_recipients` for season 2024 is stored
- **THEN** the file is `processed/mlb_api/award_recipients/season=2024/part-ALMVP.parquet`
- **AND** a second chunk that would map to the same file name is refused.
- Verified by `tests/test_part_names.py::test_part_filename_drops_what_the_folders_already_say` and `tests/test_part_names.py::test_two_chunks_that_would_share_a_file_are_refused`.

#### Scenario: Every tool reads the tree
- **GIVEN** a dataset stored in two seasons
- **THEN** DuckDB, polars, pandas and pyarrow each return the same row count
- **AND** an old `manifest.json` is renamed to `_manifest.json` the first time the manifest is opened.
- Verified by `tests/test_part_names.py::test_every_reader_sees_the_same_rows_in_the_renamed_tree` and `tests/test_part_names.py::test_a_manifest_with_the_old_name_is_renamed_on_first_use`.

### Requirement: Database Sync Drops Views of Deleted Data
`baseballpy db sync` MUST drop every view whose dataset folder no longer holds Parquet (keeping `v_player_crosswalk` and `v_season_catalog`), so a renamed or deleted dataset never leaves a view that fails when queried; the database holds views only, so nothing is lost.

#### Scenario: A deleted dataset loses its view
- **GIVEN** a synced database and a dataset folder that is then deleted
- **WHEN** the database is synced again
- **THEN** the dataset's view is gone and the other views remain
- Verified by `tests/test_database.py::test_sync_drops_a_view_whose_data_folder_is_gone`.

### Requirement: Manifests Are Parsed Only When They Change
A `ManifestTracker` MUST re-read its manifest file only when the file's size or modification time changed since it last read or wrote it, so that a chunk lookup on a manifest of thousands of entries costs a file check, not a parse. Changes made by another writer MUST still be seen on the next lookup.

#### Scenario: Lookups do not re-parse an unchanged manifest
- **WHEN** the same chunk is looked up fifty times while the file is unchanged, and then another writer adds a chunk
- **THEN** no parse happens for the fifty lookups, and the new chunk is seen on the next lookup
- Verified by `tests/test_atomic.py::test_manifest_is_parsed_only_when_the_file_changed`.

### Requirement: Cache Decisions Treat Plain And Compacted Chunks Alike
Every source MUST decide whether a chunk is already stored, and MUST read a stored chunk, through the
`ProcessedStore` (`has_part`, `is_cached`, `read_part`), never by testing for a part file name. A chunk held
by a compacted file MUST count as stored and be served without a request; a chunk whose recorded compacted
file is missing or no longer lists it MUST count as not stored and be downloaded again.

#### Scenario: A compacted Statcast season is not downloaded again
- **WHEN** a Statcast season is ingested, compacted, and ingested again
- **THEN** every window is served from the lake with no request and the same rows; with the compacted file
  removed the windows are parsed again from their raw files (no request while those are held; downloaded again only when they are not) and give the same rows
- Verified by `tests/test_cache_through_store.py::test_a_compacted_statcast_season_is_served_from_the_lake` and `tests/test_cache_through_store.py::test_a_lost_compacted_file_makes_the_windows_parse_again_from_their_raw_files`.

#### Scenario: A chunk its compacted file lacks is not cached
- **WHEN** the records call a chunk compacted but the compacted file no longer lists it
- **THEN** the store reports it as not cached
- Verified by `tests/test_cache_through_store.py::test_a_chunk_its_compacted_file_lacks_is_not_cached`.

### Requirement: A Refresh Replaces A Raw File And The Manifest Keeps A Record Of The Replaced Version
When a raw file is written again with different bytes (a refresh), `RawStore.put` MUST write the new bytes in
place and the manifest entry of that file MUST list every version it replaced under `previous` (sha256, size and
download time, oldest first). The same bytes written again MUST add nothing, and a first download MUST have no
`previous`.

#### Scenario: A file is refreshed twice
- **WHEN** a raw file is written, written again with the same bytes, written with new bytes, and written with newer bytes
- **THEN** the file holds the newest bytes, the entry's `sha256` is that of the newest bytes, and `previous` lists the two replaced versions once each with their sha256, size and download time
- Verified by `tests/test_raw_refresh_history.py::test_a_refresh_replaces_the_bytes_and_keeps_a_record_of_each_replaced_version`.

### Requirement: One Writer Per Dataset And Season: An Ingest And A Compaction Never Work On The Same Chunks At Once
`ProcessedStore.put` and `put_stream` MUST hold the cross-process lock `write-<source>-<dataset>-<season>` while they write a chunk, and `compact_dataset` MUST hold the lock of a season while it compacts that season, so that a compaction of a season and an ingest of the same season in different processes are refused (`HostBusyError`) and change nothing, while another season of the dataset stays free. The lock MUST NOT stay held after the write. A chunk the manifest records with rows that no part file and no compacted file holds MUST raise `StoredChunkMissingError` when read, never return an empty table.

#### Scenario: Same season refused, next season free, lock given back, vanished chunk
- **WHEN** another process holds a season's write lock and a chunk of that season is written, then a chunk of the next season is written, a season is compacted while another process holds the next season's lock, a chunk is written and the lock is asked for afterwards, and a chunk recorded with rows has lost its part file
- **THEN** the write of the held season is refused and changes nothing, the next season's write and the compaction succeed, the lock is free once the write ended, and the read of the vanished chunk raises instead of returning zero rows
- Verified by `tests/test_compact_lock.py::test_a_chunk_write_is_refused_while_another_process_holds_that_seasons_write_lock`, `tests/test_compact_lock.py::test_a_season_is_compacted_while_another_process_writes_the_next_season`, `tests/test_compact_lock.py::test_the_write_lock_is_held_only_while_a_chunk_is_written` and `tests/test_compact_lock.py::test_a_chunk_recorded_with_rows_but_held_nowhere_is_an_error_not_an_empty_table`.
