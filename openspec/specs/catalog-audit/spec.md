# catalog-audit Specification

## Purpose
Checks that the dataset registry is complete against what each provider lists, and that `unsupported` verdicts are re-verified (ADR 35).

## Requirements

### Requirement: Completeness Audit
`baseballpy catalog audit` MUST compare every provider-listed item with the registry and report MISSING, STALE, REVIVED and DRIFT findings with evidence, exiting non-zero on MISSING or REVIVED; every `unsupported` entry MUST record when it was verified and what was tried.

#### Scenario: Revived endpoint
- **GIVEN** a registry entry marked `unsupported` whose route now returns records
- **THEN** the audit reports it as REVIVED with the request that succeeded.
- Verified by `tests/test_audit.py::test_unsupported_leaderboard_that_answers_is_revived, ::test_every_unsupported_entry_records_when_and_what_was_tried and ::test_cli_exit_code_and_json`.

### Requirement: Cross-Source Reference Parity
The catalog audit MUST verify coverage parity against external baseball packages (pybaseball, baseballr, MLB-StatsAPI) and official OpenAPI documentation; any external dataset or endpoint that is not directly ingestible SHALL be documented with an explicit verdict and evidence.

#### Scenario: Cross-source catalog audit validation
- **GIVEN** the master coverage matrix of datasets across pybaseball, baseballr, and MLB-StatsAPI
- **THEN** every external capability maps to a registered dataset, an existing accessor, or a documented unsupported verdict with evidence.
- Verified by `tests/test_coverage_matrix.py::test_master_coverage_matrix_completeness`.

### Requirement: Expected vs Held Coverage Inspection
The catalog audit subsystem MUST provide an expected-vs-held coverage command comparing scheduled games and expected partition entities against held records in the local data lake for any given season.

#### Scenario: Season game coverage report with remediation
- **GIVEN** a data lake with a partially ingested season of games
- **WHEN** `baseballpy catalog coverage --season <year>` is executed
- **THEN** it outputs expected games, held games, completion percentage, and the exact CLI remediation command to backfill missing entities.
- Verified by `tests/test_coverage_audit.py::test_catalog_coverage_season_report`.

