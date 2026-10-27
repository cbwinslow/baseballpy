# Tasks: Minor-League Statcast Pitches

- [x] 1. Specs and records <!-- id: 1 -->
  - [x] 1.1 Spec delta (`specs/statcast-ingestion/spec.md`) and ADR 31 (correction of the "unreachable" claim)
- [x] 2. Implementation <!-- id: 2 -->
  - [x] 2.1 Register `statcast.pitches_minors` (schema = `STATCAST_SCHEMA`, view `statcast_pitches_minors`, key, doc anchor)
  - [x] 2.2 `StatcastQuery(minors, levels)` params (`minors=true`, `hfLevel=<L>|`), persistence rules (only unfiltered minors population)
  - [x] 2.3 Extractor: dataset/raw selection by population, `season_window(season, minors)`, `ingest_season(season, minors=False)`, `ingest_all(minors=False)` starting at 2021
- [x] 3. Tests <!-- id: 3 -->
  - [x] 3.1 respx tests: params, separate dataset/partitions, filtered not persisted, calendar union, pre-2021 skipped, resume
  - [x] 3.2 Registry/docs consistency (existing tests cover view/anchor)
- [x] 4. Docs <!-- id: 4 -->
  - [x] 4.1 Correct `docs/sources/statcast.md`, `docs/ROADMAP.md`, ADR notes that claim minors are unreachable; generated dictionary for `pitches_minors`
- [x] 5. Verification <!-- id: 5 -->
  - [x] 5.1 Gates (pytest, ruff, mypy --strict, docs generate --check)
  - [x] 5.2 Manual: ingest one week of 2021 and 2024 minors into a scratch home; check game_pk disjoint from MLB, 0 duplicate keys, AAA+A row sum equals the unfiltered total

## Verification (2026-10-27)
- Live (scratch home): 2021-06-14..20 8,899 minors rows, 2024-06-10..16 35,352 rows; `AAA` 4,594 + `A` 1,448 = 6,042 = unfiltered minors on 2024-06-15; minor-league `game_pk`s disjoint from MLB's; teams `SUG, GWN, BUF, ...`. The duplicate keys seen in that run exposed the overlap defect fixed by `statcast-chunk-alignment`.
