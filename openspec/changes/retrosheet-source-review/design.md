# Design: retrosheet-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/03-retrosheet.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Surveyed 2026-10-29 before the cards run (facts only; the cards decide what is a finding).

- **Provider:** `chadwickbureau/retrosheet` on GitHub, pinned in `core/sources_lock.json` at commit `ee82e50bad71...` (resolved 2026-10-27). retrosheet.org itself is unreachable from this PC and the homelab (blocks B-14, B-18). Files come from the pinned git tree (`core/github_tree.py`), classified by `sources/retrosheet/tree.py`.
- **Registry:** 25 datasets: `events`, `events_postseason`, `events_deduced`, `boxscores_batting`, `boxscores_pitching`, `daily_splits`, `substitutions`, `rosters`, `gamelogs`, `gamelogs_postseason`, `schedule`, `schedule_original`, `umpires`, `discrepancies`, 7 `reference_*` tables and 4 `box_*` tables (interim layouts, ADR 33).
- **Code:** `sources/retrosheet/` is 2,661 lines in 11 files (`api.py` 587, `parser.py` 490, `schema.py` 470, `box_parser.py` 265, `downloader.py` 261). `chadwickpy` (GPL) is imported only in `_chadwick_adapter.py`.
- **Spec:** `openspec/specs/retrosheet-ingestion/spec.md` has six requirements plus two free-text sections (partitioning, schemas) that are not requirements; box accounts are "interim".
- **Docs:** `docs/sources/retrosheet.md` (1,556 lines, mostly generated column dictionaries).
- **Currency today (read from `downloader.py`, to be confirmed by R-04):** a raw file is cached when its manifest entry says COMPLETED, its `source_ref` equals the pinned commit and its byte size matches; only an ETag is stored (no git blob SHA); processed chunks are served by `ProcessedStore.is_cached` without asking the raw tier. This is the same shape Lahman had before its review (ADR 47).
- **Open changes that touch Retrosheet:** `retrosheet-box-accounts` (blocked on the official `boxfile.txt`, B-14/B-15/B-16), `column-descriptions-retrosheet-and-leaderboards` (blocked on retrosheet.org, B-18/B-19), `data-workflow-standard` task 2.6 (this review, B-72). `retrosheet-csv-bundles` was rejected by the owner (ADR 41).
- **Closed while opening this review (2026-10-29):** `catalog-completeness-audit` was finished but never archived; ADR 35 written, `catalog-audit` spec merged, change archived (B-37).

## Opus 5.5 review findings (2026-10-29; I spot-checked R-F1, R-F3, R-F5, R-F6 in the code, the rest are the reviewer's reading or probes)
- R-F1 bug: `parser.py` loops only over the 98-field schema; chadwickpy returns 164 fields, so about 69 (EVENT_ID, BAT_TEAM_ID, START/END_BASES_CD, RUNn_FATE_ID, PA_*_CT, ...) are dropped and `ERR1/2/3_FLD_CD_NEW` are always NULL.
- R-F2 bug: `events*` key is `GAME_ID` alone, so `export --mode merge` keeps one row per game; needs `(GAME_ID, EVENT_ID)` (depends on R-F1).
- R-F3 bug: processed Parquet is served by `is_cached` (status and file only), never rebuilt when the pin moves; docs claim the opposite.
- R-F4 gap: `RetroFile` drops the tree blob SHA; raw check is source_ref plus byte size; only an ETag is stored.
- R-F5 gap: root files (README, notices) are dropped by `classify`; a test locks the drop in.
- R-F6 gap: `--datasets` rejects 14 of 25 registry names; `-d events` without seasons plans nothing and says nothing.
- R-F7 bug: `refresh` and `-d` download far more than asked (event files fetched 5 times per season on refresh).
- R-F8 bug: short game-log rows are skipped, fields past 161 and roster fields past 7 are cut, silently.
- R-F9 bug: box parser overwrites repeated `info` keys, crashes on non-padded dates, bare ValueError for bad ints.
- R-F10 bug (shared): an empty rebuild leaves the old Parquet file in place.
- R-F11 gap (shared): export loads every season into memory first.
- R-F12 gap: box scores and box accounts are not truly streamed; seasons are re-read just to count rows.
- R-F13 gap: no generic `retrosheet.table(name, season)`; `box_accounts` has no top-level function.
- R-F14 gap: no data-quality checks (key duplicates, player ids vs Chadwick register, box vs gamelogs).
- R-F15..F18 nits: processed `.part` cleanup, per-row Python event loop and silent missing `TEAM<year>`, quarantine ignores the source's lake, wrong spec/doc statements (spec sections 2 and 3 are not requirements and name wrong folders).
- Verified clean: 404 is ABSENT never COMPLETED, ref change invalidates the season chunk, thread-pool error handling, atomic writes, GPL boundary, daily/sub columns match chadwickpy, process pool equals in-process.
- Paste-ready spec text from the reviewer is applied in task 2.1.

## Owner decisions (2026-10-30: the owner took the reviewer's recommendations; ADR 48)
- D1 = A: all 164 event fields typed, events keyed `(GAME_ID, EVENT_ID)` (task 5.6).
- D2 = A: combined fingerprint of the raw blob SHAs for processed chunks (tasks 5.1, 5.2).
- D3 = A: quarantine short rows and count them; extra fields to `_extras` (task 5.8).
- D4 = A: export one season at a time, inside this review (task 5.11).

## Web check (2026-10-30)
- `github.com/chadwickbureau/retrosheet` root: `gamelog/`, `reference/`, `seasons/`, `.gitattributes`, `README.md`; there is no `misc/` folder and no LICENSE file. The README states the data is copyrighted by Retrosheet and that Retrosheet's terms of use apply; branches `official` (upstream) and `master` (augmented with errata). The pin must be checked against which branch it follows (task 1.1).
- cwevent: standard fields 0 to 96 match bevent and are stable; `EVENT_ID` is field 96; `BAT_TEAM_ID` and `START_BASES_CD` are extended fields (Chadwick docs, chadwick.readthedocs.io/en/stable/cwevent.html).

## Spec status
The spec delta `specs/retrosheet-ingestion/spec.md` is written. Scenarios marked "written by task N" cite tests that do not exist yet; each task creates its test, and task 4.1 merges the delta, deleting the free-text sections 2 and 3 of the current spec by hand (the new Lake Layout and Typed Columns requirements replace them).

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
