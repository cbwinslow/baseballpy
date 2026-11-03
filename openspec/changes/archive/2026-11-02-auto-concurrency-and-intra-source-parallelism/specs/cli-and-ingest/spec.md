## MODIFIED Requirements

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
