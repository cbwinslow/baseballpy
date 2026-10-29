## ADDED Requirements

### Requirement: Upstream Fingerprints
Every raw file MUST record, with its sha256, the provider's fingerprint of the downloaded version when the provider offers one (git blob or commit SHA, ETag, Last-Modified), in its manifest entry.

#### Scenario: Fingerprints are recorded with the hash
- **WHEN** a raw file is stored with an upstream fingerprint, or with only an ETag
- **THEN** the manifest entry has the sha256 and the fingerprint (the ETag becomes an ETag fingerprint)
- Verified by `tests/test_upstream.py::test_raw_store_records_the_upstream_fingerprint_with_the_sha256`.

#### Scenario: Git sources store the file's blob fingerprint
- **WHEN** the Chadwick register is downloaded from a git tree
- **THEN** each file's entry holds its git blob SHA and origin, and the commit chunk holds the commit
- Verified by `tests/test_chadwick_coverage.py::test_downloaded_files_record_their_git_blob_fingerprint`.

### Requirement: One Currency Rule
Whether a cached copy can be served MUST be decided by one shared function: not current on refresh or an unfinished entry; an expected upstream fingerprint decides alone; otherwise the copy is current within its time-to-live (past seasons never expire); after that upstream is asked once and a matching answer is current, a different one is stale, and no answer serves the copy with a warning.

#### Scenario: Expected fingerprint decides without a timer
- **GIVEN** a stored fingerprint and an expected one
- **WHEN** they match or differ, however old the copy is
- **THEN** the copy is current exactly when they match
- Verified by `tests/test_upstream.py::test_expected_fingerprint_decides_without_any_time_to_live`.

#### Scenario: A fresh copy costs no request and an expired one asks once
- **WHEN** the copy is within its time-to-live, and when it is not
- **THEN** no probe runs in the first case; in the second a matching probe is current (and renews the timestamp), a different one is stale, and an unreachable upstream serves the copy with a warning
- Verified by `tests/test_upstream.py::test_time_to_live_serves_fresh_copies_without_asking_upstream`, `tests/test_upstream.py::test_expired_copy_asks_upstream_and_compares` and `tests/test_upstream.py::test_unreachable_upstream_serves_the_copy_and_says_so`.

### Requirement: Cache Check Command
`baseballpy cache check` MUST verify every raw file against its recorded sha256 and exit 1 when one is missing or corrupt; with `--upstream` it MUST compare the stored git fingerprints with the latest tree of each repository (one tree per repository) and report changed, removed and unfingerprinted files without failing.

#### Scenario: Integrity and exit code
- **WHEN** a raw file is tampered with or deleted
- **THEN** it is reported corrupt or missing and the command exits 1; a clean lake exits 0
- Verified by `tests/test_cache_check.py::test_integrity_finds_corrupt_and_missing_files` and `tests/test_cache_check.py::test_cli_exit_codes_and_output`.

#### Scenario: Upstream comparison
- **WHEN** `--upstream` runs against a latest tree where some files changed or were removed
- **THEN** each file is reported current, changed, removed or without fingerprint, with one tree lookup per repository, and an unreachable repository is reported and not raised
- Verified by `tests/test_cache_check.py::test_upstream_comparison_reports_current_changed_removed_and_unfingerprinted` and `tests/test_cache_check.py::test_unreachable_upstream_is_reported_not_raised`.

### Requirement: Cached Jobs Are Logged As Cache Hits
An ingest job that served everything from the cache MUST be recorded in the audit log with `cache_hit` true.

#### Scenario: Cached rerun
- **WHEN** a job reports `cache_hit` and the runner records it
- **THEN** the audit event has `cache_hit` true
- Verified by `tests/test_ingest_runner.py::test_a_job_that_served_everything_from_the_cache_logs_a_cache_hit` and `tests/test_ingest_adapters.py::test_chadwick_adapter`.
