# Proposal: chadwick-source-review

## Why
The owner asked for a source-by-source review from the beginning. Chadwick is first: the smallest
source and the ID crosswalk that every other source joins on (`AGENTS.md` 3A). Reading the adapter
already shows a suspected defect (a hard-coded dataset list that disagrees with the registry), and
import counts show the code under-uses the designated tools (`docs/agents/TOOLING.md`).

## What changes
Run the seven stages of `docs/agents/WORK_BREAKDOWN.md` on the Chadwick source: inventory,
conformance, schema check, code review against the designated tools, tests and spec gaps, live
verification, export and docs. Findings become small follow-up tasks in this change; code changes
are made only under a numbered task.

## Out of scope
A CSV sink and the dlt role (Track 6a, BACKLOG B-43, owner brainstorm). Other sources.

## Impact
`sources/chadwick/` (possibly the adapter and register index code), `docs/sources/chadwick.md`,
the `chadwick-register` spec. The cards are in `docs/agents/tracks/01-chadwick.md`.
