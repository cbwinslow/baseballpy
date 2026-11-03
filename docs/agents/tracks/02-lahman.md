# Track 2: Lahman

OpenSpec change: `openspec/changes/lahman-source-review/`. Spec: `openspec/specs/lahman-database/`.
Docs: `docs/sources/lahman.md`. Code: `src/baseballpy/sources/lahman/`. Method: `docs/agents/WORK_BREAKDOWN.md`;
standing standards: `docs/DATA_WORKFLOW.md` (currency, export, onboarding checklist), `docs/agents/TOOLING.md`.

How to read a card: a step that does not apply is marked N/A with one sentence of reason; a step that
needs a decision from the owner is marked OWNER, the agent asks once (one short list) and moves on to
the next card. Tasks 1.x only look and report; every fix is a task 5.n.

Suspected findings to verify (not yet confirmed; the cards decide):
Review history: the first version of this plan was reviewed by an independent Opus 5.5 pass on 2026-10-29; its
findings that checked out against the code are built in below, and two of its claims were corrected (the count of
tables before `People` is 18, not 14; the first plan's "no fingerprints" claim was too strong).

- **L-A, data left behind (confirmed in code):** `extract_all` and the URL builder iterate the `LahmanTable` enum, not the git tree. The upstream repository also holds `data/readme2025.txt` (48 KB, the SABR data dictionary), `LICENSE` (22 KB), `README.md` and `.gitignore`; none is kept in `raw/`. `docs/DATA_LICENSES.md` defers the licence terms to `readme2025.txt`, which is never stored (cards L-01, L-07).
- **L-B, currency has two gaps (confirmed in code):** (1) an ETag is already stored (`RawStore.put` turns the response ETag into an ETag fingerprint), but `cache check --upstream` compares only git blob SHAs, so raw files report `not_checked`; locally imported files have no fingerprint at all. (2) `LahmanSource.get_table` returns the processed Parquet whenever it exists, before the extractor or upstream is asked, so fixing only the extractor changes nothing for users; `docs/sources/lahman.md` says a table fetched at a different ref is refetched, true only for the raw tier (cards L-04, L-05, L-06).
- **L-C, access:** `LahmanSource` has 13 named accessors and the generic `get_table(name)`; only 8 of 27 tables have top-level functions. There are no record classes (everything is a `pa.Table`). OWNER decision (card L-09): one generic top-level `lahman.table(name)` checked against the registry (recommended; keeps the 8 existing functions), or 27 named functions.
- **L-D, keys with NULLs:** composite registry keys include columns that can be empty (`AllstarFull.gameID`, `AwardsPlayers.notes`), so `export --mode merge` will be refused for those tables. Changing a key means changing `scripts/gen_schemas.py`: an OWNER decision (cards L-03, L-12).
- **L-E, descriptions:** 11 of 372 data columns in 4 datasets have no description (399 counting the 27 `_extras` columns; the scorecard in `PROJECT_MAP.md` uses the larger denominator). `readme2025.txt` may define them; cite the pinned commit, not `main` (card L-13).
- **L-F, adapter names:** the adapter takes table names from the `LahmanTable` enum, not the registry; the lists agree today (27 each) but nothing enforces it (card L-02).
- **L-G, quality checks are fragile (confirmed in code):** the orphan-player check runs only if `People` is already stored, and in enum (alphabetical) order 18 tables come before `People`, so a clean ingest never checks them; `_people_ids` re-reads `People` from disk for every table; only `playerID` is checked (not `teamID`, `franchID`, `parkkey`, `schoolID`); findings go to log warnings and manifest metadata, never to users (cards L-03, L-04).
- **L-H, the import path (confirmed in code):** `import_archive` keeps only `*.csv`, so the readme and licence of a supplied release are dropped; unknown CSV files become unregistered all-string tables; a partial import completed from the mirror mixes two releases silently (card L-08).
- **L-I, cross-source ids:** the only Lahman-to-Chadwick join in the tests is synthetic (`tests/test_database.py::test_cross_source_sql_join`, `key_bbref = bbrefID`); no real match rate is measured (card L-03).
- **L-J, export names:** Lahman column names mix case (`yearID`, `playerID`) and some start with a digit (`2B`, `3B`); every Chadwick column was snake_case. PostgreSQL naming through `dlt` and the type check (`information_schema` names) have never seen such names (card L-12).
- **L-K, small:** the raw manifest `records_count` counts lines including the header (off by one); `LahmanSource.__init__` calls `register_all()` (cheap since the Chadwick audit fix, but check).

Rules that never change for this source: Lahman data comes only from `cbwinslow/lahman-database-csv` or user-supplied data (never `chadwickbureau/baseballdatabank`; `tests/test_architecture.py` enforces it); `import_archive` keeps its zip-safety checks; the dual mode (remote mirror, local import) stays.

Results of L-01 to L-04 (2026-10-29; evidence in the change's design.md S1 to S4):
- **Confirmed:** L-A (documentation files not kept; licence is CC BY-SA 3.0 and is only deferred to the unkept readme), L-B (both cache tiers; plus the job-level `cache_hit` is never true), L-C (repeated calls re-read the Parquet: 6 to 18 ms each), L-D (exactly three tables have key columns with NULLs: `AllstarFull`, `AwardsPlayers`, `CollegePlaying`; 24 of 27 can merge), L-G and L-H (in code), L-K (records_count off by one, 0 on the file entry, a second chunk in the same manifest).
- **Refined:** L-F (all 27 registry, enum and generated names agree and every table is accepted by `--datasets`, but nothing pins the lists together and names are case-sensitive); L-I (measured: 99.94% of `bbrefID` and 99.85% of `retroID` match Chadwick; 4 people link to two different Chadwick persons; 14 and 36 ids unmatched).
- **Measured clean:** no duplicate keys, no mistyped columns, no empty strings, `_extras` empty, nothing quarantined, no `playerID` orphans; 5 `AllstarFull` rows have a (yearID, teamID) with no `Teams` row.
- **New:** unused async twins in the extractor; `cache check --upstream` prints a misleading message (shared tool, data-workflow-standard 2.9); `FieldingOFsplit.WP` and `ZR` are always empty; ShareAlike consequence for exports.
- **Still open for the review:** L-E and L-J (cards L-13 and L-12); the import path on a real SABR zip (OWNER may supply one).
- **Tasks added from the findings:** 5.6 to 5.9 (cards L-15 to L-18 at the end of this file). Owner decisions are collected in the change's design.md under "Owner decisions expected".

### L-01 Inventory the provider against the registry
- **Change task:** `lahman-source-review 1.1`
- **Stage:** S1
- **Executor:** Claude
- **Files:** docs/sources/lahman.md (hand-written part), the change's design.md
- **Tools (reuse check):** git tree listing (core/github_tree.py) or the provider's own listing, HttpClient; docs/references/
- **Inputs:** the pinned version (core/sources_lock.json) or the provider docs; `uv run baseballpy catalog list`
- **Steps:** 1. list every file, endpoint, parameter and documentation file the provider offers; 2. map each to a registered dataset, or mark it a gap with the reason (README, licence and data-dictionary files count: nothing is left behind); 3. read the provider's licence and data dictionary and write down which licence applies and what attribution it asks for; 4. if the source has a second way in (user-supplied files, an alternative mirror), inventory a real sample of that too; 5. compare the latest upstream version with the pin; record the inventory table in design.md.
- **Done when:** every upstream item is mapped or listed as a gap with a reason; the licence is named; `uv run baseballpy catalog status --gaps` for the source is pasted in design.md.
- **Record:** tick 1.1; design.md section S1.

### L-02 Check registry and adapter conformance
- **Change task:** `lahman-source-review 1.2`
- **Stage:** S2
- **Executor:** Claude
- **Files:** src/baseballpy/sources/lahman/adapter.py, tests/test_ingest_adapters.py (read only; fixes are tasks 5.n)
- **Tools (reuse check):** the dataset registry (core/datasets.py) is the only list of dataset names
- **Inputs:** `uv run baseballpy ingest lahman -d <name> --dry-run` for every registered dataset
- **Steps:** 1. reproduce: is every registered dataset accepted by --datasets, and unknown names rejected with the registry list?; 2. find every hard-coded list of dataset or table names in the source (adapter, extractor, api) and whether it agrees with the registry; 3. record the result; a disagreement becomes a task 5.n.
- **Done when:** the result for every registered dataset is in design.md; every disagreement has a task 5.n.
- **Record:** tick 1.2; design.md S2.

### L-03 Compare the generated schema with real data
- **Change task:** `lahman-source-review 1.3`
- **Stage:** S3
- **Executor:** Claude
- **Files:** design.md; regenerate with the source's generator in scripts/ only if a mismatch is proven (never hand-edit generated files)
- **Tools (reuse check):** Polars or pyarrow to profile the cached Parquet and the raw files, never a Python row loop
- **Inputs:** the source's tables.py (types), one clean ingest, docs/sources/lahman.md
- **Steps:** 1. profile every column: type, null rate, distinct values, ranges, sentinel-looking values (blank vs 0 vs a text marker), empty strings; 2. check uniqueness of every registry key and which key columns contain NULLs (a key with NULLs cannot be merged on export; changing a key is a generator change and an OWNER decision); 3. check every id column that points into another table or another source: orphan rows inside the source, and the match rate against the Chadwick register for player ids; 4. check _extras is empty and that drift is logged once; list era or provider quirks to document.
- **Done when:** a table in design.md with a verdict per column group and the measured match rates; every mismatch has a follow-up task 5.n or a regeneration commit.
- **Record:** tick 1.3; design.md S3.

### L-04 Review the code against the designated tools and decoupling rules
- **Change task:** `lahman-source-review 1.4`
- **Stage:** S4
- **Executor:** Claude (review only; no code change in this task)
- **Files:** read all of src/baseballpy/sources/lahman/
- **Tools (reuse check):** docs/agents/TOOLING.md rows: HTTP, parsing, dataframe code, concurrency, config
- **Inputs:** AGENTS.md sections 2, 4, 7, 8 and 14; tests/test_architecture.py
- **Steps:** 1. per module: what it does and which designated tool covers it; 2. flag Python loops over bulk data, hard-coded names, custom retry/hash/cache code, per-source special cases, swallowed errors, non-atomic writes; 3. list every cache shortcut (raw tier and processed tier) and say whether upstream is ever asked before it serves data; 4. check validation and quality code: does its result depend on load order, is it shown to users or only logged?; 5. measure load, first lookup and 1000 repeated calls of each public function on a real lake; look for registry, catalog or config work done on every call; 6. for each flag choose migrate (new task 5.n) or tool-cannot (one sentence of evidence).
- **Done when:** design.md has the per-module table, the cache-tier list and the timings; every migrate has a numbered follow-up task in tasks.md and a BACKLOG row.
- **Record:** tick 1.4; add tasks 5.n.

### L-05 Record upstream fingerprints for every raw file
- **Change task:** `lahman-source-review 5.1`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor, tests/test_lahman*.py
- **Tools (reuse check):** core/upstream.py (Fingerprint), RawStore.put(upstream=...), core/github_tree.py for git blob SHAs; the Chadwick extractor as the model
- **Inputs:** ADR 43; docs/DATA_WORKFLOW.md; `uv run baseballpy cache check --upstream --source lahman`
- **Steps:** 1. record the provider's fingerprint of every raw file: git blob SHA from the tree, else ETag or Last-Modified, else the content sha256; 2. files the user supplied keep their own origin marker; decide and document what `cache check --upstream` reports for them; 3. tests with respx that the fingerprints are stored; 4. run `cache check --upstream --source lahman` on a real lake.
- **Done when:** every remote raw file reports current or changed (not `no_fingerprint` or `not_checked`); local imports report a documented verdict; the tests pass.
- **Record:** tick 5.1; design.md S4.

### L-06 Decide currency with is_current() at every cache tier
- **Change task:** `lahman-source-review 5.2`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor and api modules, tests/test_lahman*.py; tick data-workflow-standard 2.5 in that change
- **Tools (reuse check):** core/upstream.py (is_current), the cache-tier list from task 1.4
- **Inputs:** ADR 43; the Chadwick extractor and register as the model
- **Steps:** 1. route every cache shortcut found in 1.4 (raw tier AND processed tier) through is_current(); fixing only the extractor leaves the processed tier serving stale data; 2. use the pinned fingerprint as `expected=` (reproducible mode) unless the owner decides the source should float with a time-to-live: OWNER decision, ask once, then continue; 3. tests with respx: fresh copy costs no request, changed fingerprint refetches, unreachable upstream serves the copy with a warning; 4. correct any documentation that claims behavior the code does not have.
- **Done when:** no cache shortcut bypasses is_current(); the old decision code is gone; the tests above pass; the docs state what is checked at each tier.
- **Record:** tick 5.2 and data-workflow-standard 2.5; design.md S4.

### L-07 Keep the provider's documentation files
- **Change task:** `lahman-source-review 5.3`
- **Stage:** S1
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** a shared helper in src/baseballpy/core/ (move Chadwick's DOCUMENT_FILES logic there), the source's extractor, docs/DATA_LICENSES.md, tests
- **Tools (reuse check):** RawStore.put with fingerprints; core/github_tree.py; AGENTS.md 14.2.4 (a helper used twice moves to core/)
- **Inputs:** the documentation files found in task 1.1 (README, licence, data dictionary)
- **Steps:** 1. keep each documentation file in raw/ with its sha256 and fingerprint through one shared helper that Chadwick and this source both use; 2. state the licence and the attribution text in docs/DATA_LICENSES.md from the kept text; 3. tests: the files are stored once, not downloaded again on a cached run, a failed download is logged and does not block the data.
- **Done when:** the files are in raw/ with hashes; Chadwick uses the same helper and its tests still pass; DATA_LICENSES names the licence.
- **Record:** tick 5.3; design.md S1.

### L-08 Review the second way in (user-supplied files); N/A if the source has none
- **Change task:** `lahman-source-review 5.4`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's import code, tests, docs/sources/lahman.md
- **Tools (reuse check):** the source's own safety checks stay; the registry decides which files are datasets
- **Inputs:** the sample inventoried in task 1.1
- **Steps:** 1. keep the non-data files (README, licence, data dictionary) of a supplied release, not only the data files; 2. detect a mixed release: a partial supplied set completed from the remote mirror must warn or refuse; 3. decide what unknown files in a supplied set become (reject, or keep raw only), never silent unregistered tables; 4. document how currency applies to supplied data.
- **Done when:** tests cover the partial import, the unknown file and the kept documents; or the card is marked N/A with one sentence.
- **Record:** tick 5.4; design.md S4.

### L-09 Make every dataset and column reachable from Python
- **Change task:** `lahman-source-review 5.5`
- **Stage:** S7
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** src/baseballpy/sources/lahman/__init__.py and api module, tests, docs/sources/lahman.md, docs/QUICKSTART.md
- **Tools (reuse check):** pyarrow tables from ProcessedStore; Polars/narwhals for lookups; a process-wide cache when lookups repeat (as ChadwickRegister.load does)
- **Inputs:** the registry (every dataset), the schema (every column); the access that already exists (do not rebuild it)
- **Steps:** 1. list datasets with no documented Python access; reuse the generic accessor if one exists, else add one driven by the registry and validated against it (OWNER decision if named functions per dataset are wanted instead); 2. if the source has record classes, add a schema-sync test that fails when a column is missing from them; otherwise mark this step N/A (tables only); 3. run every code block of docs/sources/lahman.md and the source's quickstart lines against a real lake and fix wrong examples.
- **Done when:** every registered dataset is readable with one documented call; every documented example ran; the new tests pass.
- **Record:** tick 5.5; docs updated.

### L-10 Close the spec and test gaps
- **Change task:** `lahman-source-review 2.1`
- **Stage:** S5
- **Executor:** agy writes tests from the findings, Claude reviews
- **Files:** openspec/changes/lahman-source-review/specs/lahman-database/spec.md (delta), tests/test_lahman*.py
- **Tools (reuse check):** respx for HTTP, hypothesis for parsing and lookups, fixtures under tests/fixtures/
- **Inputs:** the current spec requirements and every finding that changed behavior; start only when every task 5.n is done
- **Steps:** 1. one scenario per finding and per requirement without one; each ends with a `Verified by` line; 2. property tests where parsing or lookups are lossy; 3. confirm unit tests make no network call.
- **Done when:** `uv run pytest tests/test_spec_scenarios.py tests/test_lahman*.py -q` and `openspec validate --specs` pass.
- **Record:** tick 2.1; the delta stays in the change until the close task.

### L-11 Live verification on a clean scratch home
- **Change task:** `lahman-source-review 3.1`
- **Stage:** S6
- **Executor:** Claude
- **Files:** none in the repo; evidence goes into design.md
- **Tools (reuse check):** the CLI (ingest, cache check, catalog status, audit tail); no ad hoc scripts committed
- **Inputs:** about 120 GB free on this PC; set BASEBALLPY_HOME to a scratch folder and delete it afterwards
- **Steps:** 1. ingest the source from an empty home; note rows, bytes and seconds from audit.jsonl; 2. run again: nothing downloaded, audit shows cache_hit true; 3. `baseballpy cache check` and `cache check --upstream --source lahman`; 4. raw rows (minus any header line) against processed rows; spot-check known facts against the provider.
- **Done when:** counts, timings, the second-run result and the cache-check output are pasted in design.md.
- **Record:** tick 3.1; design.md S6.

### L-12 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source)
- **Change task:** `lahman-source-review 3.2`
- **Stage:** S7
- **Executor:** Claude
- **Files:** design.md; docs/sources/lahman.md (exceptions that apply)
- **Tools (reuse check):** baseballpy export (export.py): pyarrow files, native DuckDB, dlt PostgreSQL; embedded pgserver for PostgreSQL
- **Inputs:** the cached datasets from the live run; `uv run --with pgserver` or the dev dependency
- **Steps:** 1. export every dataset to parquet and csv, then duckdb and postgres, with verification on; 2. check that column names survive every target (mixed case, names that start with a digit, reserved words) and compare the names read back; 3. try --mode merge and note which datasets are refused (key with NULLs); 4. record rows, seconds and sizes; list the exceptions (nested columns, season partitions, size).
- **Done when:** every dataset verifies for every target or has a stated exception in the source page; numbers pasted in design.md.
- **Record:** tick 3.2; design.md S7.

### L-13 Cited column descriptions
- **Change task:** `lahman-source-review 3.3`
- **Stage:** S7
- **Executor:** Claude
- **Files:** scripts/build_column_descriptions.py (the source's builder), docs/columns/lahman.json (generated), docs/sources/lahman.md
- **Tools (reuse check):** the provider's own documentation (never invented text); `uv run baseballpy docs generate`
- **Inputs:** ADR 34; the description coverage in docs/agents/PROJECT_MAP.md (it counts _extras columns too: state which denominator you mean)
- **Steps:** 1. list undescribed columns; 2. add cited text for each column the provider defines, citing the pinned version of the document (not a moving branch); 3. list the columns the provider does not define in the source page.
- **Done when:** `uv run python scripts/build_column_descriptions.py lahman` run, `docs generate --check` clean, coverage not lower than before.
- **Record:** tick 3.3; design.md S7.

### L-14 Docs, decisions, spec merge, archive
- **Change task:** `lahman-source-review 4.1`
- **Stage:** S7
- **Executor:** Claude
- **Files:** docs/sources/lahman.md, docs/DECISIONS.md, openspec/specs/lahman-database/spec.md, this change directory (moved to archive/), BACKLOG.md, EXECUTION_ORDER.md
- **Tools (reuse check):** uv run baseballpy docs generate (never hand-type counts)
- **Inputs:** design.md of this change
- **Steps:** 1. update the hand-written parts of the source page (keys, quirks, access, export, currency); 2. one ADR per decision; 3. merge the spec delta into openspec/specs; 4. run all gates; move the change to openspec/changes/archive/<date>-lahman-source-review; update BACKLOG, EXECUTION_ORDER, PROJECT_MAP.
- **Done when:** gates green, `openspec validate --specs` passes, change archived, scorecard row complete.
- **Record:** tick 4.1 and archive the change.

## Cards created by the review (fixes found by L-01 to L-04)

### L-15 Quality checks that do not depend on load order and are visible to users
- **Change task:** `lahman-source-review 5.6`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** src/baseballpy/sources/lahman/quality.py, src/baseballpy/sources/lahman/api.py (`_quality`, `_people_ids`), the place chosen to show findings, tests/test_lahman_coverage.py, docs/sources/lahman.md
- **Tools (reuse check):** pyarrow compute (already used in quality.py); `baseballpy catalog status` or `doctor` for showing findings
- **Inputs:** design.md S3 and S4: measured results (no `playerID` orphans, 5 `AllstarFull` rows with no `Teams` row, none for `franchID`, `parkkey`, `schoolID`); the 18 tables that load before `People`
- **Steps:** 1. run the orphan checks after the tables of a run are stored, or read `People` once per run, so no table is skipped by load order; 2. add (yearID, teamID) against `Teams`, `franchID` against `TeamsFranchises`, `parkkey` against `Parks`, `schoolID` against `Schools`; 3. keep the findings in the processed manifest and show them to users in one named place (OWNER may prefer a different place: ask once); 4. tests with small fixtures, including a table that sorts before `People`.
- **Done when:** a clean ingest of the real data reports exactly the 5 `AllstarFull` rows and nothing else; the new tests pass.
- **Record:** tick 5.6; design.md S4.

### L-16 Pin the table-name lists together and decide case handling
- **Change task:** `lahman-source-review 5.7`
- **Stage:** S2
- **Executor:** agy (Claude reviews the full diff)
- **Files:** tests/test_lahman_coverage.py, src/baseballpy/sources/lahman/adapter.py and schema.py only if case-insensitive names are chosen
- **Tools (reuse check):** the dataset registry; `LahmanTable` stays (the spec requires the enum)
- **Inputs:** design.md S2 (27 names agree today; `batting` is rejected)
- **Steps:** 1. a test that fails when the enum, the registry and the generated tables disagree; 2. decide whether table names are accepted case-insensitively (recommended; OWNER, ask once) and implement it in one place with the canonical name reported back; 3. tests for both.
- **Done when:** `uv run pytest tests/test_lahman_coverage.py tests/test_ingest_adapters.py -q` passes and the lists cannot drift silently.
- **Record:** tick 5.7; design.md S2.

### L-17 One consistent raw manifest entry per file; remove unused duplicate code
- **Change task:** `lahman-source-review 5.8`
- **Stage:** S4
- **Executor:** agy (Claude reviews the full diff)
- **Files:** src/baseballpy/sources/lahman/extractor.py, tests/test_lahman_coverage.py
- **Tools (reuse check):** `RawStore.put` already writes the file entry (size, sha256, fingerprint)
- **Inputs:** design.md S4: `records_count` is the line count including the header on one chunk and 0 on the file entry; a second dataset-level chunk lives in the same manifest; `extract_table_async`, `extract_all` and `extract_all_async` have no callers
- **Steps:** 1. one entry per raw file; `records_count` means data rows or is omitted, the same way everywhere; 2. remove the unused extractor twins, or give them a caller and tests (decide with evidence); 3. keep the entry fields other code reads (check `cache_check.py`, `RawStore.verify`).
- **Done when:** the raw manifest of a clean ingest has one entry per file with consistent fields; `uv run pytest tests/test_lahman*.py tests/test_cache_check.py -q` passes.
- **Record:** tick 5.8; design.md S4.

### L-18 Ingest jobs report cache hits
- **Change task:** `lahman-source-review 5.9`
- **Stage:** S4
- **Executor:** agy (Claude reviews the full diff)
- **Files:** src/baseballpy/sources/lahman/adapter.py, src/baseballpy/sources/lahman/api.py (a way for `get_table` to say it came from the cache), tests/test_ingest_adapters.py
- **Tools (reuse check):** `JobResult.cache_hit` and the runner's audit tracker (built for Chadwick, ADR 43 follow-up)
- **Inputs:** design.md S4 (0 of 54 `ingest_job` events say cache hit)
- **Steps:** 1. let the table load report whether it was served from the cache; 2. the adapter sets `cache_hit` on the `JobResult`; 3. test with a cached and an uncached run.
- **Done when:** a second `uv run baseballpy ingest lahman` writes `cache_hit` true for every job in `audit.jsonl`.
- **Record:** tick 5.9; design.md S4.
