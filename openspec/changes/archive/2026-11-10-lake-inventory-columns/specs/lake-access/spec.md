## ADDED Requirements

### Requirement: The Season Catalog Is The Lake Inventory
`baseballpy db sync` MUST build the view `v_season_catalog` with one row per source, dataset and season
(season NULL for unpartitioned datasets) and the columns `source`, `dataset`, `season`, `row_count`,
`files`, `view_name`, `bytes` and `last_written_at`. `view_name` MUST be the DuckDB view that serves the
dataset (the registry view name, or `<source>_<dataset>` for an unregistered folder), `bytes` MUST be the
total size of the visible Parquet files and `last_written_at` the newest modification time of those files.

#### Scenario: A person asks what the lake holds
- **WHEN** the database is synced and `v_season_catalog` is queried for a source
- **THEN** each held season of each dataset has its row count, file count, byte size, last write time and
  the view name to query, and an older query that selects only the first five columns still works
- Verified by `tests/test_database.py::test_season_catalog_is_the_lake_inventory`.
