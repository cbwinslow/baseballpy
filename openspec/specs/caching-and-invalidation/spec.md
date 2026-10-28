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

#### Scenario: Datasets do not share partitions
- **GIVEN** Retrosheet regular-season and postseason events for 2023
- **THEN** they are stored in `processed/retrosheet/events/season=2023/` and `processed/retrosheet/events_postseason/season=2023/` respectively
- **AND** `SELECT count(*) FROM retrosheet_events` equals the regular-season row count only.

#### Scenario: Path helpers are read-only
- **WHEN** `LakeConfig.raw_dir(...)`/`processed_dir(...)` are evaluated on an empty home
- **THEN** no directory is created.

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

### Requirement: Manifest Checkpoint Tracking
Every partitioned source MUST maintain a `manifest.json` tracking chunk completion status (`COMPLETED`, `FAILED`), record counts, and remote ETags.

#### Scenario: Checkpoint inspection skips existing partitions
- **GIVEN** a multi-season or multi-week query
- **WHEN** scheduled for execution
- **THEN** chunks marked `COMPLETED` in the manifest are read directly from local Parquet cache without outbound HTTP requests.

### Requirement: Freshness Policy
Cached datasets MUST be revalidated per a `CachePolicy`. Completed historical seasons are immutable; current-season and reference datasets expire by TTL.

#### Scenario: Current-season schedule expires
- **GIVEN** a current-season schedule cached 20 minutes ago with TTL 15 minutes
- **WHEN** requested without `refresh`
- **THEN** it is re-fetched.

#### Scenario: In-progress boxscore not frozen
- **GIVEN** a boxscore cached while the game was in progress
- **WHEN** requested later
- **THEN** it is re-fetched; once the game is final it is cached as immutable.

### Requirement: Manifest Integrity
Manifests MUST be safe under concurrent writers and MUST NOT silently discard corrupt state.

#### Scenario: Concurrent writers
- **GIVEN** two writers completing different chunks of one manifest
- **THEN** both chunks are present after both save.

#### Scenario: Corrupt manifest
- **WHEN** `manifest.json` is invalid JSON
- **THEN** it is preserved as `manifest.json.corrupt-<ts>` and an error is logged.

### Requirement: Dead-Letter Quarantine
Rows failing coercion MUST be written to `quarantine/<source>/<date>/` with reason and context, and a structured warning MUST be logged.

#### Scenario: Bad cell is quarantined with its reason
- **WHEN** a cell fails coercion
- **THEN** a dead-letter file under `quarantine/<source>/<date>/` records the reason and context, and only the bad cell becomes NULL
- Verified by `tests/test_hardening.py::test_quarantine_writes_dead_letters and ::test_checked_cast_nulls_only_bad_cells_and_quarantines`.
