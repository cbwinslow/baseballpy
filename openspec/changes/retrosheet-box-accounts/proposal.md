# Change Proposal: Parse Retrosheet Box-Score Game Accounts (`.EB*`)

## Context & Motivation
`complete-source-coverage` stores the 428 box-score game-account files (`seasons/<Y>/<Y>.EBA|EBN|EBE|EBR|EBF`, 1871-2025) raw only, because the format specification (`https://www.retrosheet.org/boxfile.txt`) could not be fetched from the build environment (connection refused). AGENTS.md section 3 forbids leaving upstream data unparsed. The local raw files (10 profiled: 1950 and 2023) let us derive the layout empirically; the official document remains the authority and must be fetched before implementation (task 1.1).

| ID | Gap |
|----|-----|
| B-1 | `.EB*` files (box scores for games without play-by-play) are raw only; no typed tables. |
| B-2 | Pre-1920 history of many seasons exists *only* as box accounts, so box-score queries for those seasons return nothing. |

## Proposed Changes
1. Parse every record kind into strict, typed datasets (per-season partitions, key `game_id` + record-specific columns): `box_games` (id, version, info), `box_starters` (start), `box_batting` (stat,bline), `box_pinch_hitters` (stat,phline), `box_pinch_runners` (stat,prline), `box_fielding` (stat,dline), `box_pitching` (stat,pline), `box_team_totals` (stat,tline), `box_linescores` (line), `box_events` (event,*line: hrline, dpline, tpline, sbline, csline, hpline), `box_comments` (com).
2. A pure parser in `sources/retrosheet/box_parser.py` (no chadwickpy needed), streaming per file into Parquet row groups like the event parsers; unknown record kinds go to `box_unparsed` (raw line + kind) and log a drift warning.
3. Registry, generated docs, fixtures from real files, tests (Hypothesis on field counts), ADR 33.

## Out of Scope
Merging box accounts with play-by-play events (a consumer concern); the Negro Leagues game files (`gamefile.txt` format) unless present in the tree.

## Impact
Additive datasets under `retrosheet`; `box_files` raw dataset unchanged.
