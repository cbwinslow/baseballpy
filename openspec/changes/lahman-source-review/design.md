# Design: lahman-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/02-lahman.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Measured 2026-10-29 (survey before the review; no code changed):
- **Datasets:** 27 Lahman tables; the `LahmanTable` enum, the generated `tables.py` and the registry all list 27; every registry key is non-empty (composite keys, up to 6 columns).
- **Upstream (`cbwinslow/lahman-database-csv`):** the pin `0377e0b8d3` is the latest commit today. The tree has 31 blobs: 27 data CSVs (42,147,792 bytes), `data/readme2025.txt` (47,976 bytes, the SABR data dictionary), `LICENSE` (22,240), `README.md` (4,369), `.gitignore` (10). Only the 27 CSVs are ingested.
- **Code:** `sources/lahman/` adapter (61 lines), extractor (182), api (244: `LahmanSource` with `get_table`, 12 named accessors, `import_archive`, `list_tables`), quality (74: stale-year warning, duplicate-key rows, orphan-player rows), schema (58), normalizer (41), generated `tables.py` (463).
- **Top-level API:** 8 functions (`batting`, `pitching`, `people`, `teams`, `fielding`, `salaries`, `hall_of_fame`, `allstar`) plus `import_archive`.
- **Tests:** `tests/test_lahman.py` (109 lines), `tests/test_lahman_coverage.py` (229).
- **Spec `lahman-database`:** 6 requirements, 7 scenarios (dual-mode ingestion, typed Parquet, enums, strict schemas for 27 tables, permitted sources only, safe archive import).
- **Docs:** `docs/sources/lahman.md` (935 lines, mostly the generated dictionary); descriptions cover all but 11 of 372 columns.
- **Currency today:** pinned git ref plus a never-expires TTL, no fingerprints (task 1.5 moves it onto `core/upstream.py`).

### Planned spec delta (written in task 2.1; add scenarios with `Verified by` tests)
1. Currency and fingerprints: every raw table records its git blob fingerprint; a changed upstream file is detected by `cache check --upstream`; the decision is `is_current()` (matches the `caching-and-invalidation` spec; add the Lahman scenario).
2. Complete documentation capture: the upstream data dictionary, licence and README are kept in `raw/lahman/` with their hashes.
3. Complete Python access: every registered table is readable with one documented call; record types carry every column (schema-sync test).
4. Export: all 27 tables verify for every export target; tables whose key has NULLs are refused for merge with the stated message (covered by the `data-export` spec; add the Lahman table list to the source page).

## S1 inventory
(not started)

## S2 conformance
(not started)

## S3 schema and types
(not started)

## S4 code review against the designated tools
(not started)

## S5 tests and spec gaps
(not started)

## S6 live verification
(not started)

## S7 access, export, descriptions, docs, close
(not started)
