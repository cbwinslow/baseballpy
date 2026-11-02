## ADDED Requirements

### Requirement: Automated Coverage Remediation
When `baseballpy catalog coverage` is run with `--fix`, the command MUST plan and execute the remediation jobs for all missing entities across target sources and seasons, and report the resulting updated coverage.

#### Scenario: Auto-remediation executes missing jobs
- **GIVEN** a season with missing game entities
- **WHEN** `baseballpy catalog coverage --season 2024 --fix` is invoked
- **THEN** it triggers ingestion jobs for the missing entities and updates the held count.
- Verified by `tests/test_coverage_audit.py::test_catalog_coverage_fix_flag`.
