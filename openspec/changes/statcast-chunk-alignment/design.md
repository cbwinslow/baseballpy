# Design: Aligned Statcast Chunk Windows

## Evidence
2026-10-27 live check (scratch lake): `extract("2024-06-10","2024-06-16", minors)` wrote windows 06-10..06-14 and 06-15..06-16; a later `extract("2024-06-15","2024-06-15", minors)` wrote window 06-15..06-15. DuckDB: `select count(*) from (... group by game_pk, at_bat_number, pitch_number having count(*) > 1)` = 6,042 (all pitches of 2024-06-15 present twice).

## Decisions
1. **Grid:** day-of-year based blocks of `chunk_days` from January 1 (block = `(yday - 1) // chunk_days`); the last block of a year is clipped to December 31. Deterministic, independent of the request, and consistent between `ingest_season` and `extract`.
2. **Exactness for callers:** fetch whole grid windows (each is a unit of persistence and resume), then filter rows to `[start, end]` on `game_date`. A request for one day fetches its whole window (<= `chunk_days` days; <= 25,000 rows, bisected if needed).
3. **Chunk id unchanged** (`<start>_<end>` of the grid window), so the manifest/part naming scheme and `is_fresh` logic are untouched.
4. **Filtered queries** use the same grid for fetching but still never persist.
5. **No migration:** chunk files from earlier unaligned runs may overlap grid windows; the duplicate check warns, and the unified CLI change will own a repair command.

## Risks
A one-day request costs up to `chunk_days` days of downloading (default 5): acceptable for a resumable, idempotent store; callers wanting exact single-day fetches without persistence can still pass a filter-less `query` with `cache` disabled via config.
