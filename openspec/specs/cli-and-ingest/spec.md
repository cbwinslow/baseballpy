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

### Requirement: Season Selections Are Validated
A season selection (`2023`, `2015-2024`, `2015,2018`, `all`) MUST resolve to a sorted tuple of unique years between 1800 and 2100, and any other text (empty, non-numeric, reversed range, malformed range, out of range, `all` without a source of seasons) MUST raise a `ValueError` that names the bad text.

#### Scenario: Bad selections are refused
- **WHEN** a selection is empty, reversed, malformed, non-numeric or outside 1800..2100
- **THEN** a `ValueError` is raised and nothing is planned.
- Verified by `tests/test_ingest_selection.py::test_parse_reversed_range_raises` and `tests/test_ingest_selection.py::test_parse_out_of_bounds_raises` and `tests/test_ingest_selection.py::test_parse_malformed_syntax_raises`.

#### Scenario: Good selections resolve in order
- **WHEN** a selection mixes ranges, single years and duplicates
- **THEN** the years come back sorted and unique.
- Verified by `tests/test_ingest_selection.py::test_parse_sorting_and_deduplication`.

### Requirement: One Fast Overview, One Update Command
`baseballpy status` MUST show per source the datasets held out of those registered, the rows, the seasons, the newest date and the default datasets still empty, plus free disk space, the hosts a process is downloading from, and the counts of quarantine and leftover `.part` files, by reading manifests only and without creating any folder. `catalog status` MUST read manifests too and MUST count Parquet footers only with `--verify`. `baseballpy update` MUST run the built-in `daily` plan and `baseballpy backfill NAME` MUST accept a built-in plan name (`daily`, `full`) as well as a file, a file winning over a name. A season expression MUST accept `current` alone, in a list and as the end of a range.

#### Scenario: Overview, scan, plans and seasons
- **WHEN** manifests are written for two sources, the lake is scanned with and without verification, status is run as text and JSON, a host is claimed and released, built-in plans are loaded and dry-run, and `current` is parsed
- **THEN** the overview sums the manifests, the fast scan creates no folder, verification can disagree with a wrong manifest, the busy host is named and the lock is free again afterwards, the plans load and plan their jobs, a plan file beats a built-in name, an unknown name lists the built-in ones, and `current` is this year
- Verified by `tests/test_workflows.py::test_the_scan_reads_manifests_and_never_opens_a_parquet_file_or_makes_a_folder`, `tests/test_workflows.py::test_verify_counts_the_files_and_catches_a_manifest_that_is_wrong`, `tests/test_workflows.py::test_status_summarizes_each_source_and_says_nothing_runs`, `tests/test_workflows.py::test_busy_hosts_sees_a_claim_and_looking_does_not_take_the_lock`, `tests/test_workflows.py::test_the_built_in_plans_load_and_their_names_are_listed`, `tests/test_workflows.py::test_a_plan_file_still_wins_over_a_built_in_name`, `tests/test_workflows.py::test_backfill_and_update_dry_runs_use_the_built_in_daily_plan` and `tests/test_workflows.py::test_current_means_this_calendar_year_alone_in_a_list_and_in_a_range`.

### Requirement: Blank And NaN Cells Are Values, Not Errors
When a cell is built into a typed column, a blank text cell in a non-text column MUST become NULL and the text `NaN`, `Infinity` or `-Infinity` in a float column MUST become that float, neither being quarantined; a value that still does not fit MUST be set to NULL and quarantined.

#### Scenario: Blank, NaN and wrong values
- **WHEN** blanks and `NaN` text are built into integer and float columns, and a text value is built into an integer column
- **THEN** blanks are NULL, `NaN` and infinities are floats, nothing is quarantined for them, and the wrong text is NULL and quarantined once
- Verified by `tests/test_workflows.py::test_a_blank_cell_is_missing_and_nan_text_is_a_float_and_neither_is_quarantined` and `tests/test_workflows.py::test_a_value_that_is_really_wrong_is_still_quarantined`.

### Requirement: Coverage Expects Only What A Plain Ingest Fills
The season-dataset coverage audit MUST count only default-mode datasets as expected, because opt-in, on-demand and API-only datasets need an option or an input, and MUST say in its note how many it left out.

#### Scenario: Default datasets only
- **WHEN** the coverage of a source with opt-in datasets is audited on an empty lake
- **THEN** the expected count is the number of default season datasets and the note names the number left out
- Verified by `tests/test_workflows.py::test_coverage_expects_only_the_datasets_a_plain_ingest_fills`.

### Requirement: Unknown Dataset Errors Explain Groups
When `ingest -d` names a dataset the source does not plan by that name, the usage error MUST list the names it knows and MUST say that registry names missing from the list are fetched together as part of a group.

#### Scenario: A leaderboard asked for alone
- **WHEN** `ingest statcast -d leaderboard_sprint_speed` is run
- **THEN** it exits with a usage error that names the group `leaderboards`
- Verified by `tests/test_workflows.py::test_an_unknown_dataset_error_explains_that_some_names_belong_to_a_group`.

### Requirement: A Plan Can Be Run One Stage At A Time
`baseballpy backfill PLAN --stage X` (repeatable) MUST run only the stages named by `X`, a stage name or its 1-based number, in plan order, and MUST refuse an unknown stage before anything runs.

#### Scenario: Choosing stages
- **WHEN** a plan with three stages is run with `--stage` naming the second by name and the third by number, and with an unknown name
- **THEN** only those two stages are planned, in plan order, and the unknown name is refused with the list of stages
- Verified by `tests/test_queue.py::test_select_stages_by_name_and_number` and `tests/test_queue.py::test_select_stages_refuses_an_unknown_stage`.

### Requirement: A Python Supervisor Keeps A Plan Running
`baseballpy run PLAN` MUST run each stage of the plan in its own child process, retry a failed stage with exponential backoff and jitter up to `--retries` times, continue with the next stage when one is out of retries, and record the round, each stage's status, attempts and last error in a state file under the lake home. It MUST NOT retry a stage that stopped because of a disk or size limit. With `--every` it MUST start a new round after that interval and keep going until stopped; without it, it MUST end when the plan is done. It MUST depend on no operating-system scheduler.

#### Scenario: Retries, order and rounds
- **WHEN** a stage fails twice and then succeeds, another fails every time, and a third follows
- **THEN** the first stage is tried three times, the second is marked failed after its retries, the third still runs, and the exit code is 1
- Verified by `tests/test_queue.py::test_a_failed_stage_is_retried_and_does_not_block_the_next` and `tests/test_queue.py::test_a_stage_stopped_by_a_limit_is_not_retried`.

#### Scenario: Repeating and stopping
- **WHEN** the queue runs with an interval and the stop event is set during the wait
- **THEN** a second round runs after the interval, and the queue ends with exit code 130 without starting another
- Verified by `tests/test_queue.py::test_every_starts_new_rounds_until_stopped`.

### Requirement: A Restarted Supervisor Resumes The Unfinished Round
The supervisor MUST keep its state in an atomically written file and, when started again for the same plan with a round unfinished, MUST skip the stages already done in that round. Only one supervisor MUST run per lake home.

#### Scenario: Resume and single instance
- **WHEN** the queue is stopped after its first stage and started again, and a second supervisor is started while one runs
- **THEN** the first stage is not run again, and the second supervisor is refused with a clear message
- Verified by `tests/test_queue.py::test_a_restart_skips_the_stages_already_done` and `tests/test_queue.py::test_only_one_supervisor_runs_per_home`.

#### Scenario: Child process
- **WHEN** a stage is run by the child-process runner
- **THEN** it starts the current Python (`sys.executable`) with the `backfill` command and `--stage`, maps its exit code, and terminates the child when the stop event is set
- Verified by `tests/test_queue.py::test_the_child_runner_uses_the_current_python_and_stops_the_child`.

### Requirement: A Stage Whose After-Step Failed Is Not Done
When the after-step of a finished stage (compaction) exits with a non-zero code, the supervisor MUST mark the
stage `failed` with the error recorded, MUST include it in the failed stages of the round (so the exit code
is 1 and `status` shows it), and MUST run it again like any failed stage. A stage is `done` only when its
download and its after-step both succeeded.

#### Scenario: A failed compaction is retried and reported
- **WHEN** a stage downloads fine but its after-step fails once and then succeeds, with an interval set
- **THEN** the stage is failed and the round's exit code is 1 after the first pass, it runs again in the same
  round, and it ends done
- Verified by `tests/test_queue.py::test_a_failed_after_step_fails_the_stage_and_it_runs_again`.

#### Scenario: The last stage's after-step counts
- **WHEN** the last stage of a round has a failing after-step
- **THEN** the report lists that stage as failed
- Verified by `tests/test_queue.py::test_the_last_stages_after_step_is_settled_before_the_report`.
