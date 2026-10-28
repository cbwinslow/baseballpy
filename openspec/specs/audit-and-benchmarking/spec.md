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

### Requirement: Interactive CLI Reviewer Tool
The system MUST provide a CLI tool under `baseballpy audit` allowing users to inspect telemetry logs:
- `baseballpy audit summary`: Displays formatted table of recent operations with durations, record counts, and status.
- `baseballpy audit tail`: Streams or displays the latest N audit entries.
- `baseballpy audit stats`: Aggregates total records, average throughput, cache hit ratio, and error counts.

#### Scenario: Running audit summary
- **GIVEN** an `audit.jsonl` containing historical operations
- **WHEN** user executes `baseballpy audit summary --limit 10`
- **THEN** a colorized `rich` table prints the last 10 operations with clear visual status flags.

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
