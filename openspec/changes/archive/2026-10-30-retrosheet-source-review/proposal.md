# Proposal: retrosheet-source-review

## Why
Track 3 of the source-by-source review (owner request 2026-10-29). Retrosheet is reviewed with the
same seven stages and standing standards as Chadwick: complete inventory, registry conformance, schema
against real data, code against the designated tools, the shared currency check (ADR 43), full Python
access, tests and spec, a clean live run, the export checklist (ADR 46), cited column descriptions and
documentation. Starting facts and suspected findings are in design.md.

## What changes
The standard tasks in tasks.md (cards in `docs/agents/tracks/03-retrosheet.md`): look-only review tasks 1.x, the
standard fixes 5.1 to 5.5, one more task `5.n` for each finding of the review, then tests, verification and close. Code changes happen only under a numbered task.

## Out of scope
Other sources; the export command itself (built, ADR 46); changes to how the provider is reached beyond
what a finding requires.

## Impact
`src/baseballpy/sources/retrosheet/`, `docs/sources/retrosheet.md`, the `retrosheet-ingestion` spec, `docs/columns/retrosheet.json`.

## As built (2026-10-30)
All 19 fix tasks (5.1-5.19), the verification (3.1-3.4) and the close (4.1) are done. Differences from the plan: the review found four non-unique keys and one wrong value convention that only a real-data run could show (5.16-5.19); the processed tier now carries a schema digest and an optional dataset `revision` (ADR 49, 51); `box_records` is refused as CSV and PostgreSQL stores its list column as JSON; column descriptions cover 994 of 1,262 columns (the rest need retrosheet.org documents, B-18). dlt was evaluated as the processed-tier writer and rejected (ADR 50).
