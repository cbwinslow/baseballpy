# Proposal: v1-ergonomics-and-e2e-verification

## Problem Statement
Users ingesting baseball data want an intuitive, end-to-end experience:
1. **Manual DB Sync Friction:** After running `baseballpy ingest`, newly ingested Parquet files are not immediately visible in DuckDB queries until the user manually invokes `baseballpy db sync`. This creates unnecessary friction for analysts and models wanting to immediately run `baseballpy db query` or `baseballpy db shell`.
2. **Coverage Remediation Gap:** `baseballpy catalog coverage` reports expected vs. held entities and displays a remediation command, but requires users to manually copy and run the CLI command.
3. **End-to-End Live Verification:** We need a live end-to-end execution on this machine to verify ingestion, caching, multi-threading, automatic DuckDB synchronization, and coverage auditing in real practice.

## Proposed Solution
1. **Auto-Sync DuckDB Catalog on Ingest:** Add `--sync-db / --no-sync-db` (default `True`) to `baseballpy ingest`. When any ingest job writes data, `sync_database()` runs automatically and prints the count of refreshed views.
2. **One-Click Remediation (`catalog coverage --fix`):** Add `--fix` to `baseballpy catalog coverage`. When `--fix` is passed and gaps exist, the coverage engine directly executes the required remediation jobs.
3. **Live End-to-End Verification:** Ingest a 2024 MLB sample on this machine (standings + schedule + sample games), query the auto-created DuckDB view via SQL, run `catalog coverage`, and verify idempotency and speed.

## Scope
- `src/baseballpy/cli_ingest.py`: Add `--sync-db / --no-sync-db` option (default True) and auto-sync trigger.
- `src/baseballpy/coverage.py` & `src/baseballpy/cli_catalog.py`: Add `--fix` flag to execute remediation jobs for missing entities.
- `tests/test_coverage_audit.py` & `tests/test_cli_ingest.py`: Unit and integration tests.
- Live verification on 2024 MLB data.
