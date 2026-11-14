# audit-and-benchmarking Specification

## Purpose
Defines the telemetry, benchmarking, and audit logging requirements for `baseballpy`, providing structured execution tracking and an interactive CLI inspection tool.

## Requirements

### Requirement: Structured Audit Telemetry
Every public ingestion command, extractor execution, and sink operation MUST record a structured telemetry event into `~/.baseballpy/logs/audit.jsonl` (or configured log path).
- Recorded fields:
  - `timestamp_utc`: ISO 8601 string.
  - `operation`: Name of operation (e.g. `statcast_search`, `chadwick_register_sync`).
  - `source`: Source identifier (`statcast`, `mlb_api`, `chadwick`, `lahman`, `retrosheet`).
  - `status`: One of `SUCCESS`, `FAILURE`, `CANCELLED`, `RETRY`.
  - `records_count`: Integer count of records retrieved or written.
  - `duration_seconds`: Float seconds taken.
  - `throughput_rps`: Float records processed per second.
  - `cache_hit`: Boolean flag.
  - `endpoint`: Upstream URL or query identifier.
  - `destination`: Sink destination or file path.
  - `error`: Null or string error description.

#### Scenario: Successful data extraction logging
- **GIVEN** an extractor completes fetching 10,000 pitch records in 2.5 seconds
- **WHEN** the operation finishes
- **THEN** an entry is appended to `audit.jsonl` with `status="SUCCESS"`, `records_count=10000`, `duration_seconds=2.5`, `throughput_rps=4000.0`.
- Verified by `tests/test_hardening.py::test_audit_success_event_has_records_duration_and_throughput`.

### Requirement: Interactive CLI Reviewer Tool
The system MUST provide a CLI tool under `baseballpy audit` allowing users to inspect telemetry logs:
- `baseballpy audit summary`: Displays formatted table of recent operations with durations, record counts, and status.
- `baseballpy audit tail`: Streams or displays the latest N audit entries.
- `baseballpy audit stats`: Aggregates total records, average throughput, cache hit ratio, and error counts.

#### Scenario: Running audit summary
- **GIVEN** an `audit.jsonl` containing historical operations
- **WHEN** user executes `baseballpy audit summary --limit 10`
- **THEN** a colorized `rich` table prints the last 10 operations with clear visual status flags.
- Verified by `tests/test_audit_filters.py::test_cli_summary_and_tail_accept_the_filters`.

### Requirement: Cancellation Is Not Success
`track`/`async_track` MUST record `CANCELLED` for `CancelledError`/`KeyboardInterrupt` and `FAILURE` for other exceptions, then re-raise.

#### Scenario: Interrupt is recorded as CANCELLED
- **WHEN** a tracked operation is interrupted by `KeyboardInterrupt` or cancelled
- **THEN** the audit event has status `CANCELLED`, never `SUCCESS`, and the exception propagates
- Verified by `tests/test_hardening.py::test_audit_records_cancellation_not_success and ::test_audit_keyboard_interrupt_is_cancelled`.

### Requirement: Cache Hit Accuracy
Every source MUST set `cache_hit` true when no network request was made.

#### Scenario: Cached read is audited as a hit
- **GIVEN** the teams already fetched once
- **WHEN** they are requested again
- **THEN** an `mlb_api_cache_read` audit event has `cache_hit` true
- Verified by `tests/test_sources_hardening.py::test_mlb_cache_hit_is_audited`.

### Requirement: Lazy Logger
The default audit logger MUST be created on first use so `BASEBALLPY_HOME` set after import is honored.

#### Scenario: Home set after import is honored
- **WHEN** `BASEBALLPY_HOME` is set after the package is imported and the default audit logger is first used
- **THEN** events are written under the new home
- Verified by `tests/test_hardening.py::test_default_audit_logger_honors_late_home`.

### Requirement: Real Requests Are Audited and Speeds Are Checked Against the Caps
`HttpClient` MUST write one `http_request` audit event per real network attempt: `started_at_utc` is the moment the request was sent (after the rate limiter and the in-flight gate), `completed_at_utc` its end, `endpoint` the URL without its query string, and `status` `SUCCESS`, `RETRY` (an attempt that raised an error the client retries) or `FAILURE`. `baseballpy audit speed` MUST read those events and the ingest jobs and report, per host, requests, retries, failures, requests per second, requests in flight and latency next to the caps of `RateLimitConfig`, and rows per second per source over the time any of its jobs ran. It MUST exit 1 when more requests started in a window of W seconds than `rate * (W + 1) + 1` (windows of 1, 10 and 60 seconds: the limiter's bucket capacity plus what leaks out), when more requests were in flight than the host's limit, or when a request failed, and it MUST say so when the log holds no `http_request` events.

#### Scenario: A real run passes the check and a broken cap is found
- **GIVEN** 90 requests from six callers through the real client with a rate of 40 per second and 3 in flight
- **THEN** the log holds 90 `http_request` events and `audit speed` finds no problem
- **AND** 60 starts in one second against a cap of 10, 6 requests in flight against a limit of 4, or a failed request each give a problem and exit code 1.
- Verified by `tests/test_audit_speed.py::test_a_real_burst_through_the_real_limiter_stays_inside_the_caps_the_log_is_checked_against`, `tests/test_audit_speed.py::test_the_limiters_own_burst_is_allowed_but_more_is_a_broken_cap`, `tests/test_audit_speed.py::test_more_requests_in_flight_than_the_limit_is_a_problem_but_touching_ones_are_not`, `tests/test_audit_speed.py::test_failures_are_a_problem_and_retries_are_only_counted` and `tests/test_audit_speed.py::test_the_command_exits_zero_when_every_cap_held_and_one_when_not`.

#### Scenario: One event per attempt, without the query string
- **WHEN** a request answers 503 and the retry answers 200
- **THEN** two `http_request` events are logged (`RETRY` with `HTTP 503`, then `SUCCESS`) and neither endpoint holds the query string
- Verified by `tests/test_audit_speed.py::test_the_client_records_one_event_per_real_attempt_with_its_send_time`.

### Requirement: No Value Of The Provider's Text Is Lost Or Changed
`baseballpy verify-roundtrip` MUST compare sampled raw CSV files with the processed rows cell by cell (integers by their
text, floats by value as 64-bit floats, dates by their format, text exactly), report non-empty raw cells stored as NULL,
raw rows missing from the processed data and raw columns no schema column or `_extras` reads, list datasets it cannot
read as skipped with the reason, and exit 1 on any loss; no registered column MAY be a 32-bit float, and a number
written with a leading zero or a plus sign MUST be typed as text.

#### Scenario: Each kind of loss is caught and a clean dataset passes
- **WHEN** a dataset is checked whose stored cells are equal, or whose float is 32-bit, whose integer dropped a leading zero, whose cell became NULL, whose row is missing or whose raw column is unread
- **THEN** the equal dataset is `ok` and each of the others reports its own kind of loss with an example; a dataset with raw files that are not CSV is `skipped`
- Verified by `tests/test_roundtrip.py::test_equal_cells_pass_and_the_extra_column_is_accounted_for`, `tests/test_roundtrip.py::test_a_32_bit_float_is_a_changed_cell`, `tests/test_roundtrip.py::test_a_dropped_leading_zero_is_a_changed_cell`, `tests/test_roundtrip.py::test_a_value_turned_into_null_and_a_missing_row_are_reported`, `tests/test_roundtrip.py::test_a_raw_column_nothing_reads_is_a_loss_unless_extras_holds_it` and `tests/test_roundtrip.py::test_a_dataset_without_csv_raw_files_is_skipped_with_a_reason`.

#### Scenario: Repeated keys and the type rules
- **WHEN** keys repeat in the processed rows, the type guesser sees `01405134`, and the registry is scanned for 32-bit floats
- **THEN** the comparison uses multisets and ignores overlapping windows, the guesser answers text, and no column is a 32-bit float
- Verified by `tests/test_roundtrip.py::test_repeating_keys_are_compared_as_multisets_and_overlapping_windows_are_not_a_loss`, `tests/test_infer_types.py::test_numbers_with_leading_zeros_or_a_plus_sign_are_text` and `tests/test_schema_rules.py::test_no_registered_column_is_a_32_bit_float`.

#### Scenario: Full mode, true/false columns, extras by name, quarantine and counts
- **WHEN** a full check runs on a dataset with an extra processed row, a flipped true/false cell, an unread raw column held in `_extras` under another name, cells that the quarantine explains, and event files whose lines are counted
- **THEN** the extra row is `row_extra`, the flipped cell is a changed cell, the unread column is a loss, the quarantined cells are a known verdict, and a lost or invented event row is found by the count
- Verified by `tests/test_roundtrip.py::test_full_mode_reads_every_file_and_reports_rows_the_raw_text_does_not_have`, `tests/test_roundtrip.py::test_a_true_false_column_is_compared_too`, `tests/test_roundtrip.py::test_extras_must_hold_the_unread_column_by_name`, `tests/test_roundtrip.py::test_cells_that_are_in_the_quarantine_are_a_known_verdict_not_a_loss` and `tests/test_retrosheet_linecounts.py::test_a_lost_or_an_invented_row_is_found_by_the_count`.

#### Scenario: JSON page sources are checked by counting the distinct ids in the raw pages
- **WHEN** the check runs on a Kalshi or Polymarket dataset whose raw files are gzipped JSON pages
- **THEN** the distinct record ids in the raw pages are the rows the table must hold; a missing row is `row_missing`, an invented one `row_extra`, and the verdict says that rows were counted, not cells compared
- Verified by `tests/test_kalshi.py::test_the_round_trip_check_counts_kalshi_pages_and_finds_a_lost_row`, `tests/test_page_counts.py::test_kalshi_candlesticks_count_both_page_shapes_and_a_repeated_candle_once`, `tests/test_page_counts.py::test_polymarket_prices_are_keyed_by_the_request_token_and_the_time` and `tests/test_page_counts.py::test_polymarket_outcomes_come_from_the_outcome_list_of_each_market`.

### Requirement: The Audit Log Tells The Truth And Never Loses A Record
`AuditLogger.track` MUST record an operation whose tracker holds an error as `FAILURE` with that error, even when the code returned instead of raising. A failed write of the audit record MUST NOT replace the error that ended the operation. A rotation that cannot finish compressing MUST leave every record in the active log, in order, and no orphan rotation file.

#### Scenario: Not run, a full disk, and a locked log
- **WHEN** a job records "not run: prerequisite failed" and returns, a rotation hits a full disk while compressing, and the log write fails inside a failing operation
- **THEN** the job is audited as `FAILURE` with its message, the active log still holds every earlier record plus the new ones, and the caller sees the real exception
- Verified by `tests/test_audit_rotate.py::test_an_error_recorded_without_raising_is_audited_as_a_failure`, `tests/test_audit_rotate.py::test_a_rotation_that_cannot_compress_loses_no_audit_record` and `tests/test_audit_rotate.py::test_a_failed_audit_write_does_not_hide_the_error_that_ended_the_operation`.

### Requirement: The Round-Trip Check Reads MLB JSON, Never Writes, And Never Passes What It Did Not Check
`baseballpy verify-roundtrip` MUST check the MLB API datasets cell by cell as it does CSV sources: it recomputes the flattened values from the raw JSON with the ingest's own code (loose raw files and raw response-log segments) and compares each with the stored cell, reporting a rounded float, a dropped zero, a non-empty raw cell stored as NULL, a changed cell, a raw JSON key no column holds, and raw rows missing from the processed data. It MUST be read-only. A dataset where an error stopped the check MUST be reported as `error` and the command MUST exit non-zero (never a silent skip); a game listed by a commit line with no answer in its segment, and rows that name no raw answer, MUST be noted; `--full` MUST be refused above 256 MiB of raw answers (loose and segment files).

#### Scenario: Altered cells, an unreadable answer, a missing game
- **WHEN** a stored float is rounded, a zero is dropped, a value is NULL, a processed segment cell is changed, a raw answer cannot be read, and a listed game has no answer in its segment
- **THEN** each alteration is reported as a loss, the unreadable answer gives the `error` verdict with exit code 1, the missing game is named in a note, and a clean dataset still gives `ok`
- Verified by `tests/test_roundtrip_json.py::test_a_rounded_float_a_dropped_zero_and_a_null_are_reported`, `tests/test_roundtrip_json.py::test_a_changed_cell_in_a_processed_segment_is_reported`, `tests/test_roundtrip_json.py::test_an_error_on_one_answer_is_an_error_verdict_and_a_non_zero_exit`, `tests/test_roundtrip_json.py::test_a_listed_game_with_no_answer_in_its_segment_is_noted` and `tests/test_roundtrip_json.py::test_a_clean_json_answer_round_trips`.
