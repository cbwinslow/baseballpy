# caching-and-invalidation Specification

## Purpose
Defines the directory layout, source-based partitioning, and hash-based invalidation mechanics for local caching across all baseball data sources.

## Requirements

### Requirement: Source-Partitioned Directory Hierarchy
The cache MUST reside within a dedicated root (`~/.baseballpy/` by default) partitioned by source:
- `cache/statcast/`
- `cache/mlb_api/`
- `cache/chadwick/`
- `cache/lahman/`
- `cache/retrosheet/`
The base directory MUST be configurable via environment variable `BASEBALLPY_CACHE_DIR` or `PipelineConfig`.

#### Scenario: Custom cache directory
- **GIVEN** `BASEBALLPY_CACHE_DIR="/data/shared_cache"` set in environment
- **WHEN** cache manager initializes
- **THEN** all source directories are created under `/data/shared_cache/` instead of default user home.

### Requirement: Hash-Based Update Invalidation
The cache manager MUST detect upstream updates before re-downloading existing datasets:
- **Chadwick Register:** Compares remote Git commit SHA or `ETag` against cached metadata JSON.
- **MLB Gameday:** Sends `If-None-Match` (`ETag`) headers to leverage HTTP `304 Not Modified`.
- **Statcast Completed Seasons:** Historical seasons are immutable; never re-downloaded unless explicitly instructed with `refresh=True`.

#### Scenario: Chadwick Register unchanged upstream
- **GIVEN** a local cached Chadwick Parquet file with stored commit SHA `abc1234`
- **WHEN** `chadwick_sync()` checks upstream and GitHub returns commit SHA `abc1234`
- **THEN** zero bytes of table data are downloaded and local cache is reused immediately.
