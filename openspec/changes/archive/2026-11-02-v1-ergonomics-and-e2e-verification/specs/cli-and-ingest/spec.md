## ADDED Requirements

### Requirement: Automatic Database Sync After Ingestion
`baseballpy ingest` MUST automatically sync the DuckDB view catalog upon successful completion of one or more jobs (defaulting `--sync-db` to True, with `--no-sync-db` to opt out), creating or updating zero-copy views for all processed Parquet files.

#### Scenario: Successful ingest creates views automatically
- **GIVEN** an ingestion run that writes processed Parquet files
- **WHEN** `baseballpy ingest` completes with at least one completed job
- **THEN** DuckDB views are automatically synced and queryable immediately without requiring a manual `db sync` invocation.
- Verified by `tests/test_cli_ingest.py::test_ingest_auto_syncs_database`.
