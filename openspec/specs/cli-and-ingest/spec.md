# cli-and-ingest Specification

## Purpose
One command surface (`baseballpy`) plans and runs ingestion for every source through `IngestAdapter`, reports lake coverage, and exposes query, streaming, quarantine, audit and maintenance tools. Sources never appear in the runner or the CLI by name.

## Requirements

### Requirement: Ingest Planning and Execution
`baseballpy ingest [SOURCES...] --seasons <selection>` MUST plan jobs through each source's `IngestAdapter`, run them with bounded concurrency, collect failures instead of aborting (unless `--stop-on-error`), record one audit event per job, and exit non-zero if any job failed. `--dry-run` MUST plan without any network request or adapter run. A selection is `2023`, `2015-2024`, `2015,2018` or `all`; an empty selection plans only season-less jobs. `--datasets` takes `name` or `source:name`.

#### Scenario: Dry run
- **WHEN** `ingest all --seasons 2023 --dry-run` runs
- **THEN** the planned jobs are printed, zero requests are made and the exit code is 0.

#### Scenario: Resume after interruption
- **GIVEN** a run that was killed after some Statcast chunks were written
- **WHEN** the same command runs again
- **THEN** the finished chunks are not fetched again, the remaining ones are fetched and no `.part` file is left behind.

#### Scenario: Ctrl-C
- **GIVEN** a running `ingest` on a console
- **WHEN** the user presses Ctrl-C
- **THEN** the running job is interrupted promptly (sequential runs) or no new job starts (pool runs), unfinished jobs are reported `cancelled`, the audit event is `CANCELLED` and the exit code is 130.

### Requirement: Coverage Visibility
`baseballpy catalog list|show|status` MUST list every registered dataset with its view, partition, keys and schema, and report per dataset whether it is `INGESTED` or `MISSING` with files, rows, seasons and newest file date, without network access.

### Requirement: Ingest Mode Visibility
Every registered dataset MUST declare how `ingest` reaches it (`default`, `opt_in`, `on_demand` or `api_only`) and, for the last three or for a default dataset the provider publishes only for some seasons, a note saying what to do or why it can be empty. `catalog status` (table and `--json`) and `catalog show` MUST report it, and `catalog status --gaps` MUST list only MISSING datasets whose mode is `default`. The MLB endpoint modes are derived from the endpoint declaration, not from dataset names.

#### Scenario: Gaps are the only unexpected MISSING rows
- **WHEN** a full default `ingest all --seasons 2023` has completed
- **THEN** `catalog status --gaps` lists only datasets whose note says the provider does not publish that season (real run 2026-10-28: `discrepancies`, `events_deduced`, `schedule_original`)

### Requirement: Read-Only Query Access
`baseballpy db views|query|shell` MUST open the DuckDB catalog read-only: a write statement fails inside DuckDB, and a missing database or missing views produces an actionable error pointing to `db sync`.

### Requirement: Live Streaming Persistence
`baseballpy stream GAME_PK` MUST emit each live event once per watermark, support `--replay` to ignore the watermark, and, with `--duckdb`, upsert events on `(game_pk, at_bat_index, event_index)` with a schema derived from `LiveEvent`, so replaying the same game repeatedly leaves the same rows.

### Requirement: Quarantine Inspection
`baseballpy quarantine list|show` MUST list dead-letter files by source, dataset and date and show their records, refusing paths outside the quarantine directory and reporting corrupt lines instead of skipping them.

### Requirement: Audit Filters
`baseballpy audit summary|tail` MUST accept `--source`, `--status` and `--since`, applied before `--limit`.

### Requirement: Explicit Configuration
`get_config()` MUST return a cached `PipelineConfig` that `reset_config()` clears. A dotenv file MUST be read only when `BASEBALLPY_ENV_FILE` names one, and real environment variables MUST win over it; nothing is read implicitly from the working directory.

### Requirement: Generated CLI Reference
`docs/CLI.md` MUST be generated from the click command tree by `baseballpy docs generate`, and `docs generate --check` and the test suite MUST fail when it is stale.
