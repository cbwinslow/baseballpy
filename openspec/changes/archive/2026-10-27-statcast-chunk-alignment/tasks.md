# Tasks: Aligned Statcast Chunk Windows

- [x] 1. Specs and records <!-- id: 1 -->
  - [x] 1.1 Spec delta and ADR 32
- [x] 2. Implementation <!-- id: 2 -->
  - [x] 2.1 `grid_windows()` in `statcast/extractor.py`
  - [x] 2.2 `extract_async` and `ingest_season` use grid windows; `extract` filters to the requested `game_date` range
  - [x] 2.3 Duplicate-key warning for the touched season after persisted extracts
- [x] 3. Tests <!-- id: 3 -->
  - [x] 3.1 Unit tests for `grid_windows` (year boundary, leap year, partial first/last block)
  - [x] 3.2 Regression: overlapping, nested and adjacent `extract` ranges leave zero duplicate keys; results are exactly the requested days
  - [x] 3.3 Adapt existing window-count tests
- [x] 4. Docs <!-- id: 4 -->
  - [x] 4.1 `docs/sources/statcast.md` windowing paragraph
- [x] 5. Verification <!-- id: 5 -->
  - [x] 5.1 Gates; 5.2 manual: repeat the overlapping live scenario (minors 2024-06-10..16 then 06-15) and confirm 0 duplicates

## Verification (2026-10-27)
- Gates green; regression test `tests/test_statcast_grid.py` (overlapping, nested, adjacent ranges, Hypothesis on grid agreement); live: minors 2024-06-10..16 then 2024-06-15 and 06-14..20 leave 0 duplicate keys (see the closing commit).
