# Proposal: mlb_api-source-review

## Why
Track 5 of the source-by-source review (owner request 2026-10-29). MLB API is reviewed with the
same seven stages and standing standards as Chadwick: complete inventory, registry conformance, schema
against real data, code against the designated tools, the shared currency check (ADR 43), full Python
access, tests and spec, a clean live run, the export checklist (ADR 46), cited column descriptions and
documentation. Starting facts and suspected findings are in design.md.

## What changes
The standard tasks in tasks.md (cards in `docs/agents/tracks/05-mlb_api.md`): look-only review tasks 1.x, the
standard fixes 5.1 to 5.5, one more task `5.n` for each finding of the review, then tests, verification and close. Code changes happen only under a numbered task.

## Out of scope
Other sources; the export command itself (built, ADR 46); changes to how the provider is reached beyond
what a finding requires.

## Impact
`src/baseballpy/sources/mlb_api/`, `docs/sources/mlb_api.md`, the `mlb-api-ingestion` spec, `docs/columns/mlb_api.json`.

## As built (2026-10-30)
Findings 5.1-5.14: raw fingerprints, schema-following tables, no hard-coded default season (and standings honour refresh), a Python `table()` entry point, a refused request no longer aborts a season run, keys proven unique on real rows (9 datasets) with the rest documented, registry-name `--datasets`, empty text is NULL (parser revision 1), the unsupported team expectedStatistics route recorded with evidence, the league-wide pools survive the provider's 406 through people hydrate (ADR 53), and `baseballpy probe`. Not verified: a full default-season rerun after the fixes, the minor-league sports through the fallback, the all-time pools (blocked by the 406). Column descriptions cover 56% (no published definitions for the rest).
