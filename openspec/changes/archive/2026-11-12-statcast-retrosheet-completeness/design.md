# Design: statcast-retrosheet-completeness

## 1. Evidence
Live menu fetched 2026-11-11 (`/` navigation); each candidate route probed with the project's `HttpClient`; the season
parameter of each route found by comparing payload hashes across seasons (`season[]`, `season`, `season_snake`,
`season_range`, `year`; hot stove ignores the season: a flat snapshot). WBC: the page script (`isWbc`) offers the
rounds F, D, L, W and the seasons of `wbcYears`, but every request tried returned MLB rows.

## 2. Prior art and reuse check
Reused: `LeaderboardDef` registry and `scripts/gen_savant_schemas.py` (live types, keys checked unique, season styles),
`SiteDataset` and `scripts/gen_retrosheet_site_schemas.py`, `AuditTracker.mark_download_complete`. New code: one season
style (`season_array`) and a thread pool around member parsing.

## 3. Decisions
- A route that exists in the live menu is registered, or listed unsupported with the request tried and the answer.
- Odd cells in number columns of the Negro Leagues files are handled as for the other site logs (ADR 110).

## 4. Tests
`tests/test_statcast_coverage.py` (registry, schemas, fixtures, enum, doc agree for every variant),
`tests/test_retrosheet_site_logs.py` (Negro Leagues tables, parallel parsing equal to sequential),
`tests/test_retrosheet_site.py` (download seconds logged).

## 5. As built (real runs, 2026-11-11)
All twelve new leaderboards were downloaded (for example `pitcher_running_game` 5,482 rows, `year_to_year_pitcher`
2,516, `outfield_directional_oaa` 3,443, `hot_stove_batter` 197) and the Statcast type audit shows 0 text columns
without a recorded reason across 48 leaderboards. The seven Negro Leagues tables hold 459,932 rows (8,215 games, 168,152
plays); the audit is clean with the line scores recorded as text. Exact duplicate rows exist upstream (7 in batting,
193 repeated `(gid, pn)` in plays) and are kept. The lake-shape contract test needed a combined page for the two hot
stove variants, which share one route.
