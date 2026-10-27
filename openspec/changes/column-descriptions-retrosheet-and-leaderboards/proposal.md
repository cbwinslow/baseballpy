# Change Proposal: Retrosheet and Savant Leaderboard Column Descriptions

## Context & Motivation
`column-descriptions-from-provider-metadata` delivered the mechanism and the content that provider metadata supports directly (MLB, Statcast pitches, Lahman, Chadwick). Two parts could not be done on 2026-10-27: Retrosheet's format documents (`retrosheet.org` refused connections from curl and WebFetch, and web.archive.org is not fetchable) and the Savant leaderboard columns (Savant publishes a glossary only for pitch CSV columns).

## Proposed Changes
1. Retry `https://www.retrosheet.org/gamelogs/glfields.txt`, `eventfile.htm`, `boxfile.txt` and the roster/schedule/discrepancy notes; build `docs/columns/retrosheet.json` with cited sources (extend `scripts/build_column_descriptions.py`).
2. Find provider definitions for the leaderboard columns (Savant leaderboard pages and glossary); cite them; leave the rest `TODO`.
3. Raise the coverage baseline (`docs coverage --write-baseline`).

## Out of Scope
Inventing prose; guessing Retrosheet column names (see `retrosheet-box-accounts`).

## Impact
`docs/columns/*.json`, generated docs, coverage baseline only.
