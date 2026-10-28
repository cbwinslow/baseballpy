# Design: verify-optin-paths

## Method
Scratch lake on the homelab (`~/baseballpy-scratch/home`, Python 3.12, `polars[rtcompat]`, `duckdb==1.4.4`), season 2023. Scratch scripts are never committed; evidence is the `catalog status` output and the audit log.

## Findings
- 2026-10-28, per-game family (`max_games=20`, first 20 final games of 2023 across all sports): 13 of 13 per-game datasets ingested in 127 s (boxscore info/officials/pitching notes/players/teams/top performers, feed plays/play events/linescore innings/officials, linescore, win probability, play-by-play); a re-run of all 13 served every request from cache (6 s). `quarantine list` was empty.
- Real games exposed `schema_drift` the generator's three sample games had not: `reviewDetails.*` (challenge/overturn), `matchup.batterHotColdZoneStats.stats`, `team.parentOrgId`/`parentOrgName` (minor-league games). Root cause: `SAMPLE_GAMES` plus one 2015 game is too narrow. Fix: the generator samples a spread of games (first, middle, last) over four dates and the minor-league levels (`SAMPLE_GAME_DAYS`); all 13 game schemas regenerated (26 sample games, 0 failed requests), the drift fields are typed columns, and the column dictionaries were regenerated.
