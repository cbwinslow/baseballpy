## ADDED Requirements

### Requirement: Completeness Audit
`baseballpy catalog audit` MUST compare every provider-listed item with the registry and report MISSING, STALE, REVIVED and DRIFT findings with evidence, exiting non-zero on MISSING or REVIVED; every `unsupported` entry MUST record when it was verified and what was tried.

#### Scenario: Revived endpoint
- **GIVEN** a registry entry marked `unsupported` whose route now returns records
- **THEN** the audit reports it as REVIVED with the request that succeeded.
