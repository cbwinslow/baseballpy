# Change Proposal: Minor-League Statcast Pitches

## Context & Motivation
`complete-source-coverage` documented minor-league Statcast pitches as *unreachable* ("`sportId` is ignored, `hfLevel=11|` returns 0 rows"; ADR 30, `docs/sources/statcast.md`, ROADMAP). That was wrong: the probes tried the wrong parameters. A later probe (2026-10-27, `scripts`-free one-off, recorded in `design.md`) found that `statcast_search/csv?...&minors=true` returns minor-league pitches with the same 119 columns, and `hfLevel` works *together with* `minors=true`. AGENTS.md section 3 and the owner's standing rule forbid leaving upstream data behind, so this is a coverage bug, not a new feature.

| ID | Gap |
|----|-----|
| M-1 | `statcast.pitches_minors` does not exist; minor-league pitches (AAA and Single-A, 2021-present) are never downloaded. |
| M-2 | Docs/ADRs/ROADMAP state the data is unreachable (incorrect). |
| M-3 | `StatcastQuery` has no way to express `minors`/`levels`; filtered queries are (correctly) never persisted. |

## Proposed Changes
1. New dataset `statcast.pitches_minors` (view `statcast_pitches_minors`): same strict schema as `pitches`, same key `(game_pk, at_bat_number, pitch_number)`, season-partitioned, raw CSV windows under `raw/statcast/pitches_minors/`.
2. `StatcastQuery(minors=True, levels=("AAA",))`: `minors=True` alone is the canonical minors population and is persisted into `pitches_minors`; a `levels` filter narrows it and, like every filter, is returned but not persisted.
3. `StatcastExtractor.ingest_season(season, minors=False)` / `ingest_all(minors=False)`; the season window for minors is the union of the MLB calendars of sports 11-14 (`/v1/seasons?sportId=<id>&season=<Y>`, regular season start to post-season end); first season with data is 2021.
4. Fix the documentation claims (docs/sources/statcast.md, ADR 24/30 notes, ROADMAP, AGENTS-referenced text).

## Out of Scope
Level-tagging rows with a derived `level` column (not upstream data); Arizona Fall League / foreign leagues (no data found); the MLB Stats API minor-league coverage (already ingested through `sport_ids`).

## Impact
Additive: one new dataset and flags. `pitches` is unchanged. Recorded as a correction in ADR 30's follow-up and `docs/DECISIONS.md` ADR 31.
