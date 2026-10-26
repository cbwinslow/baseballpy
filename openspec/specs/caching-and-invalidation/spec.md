# caching-and-invalidation Specification

## Purpose
Defines directory layout, source-based partitioning, hash-based invalidation mechanics, and two-phase atomic write gates across all baseball data sources.

## Requirements

### Requirement: Source-Partitioned Directory Hierarchy
The cache MUST reside within a dedicated root (`~/.baseballpy/` by default) partitioned by source:
- `cache/statcast/`
- `cache/mlb_api/`
- `cache/chadwick/`
- `cache/lahman/`
- `cache/retrosheet/raw/` and `cache/retrosheet/processed/`
The base directory MUST be configurable via environment variables (`BASEBALLPY_HOME`, `BASEBALLPY_CACHE_DIR`, `BASEBALLPY_CACHE_STATCAST_DIR_OVERRIDE`, etc.) or `PipelineConfig` powered by Pydantic Settings.

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
