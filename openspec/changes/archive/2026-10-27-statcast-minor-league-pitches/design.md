# Design: Minor-League Statcast Pitches

## Evidence (live probes, 2026-10-27, `baseballsavant.mlb.com/statcast_search/csv`, `all=true&type=details`)
- `minors=true` on 2024-06-15: 6,042 pitches, home teams `ABQ, BUF, CLR, DUN, LOU, ...` (affiliated minor-league clubs), 119 columns identical to the MLB export (no extra, none missing).
- `minors=true&hfLevel=AAA|`: 4,594 rows; `hfLevel=A|`: 1,448 rows (4,594 + 1,448 = 6,042); `AA|`, `A+|`, `A-|`, `R|`, `WIN|`, `FRk|`, `CPX|`, `DSL|` returned 0 that day.
- `sport_id=`, `sportId=`, `level=`, `hfMilb=` are ignored (they return the MLB population); `hfLevel` without `minors=true` returns 0.
- Earliest data: nothing in 2014-2020 (April-September samples); 2021 from May (3,179 rows on 3 sampled days) onwards; 2022 5,683, 2023 5,713, 2024 6,042, 2025 6,152 on a mid-June day. `game_type` is `R` in all samples.
- MiLB calendars (`/v1/seasons?sportId=11|12|13|14`): regular season from late March/early April to mid/late September; `springStartDate` is null for minors.

## Decisions
1. **Separate dataset, same schema.** Minor-league `game_pk`s are disjoint from MLB's, but the populations differ (level, quality, venue), so mixing them in `pitches` would break every MLB analysis; a separate dataset with the identical schema keeps unions trivial (`UNION ALL BY NAME`).
2. **Canonical population = `minors=true` with no level filter.** `hfLevel` is a filter; filtered queries are never persisted (same rule as MLB `StatcastQuery` filters).
3. **Window source:** union of sports 11-14 calendars (earliest `regularSeasonStartDate`, latest `postSeasonEndDate`, clamped to today); seasons before 2021 are skipped with a logged reason instead of 400 empty windows, and `ingest_all(minors=True)` starts at 2021.
4. **No derived `level` column.** The upstream CSV has none; documenting how to derive it (team abbreviation -> `v1/teams?sportId=`) is enough.

## Risks
- Savant could add/rename levels (`AA` is 0 today); the probe records which levels returned rows and the docs list them with the probe date.
- Row cap: minors days are ~6,000 rows, the existing 25,000-row bisection applies unchanged.
