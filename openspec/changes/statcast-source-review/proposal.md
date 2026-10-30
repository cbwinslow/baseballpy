# Proposal: statcast-source-review

## Why
Track 4 of the source-by-source review (owner request 2026-10-29). Statcast is reviewed with the
same seven stages and standing standards as Chadwick: complete inventory, registry conformance, schema
against real data, code against the designated tools, the shared currency check (ADR 43), full Python
access, tests and spec, a clean live run, the export checklist (ADR 46), cited column descriptions and
documentation. Starting facts and suspected findings are in design.md.

## What changes
The standard tasks in tasks.md (cards in `docs/agents/tracks/04-statcast.md`): look-only review tasks 1.x, the
standard fixes 5.1 to 5.5, one more task `5.n` for each finding of the review, then tests, verification and close. Code changes happen only under a numbered task.

## Out of scope
Other sources; the export command itself (built, ADR 46); changes to how the provider is reached beyond
what a finding requires.

## Impact
`src/baseballpy/sources/statcast/`, `docs/sources/statcast.md`, the `statcast-ingestion` spec, `docs/columns/statcast.json`.
