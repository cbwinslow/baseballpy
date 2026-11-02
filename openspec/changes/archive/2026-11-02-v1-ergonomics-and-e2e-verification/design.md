# Design: v1-ergonomics-and-e2e-verification

## 1. Automatic DuckDB Catalog Sync (`--sync-db / --no-sync-db`)

### 1.1 Trigger Mechanism
In `src/baseballpy/cli_ingest.py`:
- Add option:
  ```python
  @click.option(
      "--sync-db/--no-sync-db",
      "sync_db",
      default=True,
      help="Automatically update DuckDB views after successful ingestion (default: true).",
  )
  ```
- After `run_jobs(...)` completes, if `sync_db` is True, `report.exit_code == 0`, and at least one job was completed with rows written:
  - Call `sync_database(config=config)`.
  - Print feedback on synced views count.
  - If `--json` is active, include `synced_views` in the summary or output.

## 2. Automated Coverage Remediation (`baseballpy catalog coverage --fix`)

### 2.1 Remediation Execution
In `src/baseballpy/cli_catalog.py`:
- Add `--fix` flag:
  ```python
  @click.option(
      "--fix",
      is_flag=True,
      help="Automatically execute remediation ingest jobs for missing entities.",
  )
  ```
- If `--fix` is passed and any `item.missing_count > 0`:
  - Plan the necessary jobs for the missing entities using the source adapters.
  - Execute the jobs through `run_jobs()`.
  - Re-run `audit_season_coverage()` and display the final coverage state.

## 3. Live End-to-End Test Plan
- Run `uv run baseballpy ingest mlb_api -s 2024 -d schedule_hydrated,teams_season,standings_regular_season`.
- Verify DuckDB view `mlb_schedule_hydrated` exists and query it with `baseballpy db query`.
- Ingest 50 games: `uv run baseballpy ingest mlb_api -s 2024 -d games --limit 50`.
- Run `baseballpy catalog coverage -s 2024`.
- Re-run ingest to verify cache hit (0 network requests, 0.0s elapsed).
