# Tasks: Catalog Audit First-Run Fixes

- [x] 1. Records <!-- id: 1 -->
  - [x] 1.1 Spec deltas; ADR 37
- [x] 2. Savant <!-- id: 2 -->
  - [x] 2.1 Probe `active_spin` and `catch_probability` per season (first season with data, keys)
  - [x] 2.2 Register both variants, drop them from `unsupported`, generate schemas and fixtures, enum members
- [x] 3. MLB <!-- id: 3 -->
  - [x] 3.1 Add roster types `allTime`, `coach`, `gameday` and standings type `currentHalf`; regenerate schemas and fixtures (`--only`)
  - [x] 3.2 Complete `GameType`; equality test with `/v1/gameTypes`
- [x] 4. Tests and docs <!-- id: 4 -->
  - [x] 4.1 Audit tests (respx): MISSING/STALE/NO_DATA/REVIVED/ERROR kinds and exit codes
  - [x] 4.2 Generated docs; hand-written Statcast table entries
- [x] 5. Verification <!-- id: 5 -->
  - [x] 5.1 Gates; live: ingest 2024 `active_spin`, `catch_probability`, roster types for one team, `currentHalf`; rerun `catalog audit` and confirm F-1..F-5 are gone
- [x] 6. Follow-up proposal <!-- id: 6 -->
  - [x] 6.1 Write `mlb-parameterized-stat-types` (F-6)

## Verification (2026-10-27)
- Live: `active_spin` 708 rows (2024) / 562 (2020), `catch_probability` 301 (2024) / 295 (2018, no null ids), roster types `allTime` 1,854 / `coach` 11 / `gameday` 42 rows for one team, `currentHalf` 30 team records; `baseballpy catalog audit` now reports only NO_DATA findings (26 stat types, tracked by `mlb-parameterized-stat-types`).
- Gates: 718+ tests, ruff and mypy --strict clean, docs generate --check up to date.
