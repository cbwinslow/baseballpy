# Change Proposal: Column Descriptions from Provider Metadata

## Context & Motivation
`design.md` of `complete-source-coverage` (section 8) planned hand-curated `docs/columns/<source>.yaml` descriptions merged into the generated dictionaries; they were never written, so the Description column of every generated table is blank (AGENTS.md section 1.4 requires a domain definition per attribute).

| ID | Gap |
|----|-----|
| D-1 | No description for any of the ~10,000 generated columns. |
| D-2 | No test fails when a documented column lacks a description. |

## Proposed Changes
1. A metadata layer: `docs/columns/<source>.yaml` (`dataset.column: description`) merged by `docsgen.py`; missing description renders as an explicit `TODO` and is counted.
2. Fill it from provider-supplied definitions wherever they exist, never from invention: MLB `/v1/baseballStats` (210 stat definitions with lookup names and groups), `/v1/statTypes`, `/v1/gameTypes`, `/v1/positions`, event/pitch type lists; Savant's leaderboard/CSV glossary pages; Retrosheet format documents (event, box, game log, roster, schedule, discrepancy); the Lahman readme in the mirror repo; the Chadwick register README. Descriptions cite their source (`source: <url>`).
3. A coverage report (`baseballpy docs coverage`) and a threshold test that ratchets upward (start at the measured baseline, never decreases).

## Out of Scope
Translating or paraphrasing licensed text beyond short factual definitions; per-value enumerations beyond what providers publish.

## Impact
Docs only (plus the generator's merge step). Recorded as ADR 34.
