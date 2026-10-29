# Proposal: lahman-source-review

## Why
Track 2 of the source-by-source review (owner request 2026-10-29). Lahman is reviewed with the
same seven stages and standing standards as Chadwick: complete inventory, registry conformance, schema
against real data, code against the designated tools, the shared currency check (ADR 43), full Python
access, tests and spec, a clean live run, the export checklist (ADR 46), cited column descriptions and
documentation. Starting facts and suspected findings are in design.md.

## What changes
The standard tasks in tasks.md (cards in `docs/agents/tracks/02-lahman.md`), plus a task `5.n` for each
finding of the review. Code changes happen only under a numbered task.

## Out of scope
Other sources; the export command itself (built, ADR 46); changes to how the provider is reached beyond
what a finding requires.

## Impact
`src/baseballpy/sources/lahman/`, `docs/sources/lahman.md`, the `lahman-database` spec, `docs/columns/lahman.json`.
