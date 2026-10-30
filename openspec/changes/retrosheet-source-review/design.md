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

## 5.6 evidence (2026-10-30)
- chadwickpy `COLUMNS` has 164 names (fields 0-96 plus extended 0-66); the old schema had 98, of which `ERR1/2/3_FLD_CD_NEW` do not exist in chadwickpy (always NULL, removed). 69 columns were new.
- Types of the 69 new columns were inferred from 38,161 real rows (1925 PHA, 1935/1950/1975/2000/2023 BOS from the pinned ref): 17 flags (`T`/`F`) -> bool, 10 text ids/counts -> string, the rest integers (all within 0..96) -> int16.
- `(GAME_ID, EVENT_ID)` unique in all six files, no NULL key cells; `_extras` NULL on every row (chadwickpy knows no extra field today); row count unchanged.
- Tests: `tests/test_retrosheet_events.py` (3). Docs regenerated; `docs/sources/retrosheet.md` hand-written text corrected.
- Not verified: the full re-parse of the 2015-2024 lake on the homelab (card R-11).

## 5.10 and 5.11 evidence (2026-10-30)
- 5.10: `ProcessedStore.put_stream` now deletes the old part when the new stream is empty (`test_an_empty_rebuild_removes_the_old_part_so_old_rows_are_not_served`); the Retrosheet downloader also clears stale `.part` files under `processed/retrosheet` (`test_stale_processed_part_files_are_discarded_too`). **Deferred (shared, recorded not fixed):** R-F18, the quarantine singleton writes to the default `LakeConfig`, so a source built with `LakeConfig(home=X)` quarantines into the default home; users who set `BASEBALLPY_HOME` are not affected. It needs a per-call quarantine location in `collect_bad_values` and every parser decorator; it belongs to a cross-source change.
- 5.11: export builds one lazy `_Slice` per season (row count from Parquet footers) and loads, writes and verifies one season at a time; merge key checks read only the key columns. `test_export_holds_one_season_at_a_time` pins the read/write order. Memory of a real many-season export was not measured (see R-11).

## 5.1, 5.2, 5.3, 5.4, 5.7, 5.8 evidence (2026-10-30)
- 5.1: `RetroFile.sha` carries the tree's blob SHA; `RawStore.put(upstream=Fingerprint(GIT_BLOB, sha))` records it (manifest `upstream`); `_is_cached` compares it, so an unchanged file survives a pin move; an entry without a blob fingerprint falls back to the pinned commit.
- 5.2: every processed chunk records `upstream` = `input_set` fingerprint (sha256 of the sorted `path:blob` lines of the raw files it is built from, `RetrosheetSource._expected`); `_current` serves it only on a match (chunks without one: pinned ref). Offline (tree unavailable) the pinned ref decides and a warning is logged once. Tests: `tests/test_retrosheet_currency.py` (pin move refetches 1 changed blob of 11 and rebuilds only its chunks; a pin move with no change fetches and rebuilds nothing; refresh fetches each file once; a selection downloads only what it reads).
- 5.3: README.md and .gitattributes (the whole root of `chadwickbureau/retrosheet`, checked on the web 2026-10-30) go to `raw/retrosheet/documents/`, uncovered files under the data folders to `raw/retrosheet/unclassified/`, with blob fingerprints (`ingest_reference` calls `ensure_documents`). The existing classification test no longer locks the drop in.
- 5.4: N/A, Retrosheet has no user-supplied import path.
- 5.7: `api.UNITS` is the one declarative table (raw file kinds read, datasets and chunks written); `DATASET_UNIT`, `SEASON_DATASETS` and the adapter derive from it; all 25 registry names are accepted by `--datasets` (`tests/test_retrosheet_selection.py`, which also pins the table to the registry), a season dataset without `--seasons` fails with an instruction, and `refresh` or a selection no longer downloads every kind. A reference name such as `reference_teams` ingests every reference table (they are one job).
- 5.8 (written by agy, reviewed line by line): short game-log rows (<10 fields) and roster rows (<6) are quarantined with their raw line and counted; fields past 161 (game logs) and past 7 (rosters) go to a new `_extras` JSON column (`tests/test_retrosheet_rows.py`, 2 tests).
- Memory behavior (5.12) still open: boxscores and box accounts hold one season in lists; row counts for the single-output units now come from `put_stream` (no re-read), see 5.12.

## 5.5, 5.12 and 5.13 evidence, and a key finding (2026-10-30)
- 5.5: `RetrosheetSource.table(name, season=None, kind=None)` and the module function `table` read any registered dataset through the declarative `ACCESSORS` table; `box_accounts` now has a module-level function; `test_every_registry_dataset_is_selectable_and_readable` checks every registry name (reference tables the fake repository does not publish are skipped).
- 5.12: row counts of the single-output units come from `put_stream` (no Parquet re-read) and the docs no longer claim whole-process streaming; boxscores and box accounts still build one season in memory, which is small, so no further change.
- 5.13: `retrosheet/quality.py` (declarative `FOREIGN_KEYS`, one generic function, helpers moved to `core/quality.py` and reused by Lahman) runs after a season is stored; findings land in the processed manifest `quality` field and show in `catalog status`. Real-data measurement of the match rates is left to card R-11 on the homelab lake.
- **New finding while measuring keys on 38,161 real rows (six eras):** the registered keys of `substitutions` (`GAME_ID, EVENT_ID`: 20-25% of rows duplicated) and `daily_splits` (`GAME_ID, TEAM_ID, PLAYER_ID`: 1 duplicate in 3 of 6 files) were not unique. Fixed: substitutions `(GAME_ID, EVENT_ID, SUB_ID)` and daily_splits `(GAME_ID, TEAM_ID, PLAYER_ID, SLOT_CT, SEQ_CT)` are unique in all six files. `boxscores_batting` stays non-unique (a player re-entering in the same slot), recorded as task 5.14.

## 5.9 evidence (2026-10-30)
- Written by agy, reviewed line by line, then simplified by Claude (three helper functions) to satisfy the lint limits: a repeated `info` key keeps its first value in `box_games` and every later line in `box_records`; dates parse with `strptime` (`1950/4/1` works) and bad ones are quarantined; non-integers raise `BoxParseError` naming the line; the docstring says 17 counting stats. Tests: `test_repeated_info_keys_are_kept` and two more in `tests/test_retrosheet_box.py`.

## 5.14 evidence (2026-10-30)
- The duplicates were real second stints (the same player twice in one slot and position in a 1925 game). `boxscores_batting` gets a `seq` column (order of a slot's occupants, starter first; pitching already had one) and the key `(game_id, team_id, slot, seq)`, which is unique by construction and was checked on the six sample files (12,112 rows, 0 duplicates, max seq 10). Test: `test_boxscores_batting_key_is_unique_and_orders_a_slots_occupants`. Existing `boxscores_batting` Parquet must be rebuilt (`ingest --refresh -d boxscores`).

## Evidence for 5.15 (audit logging of every operation)

Before: only `download_season` wrote an audit event. Now one event per tree listing, file download, document keeping, unit build (parse and store), quality check, season ingest and reference ingest, all through `core/audit.py` `default_audit_logger.track` (no new mechanism). `tests/test_retrosheet_audit.py` reads the events back, including a cache-hit second run. Gates: 1135 passed, 5 skipped; ruff, format, mypy --strict, docs --check, project map --check, openspec validate --specs 16 passed. Timings from the live 2015-2026 run are recorded under card R-11.

## Evidence for 5.16 (rosters key)

The live 2015-2026 run reported `rosters duplicate_key_rows` of 76 (2015) and 79 (2016). Cause: `ALS<year>.ROS` and `NLS<year>.ROS` (all-star rosters) repeat each player's club line (`altuj001,...,HOU,2B` is in `HOU2015.ROS` and in `ALS2015.ROS`), so `(year, team, player_id)` is not unique. The new `roster` column (file team code) makes `(year, roster, player_id)` unique; no player appears twice inside one roster file in the downloaded seasons. Test: `tests/test_retrosheet_rows.py::test_all_star_roster_lines_are_told_apart_by_the_roster_they_came_from`.

## Evidence for 5.17 (substitutions key)

Live run, season 2018: `substitutions duplicate_key_rows=1`. Game TBA201805080, event 53: `wendj002` is substituted in at second base and moves to shortstop in the same stoppage, so `(GAME_ID, EVENT_ID, SUB_ID)` repeats while `SUB_FLD_CD` (4 and 6) and `REMOVED_ID` differ. The key is now `(GAME_ID, EVENT_ID, SUB_ID, SUB_FLD_CD)`. A player who returned to the same position in one stoppage would still collide; the quality check would report it. Test: `tests/test_retrosheet_events.py::test_substitution_and_daily_split_keys_survive_double_switches`.

## Evidence for the live 2015-2026 run (task 3.1, partial) and 5.18

Run on a scratch home (2026-10-30, this PC, `-c 2`): 13 jobs completed (reference + seasons 2015-2026), no failures, 4,780 s of job time, 450 MB on disk, 6.67 million rows written. Seasons take 380-510 s each (2020 272 s; 2025 255 s; 2026 is schedule-only, 2,430 rows, 0.5 s). From the audit log: file downloads 894 files, 2,239 s (the largest share, network); unit builds events 1,665 s, daily_splits 1,158 s, boxscores 754 s, substitutions 319 s, box_accounts 76 s; quality check 39 s in all. Upstream 2026 holds only `2026SCHEDULE.CSV`.

Quality findings and fixes: rosters (5.16), substitutions (5.17), box_starters (5.18: 2021 Ohtani listed as DH and as pitcher in the all-star game; 1/28/23/18 duplicate rows in 2021/2022/2023/2025). After rebuilding rosters, substitutions and box accounts with the fixes, the quality check reported no finding for 2015-2025. No orphan player ids were found in events, box scores, daily splits or substitutions against the same season's rosters. Rosters against the Chadwick register were not checked (register not in the scratch lake). Finding R-28 (new task 3.4): unchanged raw files keep a stale chunk "current" after a schema change, so the stale Parquet was deleted by hand in the scratch lake before the rebuild.

## Evidence for 3.4 (schema change invalidates chunks)

Web check (2026-10-30, standard search; sources: https://dlthub.com/docs/api_reference/dlt/common/schema and https://dlthub.com/blog/schema-monitoring-with-metadata): dlt gives each schema a content-based `version_hash`, records it per load (`_dlt_loads.schema_version_hash`) and keeps the schema per version in `_dlt_version`. The same idea, applied per chunk, is `schema_sha256` in the processed manifest entry (ADR 49). Shared code: `core/stores.py` `schema_fingerprint`, `schema_matches`; used by `ProcessedStore.is_cached`, Lahman `_processed_is_current`, MLB API `_is_cached`. Tests: `tests/test_lake.py::test_a_schema_change_makes_a_stored_chunk_stale_without_refresh`, `tests/test_retrosheet_currency.py::test_a_chunk_written_under_another_schema_is_rebuilt_without_refresh`. Limit: a parser change that keeps the schema is not detected (ADR 49 consequences).


## Evidence for the export check (task 3.2, partly) and 5.19 (2026-10-30, scratch lake 2015-2026, this PC)

Targets run with read-back verification on: Parquet 23 datasets, 6,672,726 rows, 40 s, peak memory 1.28 GB, all verified. CSV: 20 datasets verified; `box_records` is refused by design (nested column `fields`); `events` and `events_postseason` first FAILED the read-back for every season: 20 text columns held `''` where a CSV round trip returns NULL (found by column-by-column diff of season 2020). Fix: the event parser stores NULL for an empty text field, with a test that fails without the fix. The stored events carried no digest and an unchanged schema, so the new `DatasetSpec.revision` (ADR 51) made the normal ingest rebuild them with no `--refresh` and no manual deletion (11 seasons, 70-230 s each at `-c 2`); after that CSV verified `events` (1,966,298 rows, 24 s) and `events_postseason` (34,949 rows). DuckDB: 20 datasets verified (3,425,349 rows, 59 s, peak 0.8 GB); `box_records` first failed the read-back type check (`varchar[]` not recognised as the list type), fixed in `sinks/dlt.py` `allowed_sql_types` with an export-level test; then `events`, `events_postseason` and `box_records` verified into one DuckDB file (3.25 million rows, 54 s, peak 0.86 GB). PostgreSQL (disposable embedded server): three datasets verified (68,805 rows, 35 s); `box_records` first failed at load (dlt's default CSV loader cannot write list columns), fixed by using the `insert_values` loader for nested columns (jsonb in PostgreSQL), tests on both databases that fail without the fix. The full PostgreSQL run of all datasets is recorded below when it finishes.
