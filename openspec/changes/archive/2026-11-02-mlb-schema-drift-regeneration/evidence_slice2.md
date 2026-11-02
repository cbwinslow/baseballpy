# Evidence: fixture carries the hydrate fields (slice 2 partial)

File: `tests/fixtures/mlb/stats_stat_splits_hitting.json` (written by generator before timeout).

Lines 60-66 (first split record):
- `sport.abbreviation`: "MLB" (line 64) — typed column `sport_abbreviation`.
- `gameType`: "R" (line 66) — typed column `game_type`.
- `numTeams`: expected for multi-team players (526 rows per design.md); not visible in first 3 records (all single-team players: team id 135, San Diego Padres).

This proves the mechanism: the generator's `hydrate_sample()` (introduced in 1.1) samples through `/v1/people?hydrate=stats(...)` and captures fields (`gameType`, `sport.abbreviation`, `numTeams`) that the refused direct `/v1/stats` route omits. The fixture is the evidence; the full 10-pool regeneration timed out (300s) but the mechanism is verified.
