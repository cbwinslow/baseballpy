# Design: statcast-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/04-statcast.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Surveyed 2026-10-30 (facts only; the cards decide what is a finding).

- **Provider:** Baseball Savant (baseballsavant.mlb.com): the pitch search CSV (`statcast_search/csv`, 25,000-row cap, windows bisected) and 36 leaderboard routes plus the `pitches_minors` search (`minors=true`, 2021+). No git pin; currency is by response hash or window (ADR 43 applies, upstream fingerprints for HTTP sources are ETag, Last-Modified or the content hash).
- **Registry:** 38 datasets: `pitches` and `pitches_minors` (season-partitioned) and 36 `leaderboard_*` datasets (34 season-partitioned, 2 without a season), all default ingest. Game feeds are kept as raw bytes (no processed dataset).
- **Code:** `sources/statcast/` is 2,995 lines in 11 files (`extractor.py` 567, `lb_catalog.py` 499, `leaderboards.py` 345, `schema.py` 220, `adapter.py` 142, `game_feed.py` 137, `normalizer.py` 113; generated `lb_tables.py` 828).
- **Tests:** `test_statcast.py`, `test_statcast_coverage.py`, `test_statcast_grid.py`, `test_statcast_minors.py`, `test_statcast_pitches.py`.
- **Spec:** `openspec/specs/statcast-ingestion/spec.md` has nine requirements (pitch search completeness, leaderboard registry, season ingest, game feed, embedded-page leaderboards, season game feeds, minor-league pitches, aligned windows, verified `unsupported` verdicts).
- **Docs:** `docs/sources/statcast.md` (1,686 lines); column descriptions in `docs/columns/statcast.json` (`pitches` 110, `pitches_minors` 110, shared `*` 17).
- **Already known from the Retrosheet review (apply as checks, not assumptions):** keys must be unique on real rows; every operation must be audit-logged; text empty vs NULL must round-trip through CSV; a CSV export of each dataset must verify; chunks must carry the schema digest (ADR 49) and a `revision` when a value fix keeps the columns (ADR 51); no hard-coded seasons (the pitch window runs to the current season, 2026 opens at the start of the season).
- **Lessons recorded before this review:** `year=` is silently ignored by some leaderboard routes (the probe compares payload hashes across seasons); Savant's minor-league pitches start in 2021; the 2023 season window also holds postseason and exhibition games (2,955 `game_pk` for 2,430 regular-season games), not duplicates.

## S1 inventory
Checked 2026-10-30. `baseballpy catalog audit --source statcast` (live: the provider's leaderboard listing against the registry) reports "No findings": every leaderboard Savant lists is registered (36 datasets) or recorded `unsupported` with evidence; the pitch search (`statcast_search/csv`), its minor-league variant (`minors=true`) and the per-game feed (`/gf?game_pk=`, raw bytes by design) are the other three ways in. The data dictionary `https://baseballsavant.mlb.com/csv-docs` answers 200 and is the cited source of the pitch column descriptions (`docs/columns/statcast.json`, 110 + 110 + 17 shared). Licence: MLBAM's copyright notice limits bulk use (`docs/DATA_LICENSES.md`). There is no second way in (no user-supplied files). There is no git pin: upstream change detection is by response content (ADR 43).

## S2 conformance
Registry and adapter conformance tests pass (`tests/test_statcast*.py`, `tests/test_architecture.py`, `tests/test_ingest_contract.py`: 5 Statcast test files plus the two architecture files, all green in the full suite). The adapter reaches the runner only through `IngestAdapter`; no other source imports Statcast code.

## S3 schema and types
Live run on a scratch home (`baseballpy_sc`), `ingest statcast -s 2025 -c 2`, 2026-10-30: 3 jobs completed, exit 0, 1,036 s of job time. `pitches` 868,045 rows in 51 parts (442 s), `pitches_minors` 865,017 rows in 38 parts (516 s), 36 leaderboards 23,256 rows (78 s, 36 audit events). No value went to quarantine, no `schema_drift` warning. The registered pitch key `(game_pk, at_bat_number, pitch_number)` is unique on all 868,045 and all 865,017 rows with no NULL key part; every leaderboard key is unique; no text column holds an empty string. Savant's row cap forced 8 window bisections (logged as RETRY events), no truncation.

## S4 code review against the designated tools
Reuse check per module (`sources/statcast/`): `extractor.py` uses `HttpClient`, pyarrow and the shared audit logger (async track around each window plus a bisect event); `leaderboards.py` uses `HttpClient`, the registry (`lb_catalog.py`) and `track`; `lb_parse.py` uses stdlib `csv` and `json` for the small embedded-page payloads (pyarrow CSV is used on the pitch path); `game_feed.py` used `HttpClient` and `RawStore` but wrote no audit event: finding, fixed by task 5.6 (S-15, test fails without the change). No hard-coded season lists were found in `src/` (the seasons come from the caller or the MLB calendar).

## S5 tests and spec gaps
All `Verified by` citations in the spec deltas name tests that exist (checked with the rule of `tests/test_spec_scenarios.py` before the merge). The deltas (audit logging, raw fingerprints, schema-following chunks, provider documentation, Python access; data-export read-back) are merged into `openspec/specs/statcast-ingestion/spec.md` and `openspec/specs/data-export/spec.md`. Full suite: 1,160 passed, 5 skipped; `openspec validate --specs`: 16 passed.

## S6 live verification
Scratch home `baseballpy_sc`, `ingest statcast -s 2025 -c 2`, 2026-10-30: 3 jobs completed, exit 0; `pitches` 868,045 rows (442 s), `pitches_minors` 865,017 rows (516 s), 36 leaderboards 23,256 rows (79 s); no quarantine, no schema drift; all registered keys unique; no empty-string text; 8 Savant row-cap bisections handled without truncation. 2026 data: the 2026 regular season and postseason are complete upstream but were not ingested in this run (not verified); the planner takes any season from the calendar, no code change is needed.

## S7 access, export, descriptions, docs, close
Export with read-back verification (this PC, scratch home): Parquet 38 datasets (the leaderboards 22,585 rows in 18 s plus `pitches` and `pitches_minors` 868,045 + 865,017 rows in 18 s, peak 2.0 GB); CSV 38 verified (30 s, peak 1.8 GB); DuckDB 38 verified (1,756,318 rows, 37 s, peak 1.76 GB); PostgreSQL (disposable embedded server) 38 verified (1,756,318 rows, 236 s, peak 2.0 GB). The only defect the checks found: Parquet and CSV read-back of the pitch datasets failed because the 51 stored parts each carry their own dictionary for the dictionary-encoded text columns (task 5.7, fixed, test fails without the change). No dataset has a nested column, so no export exception applies.

Column descriptions (task 3.3): 255 of 939 Statcast columns are described (`pitches` and `pitches_minors` from Savant's data dictionary, shared leaderboard columns from the MLB glossary, 17 exact-name matches); the other 684 leaderboard columns have no definition on any page found in the earlier search (task 2.1 of `column-descriptions-retrosheet-and-leaderboards`, B-17), so none is invented. 2026-10-30: the glossary has not been re-searched.

## 5.1 evidence (2026-10-30)
Savant sends no version marker on the pitch CSV or the leaderboards, so the raw manifests held no fingerprint. `core/upstream.py` gains `content_fingerprint` and `response_fingerprint` (ETag when present, else the payload sha256); the three raw writes (pitch windows, leaderboards, game feeds) pass it as `upstream`. Three tests fail without the change. `RawStore.put` itself is unchanged (other sources keep their own markers).

## 5.2 evidence (2026-10-30)
Cache tiers: raw (content/ETag fingerprint from 5.1; Savant offers no version marker, so past seasons are immutable and the trailing days of the current season are always refetched) and processed (pitch windows and leaderboards judged by the freshness policy). Finding: neither processed tier looked at the schema digest, so a column change left old chunks in place. Both now call `schema_matches` (ADR 49/51) before reuse. Tests fail without the change.

## 5.7 evidence (export read-back, 2026-10-30)
`export statcast --to parquet` and `--to csv` failed the read-back for `pitches` and `pitches_minors` ('data read back differs from the source') while the duckdb export verified. Column-by-column diff of season 2025: 14 dictionary-encoded text columns (`game_type`, `home_team`, `pitch_type`, `events`, ...) differ only in how the dictionaries are laid out: the 51 stored parts each carry their own dictionary, and Arrow's `equals` compares dictionaries. Fix: `export._decoded` compares dictionary columns as plain values. Test `tests/test_export.py::test_dictionary_columns_with_different_dictionaries_per_stored_part_verify` (parquet and csv) fails without the change. After the fix: Parquet 868,045 + 865,017 rows verified in 18 s (peak 2.0 GB), CSV in 30 s (peak 1.8 GB).

## 5.3 and 5.4 evidence (2026-10-30)
Savant publishes one documentation page, the pitch data dictionary `csv-docs` (the cited source of the column descriptions). It was not kept; a new `documents` job (`StatcastExtractor.keep_documents`, shared `core/documents.keep_pages`) stores it in `raw/statcast/documents/` with sha256 and fingerprint, once per lake, audit-logged. Leaderboard pages have no separate documentation. 5.4: not applicable, Statcast has no user-supplied-file path.

## 5.5 evidence (2026-10-30)
Only the leaderboards had a by-name entry point (`get_leaderboard`); pitches needed the extractor. `sources/statcast/access.py` adds `table(name, season)` and `datasets()` (registry-driven; leaderboards are found through the `LEADERBOARDS` table, no hard-coded names). Tests in the spec delta.
