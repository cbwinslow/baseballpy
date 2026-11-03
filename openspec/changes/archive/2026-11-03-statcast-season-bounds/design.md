# Design: statcast-season-bounds

## Decisions
- **Where:** `seasons.py` is the single place; `adapter.FIRST_SEASON`/`FIRST_MINORS_SEASON`
  are re-exported from it so older imports keep working.
- **Bottom:** `season_floor(minors, first_with_data)` = max of the dataset floor and the probe's
  first season. 2008 applies to everything (owner decision, 2026-11-03). Savant does return
  older rows (1990 returned 558,042 rows in a test), so this is a recorded owner exception to
  "never leave upstream data behind", written down in ADR 56.
- **Top:** no constant. `season_skip_reason(season, today)` compares with `today.year`; a
  current-year season whose calendar start is after today is skipped inside
  `_ingest_season_async` (the window's start is later than its capped end).
- **Bulk vs ad hoc:** bulk paths (`ingest_*`) return a skip reason; `get_leaderboard`,
  `extract` and `table` raise `ValueError` naming the bounds, because a caller asked for one
  specific thing and silence would hide it.
- **Reuse check (TOOLING.md):** nothing in pyarrow/duckdb/polars covers a provider's first
  season; this is a provider rule, so it is a small declarative function, not a library gap.

## Evidence
- Lake cleanup (2026-11-03, owner approved): 87 pre-2008 season folders (13 pitch seasons 1890-1990, 34 leaderboards x raw and processed for 1850) and 122 manifest entries removed; the script only touched `statcast` seasons below 2008.
- Live check (scratch home, CLI): `ingest statcast -s 1850,1990,2031 -d pitches -d leaderboards -d pitches_minors` gave 7 jobs, all `skipped`, and the audit log holds exactly the 7 job events and no HTTP request (zero lines with an `http` endpoint).
- Tests: `tests/test_statcast_seasons.py` (5 tests) plus the existing Statcast suites (104 passed) before the full run.
- Not verified: the unstarted-season skip against the real MLB calendar (covered by a mocked calendar only).
