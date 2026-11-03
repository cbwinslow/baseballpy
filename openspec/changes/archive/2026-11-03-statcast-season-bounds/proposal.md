# Proposal: statcast-season-bounds

## Problem
Statcast ingestion accepts any season. Named seasons (`ingest statcast -s 1850`) skip the
2008 start that only `all` respects, so the program spends requests on seasons the owner
excluded, and 1890-1990 pitch folders and 1850 leaderboard folders were written into the real
lake (empty or with rows). A season in the future fails with a confusing "start after end"
message.

## Solution
1. One module, `sources/statcast/seasons.py`, holds the rule: the bottom is `2008` (owner hard
   line, ADR 56) for every Statcast dataset, `2021` for minor-league pitches, and the later
   first season the live probe recorded for each leaderboard (`lb_schema.min_year`). The top is
   never a constant: it is the current year from the lake clock (`LakeConfig.today`), and a
   season that has not started yet (calendar start after today) is skipped with a reason.
2. Every library entry point applies the rule before any request: `ingest_season`,
   `ingest_all`, `ingest_leaderboard`, `get_leaderboard`, `StatcastGameFeed.ingest_season`,
   `extract`/`extract_async` and `table()`. Bulk ingests report the season as skipped with the
   reason; single ad-hoc fetches raise `ValueError`.
3. The adapter maps skips to `SKIPPED` jobs with the reason in the detail (no request, no
   failure), so a mixed selection such as `ingest all -s 1990-2024` still runs the other
   sources.
4. The stray pre-2008 Statcast data in the owner's lake was deleted (owner approved 2026-11-03).

## Scope
`src/baseballpy/sources/statcast/{seasons,adapter,extractor,leaderboards,game_feed,access}.py`,
`tests/test_statcast_seasons.py`, `openspec/specs/statcast-ingestion/spec.md`,
`docs/sources/statcast.md`, ADR 56.
