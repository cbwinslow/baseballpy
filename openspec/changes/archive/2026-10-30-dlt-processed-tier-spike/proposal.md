# Proposal: dlt-processed-tier-spike

## Why
The owner asked (2026-10-30) whether dlt, the project's designated load tool (`docs/agents/TOOLING.md`), should do more than deliver data to databases (ADR 44). Task 3.4 of `retrosheet-source-review` added a schema digest to our own manifests (ADR 49), which is the kind of work dlt does for tables (schema versions, evolution, load state). The reuse check requires evidence for what dlt cannot do, not an opinion. ADR 44 stays in force until this spike decides otherwise.

## What
A bounded, measured comparison on one small stable source (Lahman, 27 tables): the same typed Arrow tables are written (a) by the current `ProcessedStore` and (b) by `dlt` (filesystem destination, Parquet, `replace` per table, a layout that keeps one folder per dataset). We compare layout, column names and types, row-for-row equality, run time, code size, behaviour on a schema change, an interrupted run and a repeat run, and list what the current path provides that dlt does not (atomic write and footer check, fingerprints, file names, quarantine, manifests) with what it would take to keep each.

## Out of scope
No change to `src/` behaviour, no migration. A migration, if the decision says adopt, becomes its own change with differential tests per source.

## Outcome
`design.md` holds the numbers, ADR 50 records the decision, the owner gets a plain-words recommendation.
