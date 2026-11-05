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
