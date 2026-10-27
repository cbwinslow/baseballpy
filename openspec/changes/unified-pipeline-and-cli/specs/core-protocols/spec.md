## ADDED Requirements

### Requirement: Pipeline Composition
The system MUST provide `Pipeline.run(job, extractor, normalizer, sink)` composing a registered extractor, normalizer and sink via protocols only, with freshness skipping, atomic raw/processed writes, manifest checkpointing, quarantine and one audit event per job.

#### Scenario: Resume after interruption
- **GIVEN** `run_many` over 10 jobs cancelled after 4 completed
- **WHEN** re-run
- **THEN** the 4 completed jobs report `SKIPPED_FRESH` and the remaining 6 execute.

#### Scenario: Dry run
- **WHEN** `plan(...)` or `--dry-run` is used
- **THEN** zero HTTP requests are made and each job reports `WOULD_FETCH`, `FRESH` or `ABSENT`.

### Requirement: One-Command Ingest
`baseballpy ingest all --seasons <selection>` MUST ingest every registered dataset in dependency order and exit non-zero if any job fails.

### Requirement: Coverage Visibility
`baseballpy catalog status` MUST list for every registered dataset the upstream-available seasons, ingested seasons, row counts, last fetch time and freshness.

### Requirement: Signature-Level Protocol Conformance
Every registered extractor, normalizer and sink MUST pass signature-level contract tests.
