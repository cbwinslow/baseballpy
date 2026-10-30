# Track 3: Retrosheet

OpenSpec change: `openspec/changes/retrosheet-source-review/`. Spec: `openspec/specs/retrosheet-ingestion/`.
Docs: `docs/sources/retrosheet.md`. Code: `src/baseballpy/sources/retrosheet/`. Method: `docs/agents/WORK_BREAKDOWN.md`;
standing standards: `docs/DATA_WORKFLOW.md` (currency, export, onboarding checklist), `docs/agents/TOOLING.md`.

How to read a card: a step that does not apply is marked N/A with one sentence of reason; a step that
needs a decision from the owner is marked OWNER, the agent asks once (one short list) and moves on to
the next card. Tasks 1.x only look and report; every fix is a task 5.n.

Suspected findings to verify (not yet confirmed; the cards decide):
- (fill in from the survey in design.md)

### R-01 Inventory the provider against the registry
- **Change task:** `retrosheet-source-review 1.1`
- **Stage:** S1
- **Executor:** Claude
- **Files:** docs/sources/retrosheet.md (hand-written part), the change's design.md
- **Tools (reuse check):** git tree listing (core/github_tree.py) or the provider's own listing, HttpClient; docs/references/
- **Inputs:** the pinned version (core/sources_lock.json) or the provider docs; `uv run baseballpy catalog list`
- **Steps:** 1. list every file, endpoint, parameter and documentation file the provider offers; 2. map each to a registered dataset, or mark it a gap with the reason (README, licence and data-dictionary files count: nothing is left behind); 3. read the provider's licence and data dictionary and write down which licence applies and what attribution it asks for; 4. if the source has a second way in (user-supplied files, an alternative mirror), inventory a real sample of that too; 5. compare the latest upstream version with the pin; record the inventory table in design.md.
- **Done when:** every upstream item is mapped or listed as a gap with a reason; the licence is named; `uv run baseballpy catalog status --gaps` for the source is pasted in design.md.
- **Record:** tick 1.1; design.md section S1.

### R-02 Check registry and adapter conformance
- **Change task:** `retrosheet-source-review 1.2`
- **Stage:** S2
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/adapter.py, tests/test_ingest_adapters.py (read only; fixes are tasks 5.n)
- **Tools (reuse check):** the dataset registry (core/datasets.py) is the only list of dataset names
- **Inputs:** `uv run baseballpy ingest retrosheet -d <name> --dry-run` for every registered dataset
- **Steps:** 1. reproduce: is every registered dataset accepted by --datasets, and unknown names rejected with the registry list?; 2. find every hard-coded list of dataset or table names in the source (adapter, extractor, api) and whether it agrees with the registry; 3. record the result; a disagreement becomes a task 5.n.
- **Done when:** the result for every registered dataset is in design.md; every disagreement has a task 5.n.
- **Record:** tick 1.2; design.md S2.

### R-03 Compare the generated schema with real data
- **Change task:** `retrosheet-source-review 1.3`
- **Stage:** S3
- **Executor:** Claude
- **Files:** design.md; regenerate with the source's generator in scripts/ only if a mismatch is proven (never hand-edit generated files)
- **Tools (reuse check):** Polars or pyarrow to profile the cached Parquet and the raw files, never a Python row loop
- **Inputs:** the source's tables.py (types), one clean ingest, docs/sources/retrosheet.md
- **Steps:** 1. profile every column: type, null rate, distinct values, ranges, sentinel-looking values (blank vs 0 vs a text marker), empty strings; 2. check uniqueness of every registry key and which key columns contain NULLs (a key with NULLs cannot be merged on export; changing a key is a generator change and an OWNER decision); 3. check every id column that points into another table or another source: orphan rows inside the source, and the match rate against the Chadwick register for player ids; 4. check _extras is empty and that drift is logged once; list era or provider quirks to document.
- **Done when:** a table in design.md with a verdict per column group and the measured match rates; every mismatch has a follow-up task 5.n or a regeneration commit.
- **Record:** tick 1.3; design.md S3.

### R-04 Review the code against the designated tools and decoupling rules
- **Change task:** `retrosheet-source-review 1.4`
- **Stage:** S4
- **Executor:** Claude (review only; no code change in this task)
- **Files:** read all of src/baseballpy/sources/retrosheet/
- **Tools (reuse check):** docs/agents/TOOLING.md rows: HTTP, parsing, dataframe code, concurrency, config
- **Inputs:** AGENTS.md sections 2, 4, 7, 8 and 14; tests/test_architecture.py
- **Steps:** 1. per module: what it does and which designated tool covers it; 2. flag Python loops over bulk data, hard-coded names, custom retry/hash/cache code, per-source special cases, swallowed errors, non-atomic writes; 3. list every cache shortcut (raw tier and processed tier) and say whether upstream is ever asked before it serves data; 4. check validation and quality code: does its result depend on load order, is it shown to users or only logged?; 5. measure load, first lookup and 1000 repeated calls of each public function on a real lake; look for registry, catalog or config work done on every call; 6. for each flag choose migrate (new task 5.n) or tool-cannot (one sentence of evidence).
- **Done when:** design.md has the per-module table, the cache-tier list and the timings; every migrate has a numbered follow-up task in tasks.md and a BACKLOG row.
- **Record:** tick 1.4; add tasks 5.n.

### R-05 Record upstream fingerprints for every raw file
- **Change task:** `retrosheet-source-review 5.1`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor, tests/test_retrosheet*.py
- **Tools (reuse check):** core/upstream.py (Fingerprint), RawStore.put(upstream=...), core/github_tree.py for git blob SHAs; the Chadwick extractor as the model
- **Inputs:** ADR 43; docs/DATA_WORKFLOW.md; `uv run baseballpy cache check --upstream --source retrosheet`
- **Steps:** 1. record the provider's fingerprint of every raw file: git blob SHA from the tree, else ETag or Last-Modified, else the content sha256; 2. files the user supplied keep their own origin marker; decide and document what `cache check --upstream` reports for them; 3. tests with respx that the fingerprints are stored; 4. run `cache check --upstream --source retrosheet` on a real lake.
- **Done when:** every remote raw file reports current or changed (not `no_fingerprint` or `not_checked`); local imports report a documented verdict; the tests pass.
- **Record:** tick 5.1; design.md S4.

### R-06 Decide currency with is_current() at every cache tier
- **Change task:** `retrosheet-source-review 5.2`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor and api modules, tests/test_retrosheet*.py; tick data-workflow-standard 2.6 in that change
- **Tools (reuse check):** core/upstream.py (is_current), the cache-tier list from task 1.4
- **Inputs:** ADR 43; the Chadwick extractor and register as the model
- **Steps:** 1. route every cache shortcut found in 1.4 (raw tier AND processed tier) through is_current(); fixing only the extractor leaves the processed tier serving stale data; 2. use the pinned fingerprint as `expected=` (reproducible mode) unless the owner decides the source should float with a time-to-live: OWNER decision, ask once, then continue; 3. tests with respx: fresh copy costs no request, changed fingerprint refetches, unreachable upstream serves the copy with a warning; 4. correct any documentation that claims behavior the code does not have.
- **Done when:** no cache shortcut bypasses is_current(); the old decision code is gone; the tests above pass; the docs state what is checked at each tier.
- **Record:** tick 5.2 and data-workflow-standard 2.6; design.md S4.

### R-07 Keep the provider's documentation files
- **Change task:** `retrosheet-source-review 5.3`
- **Stage:** S1
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** a shared helper in src/baseballpy/core/ (move Chadwick's DOCUMENT_FILES logic there), the source's extractor, docs/DATA_LICENSES.md, tests
- **Tools (reuse check):** RawStore.put with fingerprints; core/github_tree.py; AGENTS.md 14.2.4 (a helper used twice moves to core/)
- **Inputs:** the documentation files found in task 1.1 (README, licence, data dictionary)
- **Steps:** 1. keep each documentation file in raw/ with its sha256 and fingerprint through one shared helper that Chadwick and this source both use; 2. state the licence and the attribution text in docs/DATA_LICENSES.md from the kept text; 3. tests: the files are stored once, not downloaded again on a cached run, a failed download is logged and does not block the data.
- **Done when:** the files are in raw/ with hashes; Chadwick uses the same helper and its tests still pass; DATA_LICENSES names the licence.
- **Record:** tick 5.3; design.md S1.

### R-08 Review the second way in (user-supplied files); N/A if the source has none
- **Change task:** `retrosheet-source-review 5.4`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's import code, tests, docs/sources/retrosheet.md
- **Tools (reuse check):** the source's own safety checks stay; the registry decides which files are datasets
- **Inputs:** the sample inventoried in task 1.1
- **Steps:** 1. keep the non-data files (README, licence, data dictionary) of a supplied release, not only the data files; 2. detect a mixed release: a partial supplied set completed from the remote mirror must warn or refuse; 3. decide what unknown files in a supplied set become (reject, or keep raw only), never silent unregistered tables; 4. document how currency applies to supplied data.
- **Done when:** tests cover the partial import, the unknown file and the kept documents; or the card is marked N/A with one sentence.
- **Record:** tick 5.4; design.md S4.

### R-09 Make every dataset and column reachable from Python
- **Change task:** `retrosheet-source-review 5.5`
- **Stage:** S7
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** src/baseballpy/sources/retrosheet/__init__.py and api module, tests, docs/sources/retrosheet.md, docs/QUICKSTART.md
- **Tools (reuse check):** pyarrow tables from ProcessedStore; Polars/narwhals for lookups; a process-wide cache when lookups repeat (as ChadwickRegister.load does)
- **Inputs:** the registry (every dataset), the schema (every column); the access that already exists (do not rebuild it)
- **Steps:** 1. list datasets with no documented Python access; reuse the generic accessor if one exists, else add one driven by the registry and validated against it (OWNER decision if named functions per dataset are wanted instead); 2. if the source has record classes, add a schema-sync test that fails when a column is missing from them; otherwise mark this step N/A (tables only); 3. run every code block of docs/sources/retrosheet.md and the source's quickstart lines against a real lake and fix wrong examples.
- **Done when:** every registered dataset is readable with one documented call; every documented example ran; the new tests pass.
- **Record:** tick 5.5; docs updated.

### R-10 Close the spec and test gaps
- **Change task:** `retrosheet-source-review 2.1`
- **Stage:** S5
- **Executor:** agy writes tests from the findings, Claude reviews
- **Files:** openspec/changes/retrosheet-source-review/specs/retrosheet-ingestion/spec.md (delta), tests/test_retrosheet*.py
- **Tools (reuse check):** respx for HTTP, hypothesis for parsing and lookups, fixtures under tests/fixtures/
- **Inputs:** the current spec requirements and every finding that changed behavior; start only when every task 5.n is done
- **Steps:** 1. one scenario per finding and per requirement without one; each ends with a `Verified by` line; 2. property tests where parsing or lookups are lossy; 3. confirm unit tests make no network call.
- **Done when:** `uv run pytest tests/test_spec_scenarios.py tests/test_retrosheet*.py -q` and `openspec validate --specs` pass.
- **Record:** tick 2.1; the delta stays in the change until the close task.

### R-11 Live verification on a clean scratch home
- **Change task:** `retrosheet-source-review 3.1`
- **Stage:** S6
- **Executor:** Claude
- **Files:** none in the repo; evidence goes into design.md
- **Tools (reuse check):** the CLI (ingest, cache check, catalog status, audit tail); no ad hoc scripts committed
- **Inputs:** about 120 GB free on this PC; set BASEBALLPY_HOME to a scratch folder and delete it afterwards
- **Steps:** 1. ingest the source from an empty home; note rows, bytes and seconds from audit.jsonl; 2. run again: nothing downloaded, audit shows cache_hit true; 3. `baseballpy cache check` and `cache check --upstream --source retrosheet`; 4. raw rows (minus any header line) against processed rows; spot-check known facts against the provider.
- **Done when:** counts, timings, the second-run result and the cache-check output are pasted in design.md.
- **Record:** tick 3.1; design.md S6.

### R-12 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source)
- **Change task:** `retrosheet-source-review 3.2`
- **Stage:** S7
- **Executor:** Claude
- **Files:** design.md; docs/sources/retrosheet.md (exceptions that apply)
- **Tools (reuse check):** baseballpy export (export.py): pyarrow files, native DuckDB, dlt PostgreSQL; embedded pgserver for PostgreSQL
- **Inputs:** the cached datasets from the live run; `uv run --with pgserver` or the dev dependency
- **Steps:** 1. export every dataset to parquet and csv, then duckdb and postgres, with verification on; 2. check that column names survive every target (mixed case, names that start with a digit, reserved words) and compare the names read back; 3. try --mode merge and note which datasets are refused (key with NULLs); 4. record rows, seconds and sizes; list the exceptions (nested columns, season partitions, size).
- **Done when:** every dataset verifies for every target or has a stated exception in the source page; numbers pasted in design.md.
- **Record:** tick 3.2; design.md S7.

### R-13 Cited column descriptions
- **Change task:** `retrosheet-source-review 3.3`
- **Stage:** S7
- **Executor:** Claude
- **Files:** scripts/build_column_descriptions.py (the source's builder), docs/columns/retrosheet.json (generated), docs/sources/retrosheet.md
- **Tools (reuse check):** the provider's own documentation (never invented text); `uv run baseballpy docs generate`
- **Inputs:** ADR 34; the description coverage in docs/agents/PROJECT_MAP.md (it counts _extras columns too: state which denominator you mean)
- **Steps:** 1. list undescribed columns; 2. add cited text for each column the provider defines, citing the pinned version of the document (not a moving branch); 3. list the columns the provider does not define in the source page.
- **Done when:** `uv run python scripts/build_column_descriptions.py retrosheet` run, `docs generate --check` clean, coverage not lower than before.
- **Record:** tick 3.3; design.md S7.

### R-14 Docs, decisions, spec merge, archive
- **Change task:** `retrosheet-source-review 4.1`
- **Stage:** S7
- **Executor:** Claude
- **Files:** docs/sources/retrosheet.md, docs/DECISIONS.md, openspec/specs/retrosheet-ingestion/spec.md, this change directory (moved to archive/), BACKLOG.md, EXECUTION_ORDER.md
- **Tools (reuse check):** uv run baseballpy docs generate (never hand-type counts)
- **Inputs:** design.md of this change
- **Steps:** 1. update the hand-written parts of the source page (keys, quirks, access, export, currency); 2. one ADR per decision; 3. merge the spec delta into openspec/specs; 4. run all gates; move the change to openspec/changes/archive/<date>-retrosheet-source-review; update BACKLOG, EXECUTION_ORDER, PROJECT_MAP.
- **Done when:** gates green, `openspec validate --specs` passes, change archived, scorecard row complete.
- **Record:** tick 4.1 and archive the change.

### R-15 Store every event field chadwickpy emits and key events on (GAME_ID, EVENT_ID)
- **Change task:** `retrosheet-source-review 5.6`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/parser.py, schema.py, tables.py (generated; change scripts/gen_schemas.py, not the file), sources/retrosheet/catalog.py, scripts/gen_schemas.py, tests/test_retrosheet*.py
- **Tools (reuse check):** chadwickpy output is the type source; pyarrow casts; types come from data, never column names (CLAUDE.md)
- **Inputs:** Opus finding R-F1/R-F2 (design.md): the parser loops over 98 schema fields, chadwickpy returns 164, EVENT_ID (cwevent field 96, standard) is dropped; owner decision D1 = A (ADR 48)
- **Steps:** 1. list chadwickpy's keys on a fixture game and on a real season sample; 2. extend the generated schema to all of them, typed from data; 3. unknown future keys go to `_extras` with the one-time drift warning; 4. drop or justify the always-NULL `ERR*_FLD_CD_NEW` columns; 5. registry key `(GAME_ID, EVENT_ID)` for events, events_postseason, events_deduced; check the keys of substitutions and daily_splits the same way; 6. replace the per-field Python loop with a vectorised cast where the fixture shows identical output.
- **Done when:** `uv run pytest tests/test_retrosheet*.py -q` passes with a test that every chadwickpy key is a column and no key repeats on a multi-play game; `uv run baseballpy export` merge keeps every play
- **Record:** tick 5.6; design.md.

### R-16 One declarative dataset-to-producer map: every registry name works with --datasets, one download per ingest
- **Change task:** `retrosheet-source-review 5.7`
- **Stage:** S2
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/adapter.py, api.py, tests/test_ingest_adapters.py, tests/test_retrosheet_coverage.py
- **Tools (reuse check):** dataset registry (core/datasets.py) is the only list of names
- **Inputs:** Opus finding R-F6/R-F7: `KNOWN_DATASETS` rejects 14 of 25 registry names; `-d events` without seasons plans nothing; `refresh` downloads event files 5 times per season
- **Steps:** 1. one table registry name -> (producer, chunk, raw kinds needed); 2. adapter and `ingest_season` read it; 3. an unknown name is rejected with the registry list, missing seasons fail with an instruction; 4. download the needed kinds once per ingest and pass refresh=False to inner calls.
- **Done when:** `uv run pytest tests/test_ingest_adapters.py tests/test_retrosheet_coverage.py -q` passes; a test plans every registry name and counts HTTP requests per file
- **Record:** tick 5.7; design.md.

### R-17 No silent loss in game logs and rosters: quarantine short rows, keep extra fields in _extras
- **Change task:** `retrosheet-source-review 5.8`
- **Stage:** S3
- **Executor:** agy (Claude reviews the full diff)
- **Files:** src/baseballpy/sources/retrosheet/parser.py, tests/test_retrosheet*.py
- **Tools (reuse check):** core/quarantine.py, `_extras` JSON column
- **Inputs:** Opus finding R-F8; owner decision D3 = A (ADR 48): `parser.py` skips game-log rows under 10 fields, cuts fields past 161 and roster fields past 7
- **Steps:** 1. a short row goes to quarantine with its raw line and the report counts it; 2. fields past the schema go to `_extras`; 3. remove dead `team_code` code or give it a caller.
- **Done when:** `uv run pytest tests/test_retrosheet*.py -q` passes with tests for a short game-log row, a 171-field row and an 8-field roster row
- **Record:** tick 5.8; design.md.

### R-18 Box parser: keep repeated info keys, safe dates, BoxParseError for bad numbers
- **Change task:** `retrosheet-source-review 5.9`
- **Stage:** S4
- **Executor:** agy (Claude reviews the full diff)
- **Files:** src/baseballpy/sources/retrosheet/box_parser.py, tests/test_retrosheet_box.py
- **Tools (reuse check):** stdlib datetime.strptime; BoxParseError
- **Inputs:** Opus finding R-F9: a repeated `info` key overwrites the first value; `1950/4/1` crashes the season; bare ValueError on a bad version or int; docstring says 21 counting stats, the code has 17
- **Steps:** 1. a repeated key is kept (list in `_extras` or a `box_records` row) so every line stays accounted for (ADR 33); 2. parse dates with strptime, quarantine the bad ones; 3. wrap int errors in BoxParseError; 4. fix the docstring.
- **Done when:** `uv run pytest tests/test_retrosheet_box.py -q` passes with `test_repeated_info_keys_are_kept` and tests for an unpadded date and a bad int
- **Record:** tick 5.9; design.md.

### R-19 Shared stores: an empty rebuild removes the stale Parquet; stale .part files cleaned in processed/; quarantine follows the source's lake
- **Change task:** `retrosheet-source-review 5.10`
- **Stage:** S4
- **Executor:** Claude
- **Files:** src/baseballpy/core/stores.py, core/quarantine.py, src/baseballpy/sources/retrosheet/downloader.py, tests/test_stores*.py
- **Tools (reuse check):** core/atomic.py cleanup_stale_parts
- **Inputs:** Opus finding R-F10, R-F15, R-F18 (shared code, every source benefits); `put_stream` with an empty stream keeps the old part file, `is_cached` then serves old rows
- **Steps:** 1. empty stream unlinks the old part and records 0 rows; 2. `cleanup_stale_parts` also runs on processed/ for Retrosheet like Statcast and MLB; 3. quarantine writes under the LakeConfig of the source; 4. run the full test suite because the code is shared.
- **Done when:** `uv run pytest -q` passes with a test that an empty rebuild leaves no old rows and a test for the quarantine location
- **Record:** tick 5.10; design.md.

### R-20 Export streams one season at a time
- **Change task:** `retrosheet-source-review 5.11`
- **Stage:** S4
- **Executor:** Claude
- **Files:** src/baseballpy/export.py, src/baseballpy/sinks/*.py (only if needed), tests/test_export.py
- **Tools (reuse check):** pyarrow, dlt; ADR 46 verify-after-write stays
- **Inputs:** Opus finding R-F11; owner decision D4 = A: `_slices` reads every season into a list before writing, `events` is about 115 seasons
- **Steps:** 1. make `_slices` a generator, write each season, drop it; 2. verification reads back per season and compares totals; 3. measure peak memory on a many-season dataset in a test or manual run.
- **Done when:** `uv run pytest tests/test_export.py -q` passes; a test shows peak memory does not grow with the number of seasons
- **Record:** tick 5.11; design.md.

### R-21 Really stream box scores and box accounts; count rows without re-reading Parquet
- **Change task:** `retrosheet-source-review 5.12`
- **Stage:** S4
- **Executor:** agy (Claude reviews the full diff)
- **Files:** src/baseballpy/sources/retrosheet/api.py, tests/test_retrosheet_coverage.py
- **Tools (reuse check):** ProcessedStore.put_stream returns the row count
- **Inputs:** Opus finding R-F12: `boxscores()` and `box_accounts()` hold a whole season in memory; `_read` and `ingest_season` re-read Parquet to count rows
- **Steps:** 1. feed pairs into two writers batch by batch; 2. use the row count returned by `put_stream`; 3. correct the spec and docs wording on streaming.
- **Done when:** `uv run pytest tests/test_retrosheet_coverage.py tests/test_retrosheet_box.py -q` passes; no whole-season list in the two functions
- **Record:** tick 5.12; design.md.

### R-22 Data-quality checks across datasets, shown by catalog status
- **Change task:** `retrosheet-source-review 5.13`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/quality.py (new), api.py, tests/test_retrosheet_quality.py (new)
- **Tools (reuse check):** Lahman's `quality.py` is the model (one declarative table, one generic function); Chadwick register `key_retro` for player ids
- **Inputs:** Opus finding R-F14: no key-duplicate check, no check of player ids against the register, no check of `box_games.game_id` against `gamelogs`
- **Steps:** 1. a FOREIGN_KEYS table; 2. one generic function independent of load order; 3. findings reach users through `catalog status`; 4. measure the real match rates on the homelab lake (2015 to 2024) in card R-11.
- **Done when:** `uv run pytest tests/test_retrosheet_quality.py -q` passes; `uv run baseballpy catalog status` shows the findings
- **Record:** tick 5.13; design.md.

### R-23 boxscores_batting has no unique key: a player who re-enters in the same slot gets two rows
- **Change task:** `retrosheet-source-review 5.14`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/parser.py (boxscores), schema.py, src/baseballpy/sources/catalog.py, tests/test_retrosheet_events.py
- **Tools (reuse check):** chadwickpy `box_create` output order; core/quality.py duplicate_rows
- **Inputs:** design.md 5.13 evidence: 1925 and 1935 samples each hold one game where the same player appears twice with the same (game, team, player, slot, position) in separate stints; (game_id, team_id, player_id, slot) is therefore not unique and `export --mode merge` would keep one of the two rows
- **Steps:** 1. look at the two games in the raw files and decide what the second row means (a second stint); 2. add a per-(game, team, slot) appearance sequence column so the key is unique, or document why not; 3. measure on the homelab lake; 4. update the registry key and the generated docs.
- **Done when:** `uv run pytest tests/test_retrosheet_events.py -q` passes with a test of a re-entering player, and the key is unique on the six sample files.
- **Record:** tick 5.14; design.md.

### R-24 Audit-log and time every Retrosheet operation
- **Change task:** `retrosheet-source-review 5.15`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/downloader.py, api.py, tests/test_retrosheet_audit.py (new)
- **Tools (reuse check):** `core/audit.py` `default_audit_logger.track` (already used by Lahman, Chadwick, MLB API, Statcast); no new code path
- **Inputs:** before this task only `download_season` was logged; tree listing, single files, documents, unit builds (parse and store), quality checks and the season and reference ingests were not
- **Steps:** 1. wrap each operation in `track`; 2. one test that reads the events back; 3. use the events to read timings from the live run in card R-11.
- **Done when:** `uv run pytest tests/test_retrosheet_audit.py -q` passes; `baseballpy audit` shows the new operations after an ingest
- **Record:** tick 5.15; design.md.

### R-25 rosters key is not unique: the all-star rosters repeat club lines
- **Change task:** `retrosheet-source-review 5.16`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/parser.py, schema.py, src/baseballpy/sources/catalog.py, tests/test_retrosheet_rows.py
- **Tools (reuse check):** core/quality.py duplicate_rows (found it)
- **Inputs:** the live 2015-2026 run reported rosters duplicate_key_rows=76 (2015) and 79 (2016); ALS and NLS roster files repeat each player's club line exactly
- **Steps:** 1. add a roster column (file team code); 2. key (year, roster, player_id); 3. rebuild and re-measure.
- **Done when:** `uv run pytest tests/test_retrosheet_rows.py -q` passes; the quality check reports no duplicate roster rows on the live lake
- **Record:** tick 5.16; design.md.

### R-26 substitutions key is not unique: a player who changes position in one stoppage gets two rows
- **Change task:** `retrosheet-source-review 5.17`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/catalog.py, tests/test_retrosheet_events.py
- **Tools (reuse check):** the existing quality check found it (no new code)
- **Inputs:** live run: substitutions duplicate_key_rows=1 for 2018 (TBA201805080, event 53: wendj002 enters at 2B, then moves to SS in the same stoppage)
- **Steps:** 1. add SUB_FLD_CD to the key; 2. test a position change; 3. re-measure on the live lake (the quality check stays the safety net).
- **Done when:** `uv run pytest tests/test_retrosheet_events.py -q` passes; no duplicate substitution rows on the live lake
- **Record:** tick 5.17; design.md.

### R-27 box_starters key is not unique: a two-way player is listed twice in a lineup
- **Change task:** `retrosheet-source-review 5.18`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/catalog.py, tests/test_retrosheet_box.py
- **Tools (reuse check):** the existing quality check found it
- **Inputs:** live run: box_starters duplicate_key_rows of 1 (2021), 28 (2022), 23 (2023), 18 (2025); 2021 all-star game lists Ohtani as DH (order 1, position 10) and as pitcher (order 0, position 1)
- **Steps:** 1. add position to the key; 2. test; 3. rebuild the scratch lake and re-check.
- **Done when:** `uv run pytest tests/test_retrosheet_box.py -q` passes; no duplicates on the live lake 2015-2025 (checked 2026-10-30: none)
- **Record:** tick 5.18; design.md.

### R-28 Processed chunks are not rebuilt when the parser or schema changes
- **Change task:** `retrosheet-source-review 3.4`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/core/stores.py, src/baseballpy/sources/retrosheet/api.py, openspec spec delta, ADR
- **Tools (reuse check):** core/upstream.py Fingerprint (add a schema/parser fingerprint kind); check how Lahman and Chadwick handle it
- **Inputs:** after the 5.16-5.18 schema and key changes the unchanged raw files still looked current, so the stale Parquet had to be deleted by hand in the scratch lake; a user upgrading would silently keep old-shaped files
- **Steps:** 1. web-search how dlt and others version transforms; 2. store a schema fingerprint in the chunk manifest and treat a mismatch as not current; 3. test; 4. ADR.
- **Done when:** a test changes the schema and sees the chunk rebuilt without `--refresh`
- **Record:** tick 3.4; ADR.

### R-29 Event text fields: missing means NULL; a parser revision replaces older chunks
- **Change task:** `retrosheet-source-review 5.19`
- **Stage:** S7
- **Executor:** Claude
- **Files:** src/baseballpy/sources/retrosheet/parser.py, src/baseballpy/core/datasets.py (`revision`), src/baseballpy/core/stores.py (`spec_fingerprint`), src/baseballpy/sources/catalog.py, tests/test_retrosheet_events.py, tests/test_lake.py
- **Tools (reuse check):** the export read-back verification found it; ADR 49 digest extended (a value fix keeps the columns, so the schema digest cannot see it)
- **Inputs:** card R-12 run: `export --to csv` failed its read-back check for events and events_postseason in every season; 20 text columns hold `''` where the CSV round trip returns NULL
- **Steps:** 1. empty text becomes NULL in the event parser; 2. `DatasetSpec.revision` goes into the stored digest, and a spec with a revision distrusts digest-less chunks; 3. rebuild events on the scratch lake through the normal ingest (no manual deletion); 4. rerun the CSV export.
- **Done when:** `uv run pytest tests/test_retrosheet_events.py tests/test_lake.py -q` passes; the test fails without the fix; `export retrosheet --to csv` verifies events on the scratch lake
- **Record:** tick 5.19; design.md; ADR 51.
