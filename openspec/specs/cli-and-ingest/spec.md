# cli-and-ingest Specification

## Purpose
One command surface (`baseballpy`) plans and runs ingestion for every source through `IngestAdapter`, reports lake coverage, and exposes query, streaming, quarantine, audit and maintenance tools. Sources never appear in the runner or the CLI by name.

## Requirements

### Requirement: Ingest Planning and Execution
`baseballpy ingest [SOURCES...] --seasons <selection>` MUST plan jobs through each source's `IngestAdapter`, run them with bounded concurrency (automatically scaling worker threads to available CPU cores and planned job count when `--concurrency` is omitted or set to `auto`, or using explicit integer values), collect failures instead of aborting (unless `--stop-on-error`), record one audit event per job, and exit non-zero if any job failed. `--dry-run` MUST plan without any network request or adapter run. A selection is `2023`, `2015-2024`, `2015,2018` or `all`; an empty selection plans only season-less jobs. `--datasets` takes `name` or `source:name`.

#### Scenario: Dry run
- **WHEN** `ingest all --seasons 2023 --dry-run` runs
- **THEN** the planned jobs are printed, zero requests are made and the exit code is 0.
- Verified by `tests/test_cli_ingest.py::test_dry_run_makes_zero_run_calls`.

#### Scenario: Resume after interruption
- **GIVEN** a run that was killed after some Statcast chunks were written
- **WHEN** the same command runs again
- **THEN** the finished chunks are not fetched again, the remaining ones are fetched and no `.part` file is left behind.
- Verified by `tests/test_statcast_pitches.py::test_ingest_season_is_resumable_and_checks_pitch_keys` and `tests/test_retrosheet_coverage.py::test_ingest_all_resumes_after_an_interruption` and `tests/test_hardening.py::test_cleanup_stale_parts`.

#### Scenario: Ctrl-C
- **GIVEN** a running `ingest` on a console
- **WHEN** the user presses Ctrl-C
- **THEN** the running job is interrupted promptly (sequential runs) or no new job starts (pool runs), unfinished jobs are reported `cancelled`, the audit event is `CANCELLED` and the exit code is 130.
- Verified by `tests/test_ingest_runner.py::test_run_jobs_keyboard_interrupt_marks_cancelled and ::test_run_jobs_pool_interrupt_returns_while_a_job_is_still_running` and `tests/test_hardening.py::test_audit_keyboard_interrupt_is_cancelled`.

#### Scenario: Auto concurrency resolves dynamically
- **GIVEN** a planned list of ingestion jobs
- **WHEN** `baseballpy ingest` runs without an explicit `--concurrency` argument
- **THEN** worker thread concurrency is automatically resolved based on available CPU cores and job count, bounded by safe limits.
- Verified by `tests/test_auto_concurrency.py::test_resolve_concurrency_auto_scaling`.

### Requirement: Coverage Visibility
`baseballpy catalog list|show|status` MUST list every registered dataset with its view, partition, keys and schema, and report per dataset whether it is `INGESTED` or `MISSING` with files, rows, seasons and newest file date, without network access.

#### Scenario: Fabricated Parquet is reported INGESTED
- **GIVEN** Parquet written under a dataset's processed directory
- **WHEN** `catalog show` or `catalog status` runs
- **THEN** the dataset is `INGESTED` with its rows, files and seasons, and untouched datasets are `MISSING`, with no network access
- Verified by `tests/test_cli_ingest.py::test_scan_lake_and_catalog_status_fabricated_parquet and tests/test_cli_catalog.py::test_catalog_show_fabricated_parquet_reports_ingested`.

### Requirement: Ingest Mode Visibility
Every registered dataset MUST declare how `ingest` reaches it (`default`, `opt_in`, `on_demand` or `api_only`) and, for the last three or for a default dataset the provider publishes only for some seasons, a note saying what to do or why it can be empty. `catalog status` (table and `--json`) and `catalog show` MUST report it, and `catalog status --gaps` MUST list only MISSING datasets whose mode is `default`. The MLB endpoint modes are derived from the endpoint declaration, not from dataset names.

#### Scenario: Gaps are the only unexpected MISSING rows
- **WHEN** a full default `ingest all --seasons 2023` has completed
- **THEN** `catalog status --gaps` lists only datasets whose note says the provider does not publish that season (real run 2026-10-28: `discrepancies`, `events_deduced`, `schedule_original`)
- Verified by `tests/test_cli_ingest.py::test_catalog_status_gaps_only_lists_default_datasets and ::test_catalog_status_gaps_shrinks_when_a_default_dataset_is_ingested`.

### Requirement: Read-Only Query Access
`baseballpy db views|query|shell` MUST open the DuckDB catalog read-only: a write statement fails inside DuckDB, and a missing database or missing views produces an actionable error pointing to `db sync`.

#### Scenario: Writes fail and a missing database is actionable
- **WHEN** `db query` is given a write statement
- **THEN** DuckDB rejects it; and when the database or views are missing the error points to `db sync`
- Verified by `tests/test_cli_db.py::test_db_query_write_fails and ::test_db_missing_gives_click_exception`.

### Requirement: Live Streaming Persistence
`baseballpy stream GAME_PK` MUST emit each live event once per watermark, support `--replay` to ignore the watermark, and, with `--duckdb`, upsert events on `(game_pk, at_bat_index, event_index)` with a schema derived from `LiveEvent`, so replaying the same game repeatedly leaves the same rows.

#### Scenario: Replaying a game upserts the same rows
- **WHEN** `stream GAME_PK --replay --duckdb` runs repeatedly on the same events
- **THEN** the row count and keys are unchanged
- Verified by `tests/test_cli_stream.py::test_stream_duckdb_upsert_idempotent`.

### Requirement: Quarantine Inspection
`baseballpy quarantine list|show` MUST list dead-letter files by source, dataset and date and show their records, refusing paths outside the quarantine directory and reporting corrupt lines instead of skipping them.

#### Scenario: Outside paths are refused and corrupt lines reported
- **WHEN** `quarantine show` is given a path outside the quarantine directory
- **THEN** it exits with code 2; and a corrupt JSON line is reported with its line number instead of skipped
- Verified by `tests/test_cli_quarantine.py::test_quarantine_show_refuses_outside_path and ::test_quarantine_show_corrupt_line_reported`.

### Requirement: Audit Filters
`baseballpy audit summary|tail` MUST accept `--source`, `--status` and `--since`, applied before `--limit`.

#### Scenario: Filters apply before the limit
- **WHEN** `audit summary --source X --limit N` runs
- **THEN** the N newest events of source X are shown, not the matches among the N newest
- Verified by `tests/test_audit_filters.py::test_filters_apply_before_limit`.

### Requirement: Explicit Configuration
`get_config()` MUST return a cached `PipelineConfig` that `reset_config()` clears. A dotenv file MUST be read only when `BASEBALLPY_ENV_FILE` names one, and real environment variables MUST win over it; nothing is read implicitly from the working directory.

#### Scenario: Dotenv only when named, environment wins
- **WHEN** a `.env` sits in the working directory and `BASEBALLPY_ENV_FILE` is unset
- **THEN** it is not read; with the variable set it is read and a real environment variable still wins; `reset_config()` rereads the environment
- Verified by `tests/test_config.py::test_dotenv_in_cwd_is_not_read_implicitly, ::test_env_file_var_opts_in_and_real_env_wins and ::test_reset_config_rereads_the_environment`.

### Requirement: Generated CLI Reference
`docs/CLI.md` MUST be generated from the click command tree by `baseballpy docs generate`, and `docs generate --check` and the test suite MUST fail when it is stale.

#### Scenario: Stale CLI reference fails
- **WHEN** `docs/CLI.md` differs from the click help
- **THEN** `docs generate --check` and the test suite fail
- Verified by `tests/test_clidocs.py::test_committed_cli_doc_is_not_stale`.

### Requirement: Automatic Database Sync After Ingestion
`baseballpy ingest` MUST automatically sync the DuckDB view catalog upon successful completion of one or more jobs (defaulting `--sync-db` to True, with `--no-sync-db` to opt out), creating or updating zero-copy views for all processed Parquet files.

#### Scenario: Successful ingest creates views automatically
- **GIVEN** an ingestion run that writes processed Parquet files
- **WHEN** `baseballpy ingest` completes with at least one completed job
- **THEN** DuckDB views are automatically synced and queryable immediately without requiring a manual `db sync` invocation.
- Verified by `tests/test_cli_ingest.py::test_ingest_auto_syncs_database`.

### Requirement: Job Prerequisites
A planned job MAY name the jobs that must finish before it starts (`Job.needs`, job ids; ids not in the plan are ignored because the data is then read from the lake as it is). The runner MUST start such a job only after those jobs finished, in the sequential and the pooled path, and MUST keep the results in planned order. A job whose prerequisite failed or was cancelled MUST be reported `failed` with the prerequisite named, without running, and one audit event MUST still be written for it. Jobs that wait for each other MUST be rejected before anything runs. The MLB adapter MUST declare these prerequisites from the endpoint registry (`prerequisites(endpoint)`), never from a hard-coded name list, and an endpoint whose fan-out values are not in the lake MUST log a warning that nothing was requested.

#### Scenario: A dependent job waits even with many workers
- **GIVEN** a roster job planned before the teams job it needs, and four workers
- **WHEN** the plan runs
- **THEN** the teams job runs first, the roster job second, and the results keep the planned order.
- Verified by `tests/test_request_parallelism.py::test_a_dependent_job_waits_for_its_prerequisite_even_with_many_workers`.

#### Scenario: A failed prerequisite fails its dependents visibly
- **GIVEN** a teams job that raises and a roster job that needs it
- **WHEN** the plan runs sequentially or on a pool
- **THEN** the roster job is `failed` with the prerequisite named and was not run.
- Verified by `tests/test_request_parallelism.py::test_a_dependent_of_a_failed_job_fails_visibly_without_running`.

#### Scenario: A cycle is rejected
- **WHEN** two jobs need each other
- **THEN** `ValueError` naming the cycle is raised and no job ran.
- Verified by `tests/test_request_parallelism.py::test_jobs_that_wait_for_each_other_are_rejected_before_anything_runs`.

#### Scenario: Independent jobs run in parallel
- **GIVEN** six independent jobs and three workers
- **WHEN** they run
- **THEN** three are in flight at once.
- Verified by `tests/test_request_parallelism.py::test_independent_jobs_do_run_in_parallel`.

#### Scenario: The MLB planner orders a fan-out endpoint after its teams
- **GIVEN** `--datasets team_roster_active teams_season` for 2024
- **WHEN** the adapter plans
- **THEN** the roster job needs the `teams_season` job, and needs nothing when `teams_season` is not planned.
- Verified by `tests/test_request_parallelism.py::test_the_planner_orders_a_fan_out_endpoint_after_its_teams` and `::test_prerequisites_come_from_the_scope_and_the_placeholders`.

#### Scenario: An empty fan-out is not a silent success
- **WHEN** a team-scoped endpoint runs and no teams are in the lake
- **THEN** a warning names the missing prerequisite dataset.
- Verified by `tests/test_request_parallelism.py::test_an_empty_fan_out_is_warned_about_not_silently_completed`.

### Requirement: The CLI States the Network Limit
`baseballpy ingest` MUST print the number of job workers and the per-host in-flight limit that applies to the network, because `--concurrency` sizes only the job workers.

#### Scenario: Workers and limit are shown
- **WHEN** `ingest -c 3` runs with `BASEBALLPY_RATE_MAX_CONCURRENCY=6`
- **THEN** the output says 3 parallel workers and up to 6 requests in flight per host.
- Verified by `tests/test_cli_ingest.py::test_the_cli_states_the_workers_and_the_real_network_limit`.

### Requirement: Seasons Exist Once Their First Day Has Arrived
`all_seasons()` of the Statcast and MLB Stats API adapters MUST end at the newest season whose first day (spring training, else opening day, from the MLB `/v1/seasons/all` calendar) is on or before the lake clock, and a job for a season that has not started MUST be reported as `skipped` with the reason and never reach the provider code, so the weeks between New Year and spring training plan and run without errors. Seasons before the current year MUST NOT need the calendar, the calendar MUST be cached for twelve hours, and a calendar that cannot be read MUST raise instead of guessing.

#### Scenario: January plans the last season and skips the new one
- **GIVEN** a lake clock of 15 January 2027 and a calendar that lists 2027 starting on 19 February
- **THEN** `all_seasons()` ends at 2026, a 2027 job of either adapter is `skipped` with "has not started", and on 19 February 2027 the season counts
- **AND** a calendar that answers HTTP 500 raises.
- Verified by `tests/test_season_calendar.py::test_statcast_adapter_plans_to_last_season_and_skips_a_new_one_in_january`, `tests/test_season_calendar.py::test_mlb_adapter_plans_to_last_season_and_skips_a_new_one_in_january`, `tests/test_season_calendar.py::test_in_january_the_new_season_has_not_started_and_the_last_one_is_the_latest`, `tests/test_season_calendar.py::test_once_spring_training_begins_the_new_season_counts` and `tests/test_season_calendar.py::test_a_calendar_that_cannot_be_read_fails_loudly_not_silently`.
