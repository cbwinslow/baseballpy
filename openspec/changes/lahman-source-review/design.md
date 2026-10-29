# Design: lahman-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/02-lahman.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Measured 2026-10-29 (survey before the review; no code changed):
- **Datasets:** 27 Lahman tables; the `LahmanTable` enum, the generated `tables.py` and the registry all list 27; every registry key is non-empty (composite keys, up to 6 columns).
- **Upstream (`cbwinslow/lahman-database-csv`):** the pin `0377e0b8d3` is the latest commit today. The tree has 31 blobs: 27 data CSVs (42,147,792 bytes), `data/readme2025.txt` (47,976 bytes, the SABR data dictionary), `LICENSE` (22,240), `README.md` (4,369), `.gitignore` (10). Only the 27 CSVs are ingested.
- **Code:** `sources/lahman/` adapter (61 lines), extractor (182), api (244: `LahmanSource` with `get_table`, 13 named accessors, `import_archive`, `list_tables`), quality (74: stale-year warning, duplicate-key rows, orphan-player rows), schema (58), normalizer (41), generated `tables.py` (463).
- **Top-level API:** 8 functions (`batting`, `pitching`, `people`, `teams`, `fielding`, `salaries`, `hall_of_fame`, `allstar`) plus `import_archive`.
- **Tests:** `tests/test_lahman.py` (109 lines), `tests/test_lahman_coverage.py` (229).
- **Spec `lahman-database`:** 6 requirements, 7 scenarios (dual-mode ingestion, typed Parquet, enums, strict schemas for 27 tables, permitted sources only, safe archive import).
- **Docs:** `docs/sources/lahman.md` (935 lines, mostly the generated dictionary); descriptions cover all but 11 of 372 data columns (399 with `_extras`).
- **Currency today:** pinned git ref; the raw tier uses a never-expires TTL and compares `source_ref`; the processed tier is served without any check; ETags are stored, git blob fingerprints are not (tasks 5.1 and 5.2).
- **Owner decisions expected during the review:** stay pinned or float with a time-to-live (5.2); one generic accessor or 27 named functions (5.5); whether to change registry keys that contain nullable columns (1.3, 3.2). Each is asked once, in one short list.
- **Plan review:** an independent Opus 5.5 pass reviewed this plan before any card ran; the standard task table (`scripts/new_source_review.py`) was changed because of it (look-only review tasks 1.x, standard fixes 5.1 to 5.5, tests wait for every fix, new checks for licence, documentation files, cache tiers, repeated-call cost, cross-source id match, names on export, pinned citations).

### Planned spec delta (written in task 2.1; add scenarios with `Verified by` tests)
1. Currency and fingerprints: every raw table records its fingerprint; a changed upstream file is detected by `cache check --upstream`; every cache tier (raw and processed) decides with `is_current()` (matches the `caching-and-invalidation` spec; add the Lahman scenarios).
2. Complete documentation capture: the data dictionary, licence and README are kept in `raw/lahman/` with their hashes, and the licence is stated in `docs/DATA_LICENSES.md`.
3. Complete Python access: every registered table is readable with one documented call.
4. Import path: non-data files of a supplied release are kept; a mixed release is detected; unknown files are not silently registered.
5. Data quality: the orphan checks are order-independent, cover every id column, and their findings are visible to users.
6. Export: all 27 tables verify for every export target; column names survive PostgreSQL; tables whose key has NULLs are refused for merge with the stated message.

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
