## ADDED Requirements

### Requirement: Expected vs Held Coverage Inspection
The catalog audit subsystem MUST provide an expected-vs-held coverage command comparing scheduled games and expected partition entities against held records in the local data lake for any given season.

#### Scenario: Season game coverage report with remediation
- **GIVEN** a data lake with a partially ingested season of games
- **WHEN** `baseballpy catalog coverage --season <year>` is executed
- **THEN** it outputs expected games, held games, completion percentage, and the exact CLI remediation command to backfill missing entities.
- Verified by `tests/test_coverage_audit.py::test_catalog_coverage_season_report`.
