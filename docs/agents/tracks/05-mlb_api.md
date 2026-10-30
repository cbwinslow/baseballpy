# Track 5: MLB API

OpenSpec change: `openspec/changes/mlb_api-source-review/`. Spec: `openspec/specs/mlb-api-ingestion/`.
Docs: `docs/sources/mlb_api.md`. Code: `src/baseballpy/sources/mlb_api/`. Method: `docs/agents/WORK_BREAKDOWN.md`;
standing standards: `docs/DATA_WORKFLOW.md` (currency, export, onboarding checklist), `docs/agents/TOOLING.md`.

How to read a card: a step that does not apply is marked N/A with one sentence of reason; a step that
needs a decision from the owner is marked OWNER, the agent asks once (one short list) and moves on to
the next card. Tasks 1.x only look and report; every fix is a task 5.n.

Suspected findings to verify (not yet confirmed; the cards decide):
- (fill in from the survey in design.md)

### M-01 Inventory the provider against the registry
- **Change task:** `mlb_api-source-review 1.1`
- **Stage:** S1
- **Executor:** Claude
- **Files:** docs/sources/mlb_api.md (hand-written part), the change's design.md
- **Tools (reuse check):** git tree listing (core/github_tree.py) or the provider's own listing, HttpClient; docs/references/
- **Inputs:** the pinned version (core/sources_lock.json) or the provider docs; `uv run baseballpy catalog list`
- **Steps:** 1. list every file, endpoint, parameter and documentation file the provider offers; 2. map each to a registered dataset, or mark it a gap with the reason (README, licence and data-dictionary files count: nothing is left behind); 3. read the provider's licence and data dictionary and write down which licence applies and what attribution it asks for; 4. if the source has a second way in (user-supplied files, an alternative mirror), inventory a real sample of that too; 5. compare the latest upstream version with the pin; record the inventory table in design.md.
- **Done when:** every upstream item is mapped or listed as a gap with a reason; the licence is named; `uv run baseballpy catalog status --gaps` for the source is pasted in design.md.
- **Record:** tick 1.1; design.md section S1.

### M-02 Check registry and adapter conformance
- **Change task:** `mlb_api-source-review 1.2`
- **Stage:** S2
- **Executor:** Claude
- **Files:** src/baseballpy/sources/mlb_api/adapter.py, tests/test_ingest_adapters.py (read only; fixes are tasks 5.n)
- **Tools (reuse check):** the dataset registry (core/datasets.py) is the only list of dataset names
- **Inputs:** `uv run baseballpy ingest mlb_api -d <name> --dry-run` for every registered dataset
- **Steps:** 1. reproduce: is every registered dataset accepted by --datasets, and unknown names rejected with the registry list?; 2. find every hard-coded list of dataset or table names in the source (adapter, extractor, api) and whether it agrees with the registry; 3. record the result; a disagreement becomes a task 5.n.
- **Done when:** the result for every registered dataset is in design.md; every disagreement has a task 5.n.
- **Record:** tick 1.2; design.md S2.

### M-03 Compare the generated schema with real data
- **Change task:** `mlb_api-source-review 1.3`
- **Stage:** S3
- **Executor:** Claude
- **Files:** design.md; regenerate with the source's generator in scripts/ only if a mismatch is proven (never hand-edit generated files)
- **Tools (reuse check):** Polars or pyarrow to profile the cached Parquet and the raw files, never a Python row loop
- **Inputs:** the source's tables.py (types), one clean ingest, docs/sources/mlb_api.md
- **Steps:** 1. profile every column: type, null rate, distinct values, ranges, sentinel-looking values (blank vs 0 vs a text marker), empty strings; 2. check uniqueness of every registry key and which key columns contain NULLs (a key with NULLs cannot be merged on export; changing a key is a generator change and an OWNER decision); 3. check every id column that points into another table or another source: orphan rows inside the source, and the match rate against the Chadwick register for player ids; 4. check _extras is empty and that drift is logged once; list era or provider quirks to document.
- **Done when:** a table in design.md with a verdict per column group and the measured match rates; every mismatch has a follow-up task 5.n or a regeneration commit.
- **Record:** tick 1.3; design.md S3.

### M-04 Review the code against the designated tools and decoupling rules
- **Change task:** `mlb_api-source-review 1.4`
- **Stage:** S4
- **Executor:** Claude (review only; no code change in this task)
- **Files:** read all of src/baseballpy/sources/mlb_api/
- **Tools (reuse check):** docs/agents/TOOLING.md rows: HTTP, parsing, dataframe code, concurrency, config
- **Inputs:** AGENTS.md sections 2, 4, 7, 8 and 14; tests/test_architecture.py
- **Steps:** 1. per module: what it does and which designated tool covers it; 2. flag Python loops over bulk data, hard-coded names, custom retry/hash/cache code, per-source special cases, swallowed errors, non-atomic writes; 3. list every cache shortcut (raw tier and processed tier) and say whether upstream is ever asked before it serves data; 4. check validation and quality code: does its result depend on load order, is it shown to users or only logged?; 5. measure load, first lookup and 1000 repeated calls of each public function on a real lake; look for registry, catalog or config work done on every call; 6. for each flag choose migrate (new task 5.n) or tool-cannot (one sentence of evidence).
- **Done when:** design.md has the per-module table, the cache-tier list and the timings; every migrate has a numbered follow-up task in tasks.md and a BACKLOG row.
- **Record:** tick 1.4; add tasks 5.n.

### M-05 Record upstream fingerprints for every raw file
- **Change task:** `mlb_api-source-review 5.1`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor, tests/test_mlb_api*.py
- **Tools (reuse check):** core/upstream.py (Fingerprint), RawStore.put(upstream=...), core/github_tree.py for git blob SHAs; the Chadwick extractor as the model
- **Inputs:** ADR 43; docs/DATA_WORKFLOW.md; `uv run baseballpy cache check --upstream --source mlb_api`
- **Steps:** 1. record the provider's fingerprint of every raw file: git blob SHA from the tree, else ETag or Last-Modified, else the content sha256; 2. files the user supplied keep their own origin marker; decide and document what `cache check --upstream` reports for them; 3. tests with respx that the fingerprints are stored; 4. run `cache check --upstream --source mlb_api` on a real lake.
- **Done when:** every remote raw file reports current or changed (not `no_fingerprint` or `not_checked`); local imports report a documented verdict; the tests pass.
- **Record:** tick 5.1; design.md S4.

### M-06 Decide currency with is_current() at every cache tier
- **Change task:** `mlb_api-source-review 5.2`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor and api modules, tests/test_mlb_api*.py; tick data-workflow-standard 2.8 in that change
- **Tools (reuse check):** core/upstream.py (is_current), the cache-tier list from task 1.4
- **Inputs:** ADR 43; the Chadwick extractor and register as the model
- **Steps:** 1. route every cache shortcut found in 1.4 (raw tier AND processed tier) through is_current(); fixing only the extractor leaves the processed tier serving stale data; 2. use the pinned fingerprint as `expected=` (reproducible mode) unless the owner decides the source should float with a time-to-live: OWNER decision, ask once, then continue; 3. tests with respx: fresh copy costs no request, changed fingerprint refetches, unreachable upstream serves the copy with a warning; 4. correct any documentation that claims behavior the code does not have.
- **Done when:** no cache shortcut bypasses is_current(); the old decision code is gone; the tests above pass; the docs state what is checked at each tier.
- **Record:** tick 5.2 and data-workflow-standard 2.8; design.md S4.

### M-07 Keep the provider's documentation files
- **Change task:** `mlb_api-source-review 5.3`
- **Stage:** S1
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** a shared helper in src/baseballpy/core/ (move Chadwick's DOCUMENT_FILES logic there), the source's extractor, docs/DATA_LICENSES.md, tests
- **Tools (reuse check):** RawStore.put with fingerprints; core/github_tree.py; AGENTS.md 14.2.4 (a helper used twice moves to core/)
- **Inputs:** the documentation files found in task 1.1 (README, licence, data dictionary)
- **Steps:** 1. keep each documentation file in raw/ with its sha256 and fingerprint through one shared helper that Chadwick and this source both use; 2. state the licence and the attribution text in docs/DATA_LICENSES.md from the kept text; 3. tests: the files are stored once, not downloaded again on a cached run, a failed download is logged and does not block the data.
- **Done when:** the files are in raw/ with hashes; Chadwick uses the same helper and its tests still pass; DATA_LICENSES names the licence.
- **Record:** tick 5.3; design.md S1.

### M-08 Review the second way in (user-supplied files); N/A if the source has none
- **Change task:** `mlb_api-source-review 5.4`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's import code, tests, docs/sources/mlb_api.md
- **Tools (reuse check):** the source's own safety checks stay; the registry decides which files are datasets
- **Inputs:** the sample inventoried in task 1.1
- **Steps:** 1. keep the non-data files (README, licence, data dictionary) of a supplied release, not only the data files; 2. detect a mixed release: a partial supplied set completed from the remote mirror must warn or refuse; 3. decide what unknown files in a supplied set become (reject, or keep raw only), never silent unregistered tables; 4. document how currency applies to supplied data.
- **Done when:** tests cover the partial import, the unknown file and the kept documents; or the card is marked N/A with one sentence.
- **Record:** tick 5.4; design.md S4.

### M-09 Make every dataset and column reachable from Python
- **Change task:** `mlb_api-source-review 5.5`
- **Stage:** S7
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** src/baseballpy/sources/mlb_api/__init__.py and api module, tests, docs/sources/mlb_api.md, docs/QUICKSTART.md
- **Tools (reuse check):** pyarrow tables from ProcessedStore; Polars/narwhals for lookups; a process-wide cache when lookups repeat (as ChadwickRegister.load does)
- **Inputs:** the registry (every dataset), the schema (every column); the access that already exists (do not rebuild it)
- **Steps:** 1. list datasets with no documented Python access; reuse the generic accessor if one exists, else add one driven by the registry and validated against it (OWNER decision if named functions per dataset are wanted instead); 2. if the source has record classes, add a schema-sync test that fails when a column is missing from them; otherwise mark this step N/A (tables only); 3. run every code block of docs/sources/mlb_api.md and the source's quickstart lines against a real lake and fix wrong examples.
- **Done when:** every registered dataset is readable with one documented call; every documented example ran; the new tests pass.
- **Record:** tick 5.5; docs updated.

### M-10 Close the spec and test gaps
- **Change task:** `mlb_api-source-review 2.1`
- **Stage:** S5
- **Executor:** agy writes tests from the findings, Claude reviews
- **Files:** openspec/changes/mlb_api-source-review/specs/mlb-api-ingestion/spec.md (delta), tests/test_mlb_api*.py
- **Tools (reuse check):** respx for HTTP, hypothesis for parsing and lookups, fixtures under tests/fixtures/
- **Inputs:** the current spec requirements and every finding that changed behavior; start only when every task 5.n is done
- **Steps:** 1. one scenario per finding and per requirement without one; each ends with a `Verified by` line; 2. property tests where parsing or lookups are lossy; 3. confirm unit tests make no network call.
- **Done when:** `uv run pytest tests/test_spec_scenarios.py tests/test_mlb_api*.py -q` and `openspec validate --specs` pass.
- **Record:** tick 2.1; the delta stays in the change until the close task.

### M-11 Live verification on a clean scratch home
- **Change task:** `mlb_api-source-review 3.1`
- **Stage:** S6
- **Executor:** Claude
- **Files:** none in the repo; evidence goes into design.md
- **Tools (reuse check):** the CLI (ingest, cache check, catalog status, audit tail); no ad hoc scripts committed
- **Inputs:** about 120 GB free on this PC; set BASEBALLPY_HOME to a scratch folder and delete it afterwards
- **Steps:** 1. ingest the source from an empty home; note rows, bytes and seconds from audit.jsonl; 2. run again: nothing downloaded, audit shows cache_hit true; 3. `baseballpy cache check` and `cache check --upstream --source mlb_api`; 4. raw rows (minus any header line) against processed rows; spot-check known facts against the provider.
- **Done when:** counts, timings, the second-run result and the cache-check output are pasted in design.md.
- **Record:** tick 3.1; design.md S6.

### M-12 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source)
- **Change task:** `mlb_api-source-review 3.2`
- **Stage:** S7
- **Executor:** Claude
- **Files:** design.md; docs/sources/mlb_api.md (exceptions that apply)
- **Tools (reuse check):** baseballpy export (export.py): pyarrow files, native DuckDB, dlt PostgreSQL; embedded pgserver for PostgreSQL
- **Inputs:** the cached datasets from the live run; `uv run --with pgserver` or the dev dependency
- **Steps:** 1. export every dataset to parquet and csv, then duckdb and postgres, with verification on; 2. check that column names survive every target (mixed case, names that start with a digit, reserved words) and compare the names read back; 3. try --mode merge and note which datasets are refused (key with NULLs); 4. record rows, seconds and sizes; list the exceptions (nested columns, season partitions, size).
- **Done when:** every dataset verifies for every target or has a stated exception in the source page; numbers pasted in design.md.
- **Record:** tick 3.2; design.md S7.

### M-13 Cited column descriptions
- **Change task:** `mlb_api-source-review 3.3`
- **Stage:** S7
- **Executor:** Claude
- **Files:** scripts/build_column_descriptions.py (the source's builder), docs/columns/mlb_api.json (generated), docs/sources/mlb_api.md
- **Tools (reuse check):** the provider's own documentation (never invented text); `uv run baseballpy docs generate`
- **Inputs:** ADR 34; the description coverage in docs/agents/PROJECT_MAP.md (it counts _extras columns too: state which denominator you mean)
- **Steps:** 1. list undescribed columns; 2. add cited text for each column the provider defines, citing the pinned version of the document (not a moving branch); 3. list the columns the provider does not define in the source page.
- **Done when:** `uv run python scripts/build_column_descriptions.py mlb_api` run, `docs generate --check` clean, coverage not lower than before.
- **Record:** tick 3.3; design.md S7.

### M-14 Docs, decisions, spec merge, archive
- **Change task:** `mlb_api-source-review 4.1`
- **Stage:** S7
- **Executor:** Claude
- **Files:** docs/sources/mlb_api.md, docs/DECISIONS.md, openspec/specs/mlb-api-ingestion/spec.md, this change directory (moved to archive/), BACKLOG.md, EXECUTION_ORDER.md
- **Tools (reuse check):** uv run baseballpy docs generate (never hand-type counts)
- **Inputs:** design.md of this change
- **Steps:** 1. update the hand-written parts of the source page (keys, quirks, access, export, currency); 2. one ADR per decision; 3. merge the spec delta into openspec/specs; 4. run all gates; move the change to openspec/changes/archive/<date>-mlb_api-source-review; update BACKLOG, EXECUTION_ORDER, PROJECT_MAP.
- **Done when:** gates green, `openspec validate --specs` passes, change archived, scorecard row complete.
- **Record:** tick 4.1 and archive the change.

### M-15 No hard-coded default season; standings honour refresh
- **Change task:** `mlb_api-source-review 5.6`
- **Stage:** S3
- **Executor:** Claude
- **Files:** src/baseballpy/sources/mlb_api/api.py, extractor.py, tests/test_mlb_api.py
- **Tools (reuse check):** `LakeConfig.today_or_now()` (the calendar; testable)
- **Inputs:** card M-04 review: nine signatures defaulted `season`/`year` to 2024; `extract_standings` dropped `refresh`
- **Steps:** 1. default to None and resolve the current season in the extractor; 2. pass `refresh` through; 3. a test with a fixed calendar.
- **Done when:** `uv run pytest tests/test_mlb_api.py -q` passes and fails without the change
- **Record:** tick 5.6; design.md S4.

### M-16 One refused request must not abort the season job
- **Change task:** `mlb_api-source-review 5.7`
- **Stage:** S6
- **Executor:** Claude
- **Files:** src/baseballpy/sources/mlb_api/generic.py, adapter.py, tests/test_mlb_coverage.py
- **Tools (reuse check):** existing `JobResult` failed status and `EndpointReport`; no new mechanism
- **Inputs:** card M-11 live run 2026-10-30: the season job failed at the first league-wide `v1/stats` (HTTP 406) and stored nothing of the other default endpoints
- **Steps:** 1. catch the refusal per request, keep going, report it; 2. the adapter ends the job as failed with detail and rows; 3. rerun the live season.
- **Done when:** the test passes and fails without the change; the live 2025 season stores every endpoint the provider answers
- **Record:** tick 5.7; design.md S6.
