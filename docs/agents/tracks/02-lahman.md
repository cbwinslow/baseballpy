# Track 2: Lahman

OpenSpec change: `openspec/changes/lahman-source-review/`. Spec: `openspec/specs/lahman-database/`.
Docs: `docs/sources/lahman.md`. Code: `src/baseballpy/sources/lahman/`. Method: `docs/agents/WORK_BREAKDOWN.md`;
standing standards: `docs/DATA_WORKFLOW.md` (currency, export, onboarding checklist), `docs/agents/TOOLING.md`.

Suspected findings to verify (not yet confirmed; the cards decide):
- **L-A, data left behind:** the extractor builds file URLs from the `LahmanTable` enum, not from the git tree. The upstream repository also holds `data/readme2025.txt` (48 KB, the SABR data dictionary), `LICENSE` (22 KB), `README.md` and `.gitignore`; none is kept in `raw/` (cards L-01, L-10).
- **L-B, own currency logic:** `LahmanExtractor._is_cached` compares `source_ref` and applies a never-expires TTL; no upstream fingerprint is stored, so `cache check --upstream` cannot see a changed Lahman file (card L-05, data-workflow-standard 2.5).
- **L-C, access gap:** only 8 of 27 tables have top-level functions (`lahman.batting()` and so on) and `LahmanSource` has 12 accessors; the other tables are reachable only through `get_table(name)` (card L-06).
- **L-D, composite keys with NULLs:** registry keys are composite (for example `AllstarFull`: 6 columns, `AwardsPlayers`: 5 including `notes`); a key column with NULLs means `export --mode merge` will be refused for that table (cards L-03, L-09).
- **L-E, descriptions:** 11 of 372 columns in 4 datasets have no description; `readme2025.txt` may define them (card L-10).
- **L-F, adapter names:** the adapter takes table names from the `LahmanTable` enum, not the registry; the two lists agree today (27 each) but nothing enforces it (card L-02).

Rules that never change for this source: Lahman data comes only from `cbwinslow/lahman-database-csv` or user-supplied data (never `chadwickbureau/baseballdatabank`; `tests/test_architecture.py` enforces it); `import_archive` keeps its zip-safety checks; the dual mode (remote mirror, local import) stays.

### L-01 Inventory the provider against the registry
- **Change task:** `lahman-source-review 1.1`
- **Stage:** S1
- **Executor:** Claude
- **Files:** docs/sources/lahman.md (hand-written part), the change's design.md
- **Tools (reuse check):** git tree listing (core/github_tree.py) or the provider's own listing, HttpClient; docs/references/
- **Inputs:** the pinned version (core/sources_lock.json) or the provider docs; `uv run baseballpy catalog list`
- **Steps:** 1. list every file, endpoint, parameter and documentation file the provider offers; 2. map each to a registered dataset, or mark it a gap with the reason (documentation, licence and README files count: nothing is left behind); 3. compare the latest upstream version with the pin; 4. record the inventory table in design.md.
- **Done when:** every upstream item is mapped or listed as a gap with a reason; `uv run baseballpy catalog status --gaps` for the source is pasted in design.md.
- **Record:** tick 1.1; design.md section S1.

### L-02 Check registry and adapter conformance
- **Change task:** `lahman-source-review 1.2`
- **Stage:** S2
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** src/baseballpy/sources/lahman/adapter.py, tests/test_ingest_adapters.py
- **Tools (reuse check):** the dataset registry (core/datasets.py) is the only list of dataset names
- **Inputs:** `uv run baseballpy ingest lahman -d <name> --dry-run` for every registered dataset
- **Steps:** 1. reproduce: is every registered dataset accepted by --datasets, and unknown names rejected with the registry list?; 2. derive names from the registry (no hard-coded dataset lists); 3. test the accepted and the rejected path.
- **Done when:** `uv run pytest tests/test_ingest_adapters.py tests/test_ingest_contract.py tests/test_architecture.py -q` passes and no dataset name literal list remains in the adapter.
- **Record:** tick 1.2; design.md S2.

### L-03 Compare the generated schema with real data
- **Change task:** `lahman-source-review 1.3`
- **Stage:** S3
- **Executor:** Claude
- **Files:** design.md; regenerate with the source's generator in scripts/ only if a mismatch is proven (never hand-edit generated files)
- **Tools (reuse check):** Polars or pyarrow to profile the cached Parquet and the raw files, never a Python row loop
- **Inputs:** the source's tables.py (types), one clean ingest, docs/sources/lahman.md
- **Steps:** 1. profile every column: type, null rate, distinct values, ranges, sentinel-looking values, empty strings; 2. check uniqueness of every registry key and which key columns contain NULLs (a key with NULLs cannot be merged on export); 3. check _extras is empty and that drift is logged once; 4. list era or provider quirks to document.
- **Done when:** a table in design.md with a verdict per column group; every mismatch has a follow-up task or a regeneration commit.
- **Record:** tick 1.3; design.md S3.

### L-04 Review the code against the designated tools and decoupling rules
- **Change task:** `lahman-source-review 1.4`
- **Stage:** S4
- **Executor:** Claude (review), agy (mechanical migrations it approves)
- **Files:** read all of src/baseballpy/sources/lahman/; edit only files a follow-up task names
- **Tools (reuse check):** docs/agents/TOOLING.md rows: HTTP, parsing, dataframe code, concurrency, config
- **Inputs:** AGENTS.md sections 2, 4, 7, 8 and 14; tests/test_architecture.py
- **Steps:** 1. per module: what it does and which designated tool covers it; 2. flag Python loops over bulk data, hard-coded names, custom retry/hash/cache code, per-source special cases, swallowed errors, non-atomic writes; 3. measure load, first lookup and ingest times on a real lake; 4. for each flag choose migrate (new task 5.n) or tool-cannot (one sentence of evidence); no code change in this task.
- **Done when:** design.md has the per-module table and timings; every migrate has a numbered follow-up task in tasks.md and a BACKLOG row.
- **Record:** tick 1.4; add tasks 5.n.

### L-05 Move the source onto the shared currency check
- **Change task:** `lahman-source-review 1.5`
- **Stage:** S4
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** the source's extractor, tests/test_lahman*.py; tick data-workflow-standard 2.5 in that change
- **Tools (reuse check):** core/upstream.py (Fingerprint, is_current), RawStore.put(upstream=...), core/github_tree.py for git blob SHAs
- **Inputs:** ADR 43; docs/DATA_WORKFLOW.md; the Chadwick extractor as the model
- **Steps:** 1. record the provider's fingerprint of every raw file (git blob SHA, ETag or Last-Modified, content sha256); 2. replace the source's own 'is my copy current' logic with is_current(); keep a time-to-live only for how often to ask; 3. tests with respx: fresh copy costs no request, changed fingerprint refetches, unreachable upstream serves the copy with a warning; 4. run `uv run baseballpy cache check --upstream --source lahman` on a real lake.
- **Done when:** no raw file of the source reports `no_fingerprint`; the old decision code is gone; the tests above pass.
- **Record:** tick 1.5 and data-workflow-standard 2.5; design.md S4.

### L-06 Make every dataset and column reachable from Python
- **Change task:** `lahman-source-review 1.6`
- **Stage:** S7
- **Executor:** Claude designs, agy codes (review the full diff)
- **Files:** src/baseballpy/sources/lahman/__init__.py and api module, tests, docs/sources/lahman.md, docs/QUICKSTART.md
- **Tools (reuse check):** pyarrow tables from ProcessedStore; Polars/narwhals for lookups; a process-wide cache when lookups repeat (as ChadwickRegister.load does)
- **Inputs:** the registry (every dataset), the schema (every column)
- **Steps:** 1. list datasets and columns with no Python access (top-level function or documented accessor) and records that lack columns; 2. add a generic accessor driven by the registry instead of one hand-written function per dataset; 3. add a schema-sync test that fails when a regenerated column is missing from a record class; 4. run every example in the docs against a real lake.
- **Done when:** every registered dataset is readable with one documented call and every column is on the record types; `uv run pytest` for the new tests passes.
- **Record:** tick 1.6; docs updated.

### L-07 Close the spec and test gaps
- **Change task:** `lahman-source-review 2.1`
- **Stage:** S5
- **Executor:** agy writes tests from the findings, Claude reviews
- **Files:** openspec/changes/lahman-source-review/specs/lahman-database/spec.md (delta), tests/test_lahman*.py
- **Tools (reuse check):** respx for HTTP, hypothesis for parsing and lookups, fixtures under tests/fixtures/
- **Inputs:** the current spec requirements and every finding that changed behavior
- **Steps:** 1. one scenario per finding and per requirement without one; each ends with a `Verified by` line; 2. property tests where parsing or lookups are lossy; 3. confirm unit tests make no network call.
- **Done when:** `uv run pytest tests/test_spec_scenarios.py tests/test_lahman*.py -q` and `openspec validate --specs` pass.
- **Record:** tick 2.1; the delta stays in the change until the close task.

### L-08 Live verification on a clean scratch home
- **Change task:** `lahman-source-review 3.1`
- **Stage:** S6
- **Executor:** Claude
- **Files:** none in the repo; evidence goes into design.md
- **Tools (reuse check):** the CLI (ingest, cache check, catalog status, audit tail); no ad hoc scripts committed
- **Inputs:** about 120 GB free on this PC; set BASEBALLPY_HOME to a scratch folder and delete it afterwards
- **Steps:** 1. ingest the source from an empty home; note rows, bytes and seconds from audit.jsonl; 2. run again: nothing downloaded, audit shows cache_hit true; 3. `baseballpy cache check` and `cache check --upstream --source lahman`; 4. raw rows against processed rows; spot-check known facts against the provider.
- **Done when:** counts, timings, the second-run result and the cache-check output are pasted in design.md.
- **Record:** tick 3.1; design.md S6.

### L-09 Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source)
- **Change task:** `lahman-source-review 3.2`
- **Stage:** S7
- **Executor:** Claude
- **Files:** design.md; docs/sources/lahman.md (exceptions that apply)
- **Tools (reuse check):** baseballpy export (export.py): pyarrow files, native DuckDB, dlt PostgreSQL; embedded pgserver for PostgreSQL
- **Inputs:** the cached datasets from the live run; `uv run --with pgserver` or the dev dependency
- **Steps:** 1. export every dataset to parquet and csv, then duckdb and postgres, with verification on; 2. try --mode merge and note which datasets are refused (key with NULLs); 3. record rows, seconds and sizes; list the exceptions (nested columns, season partitions, size).
- **Done when:** every dataset verifies for every target or has a stated exception in the source page; numbers pasted in design.md.
- **Record:** tick 3.2; design.md S7.

### L-10 Cited column descriptions
- **Change task:** `lahman-source-review 3.3`
- **Stage:** S7
- **Executor:** Claude
- **Files:** scripts/build_column_descriptions.py (the source's builder), docs/columns/lahman.json (generated), docs/sources/lahman.md
- **Tools (reuse check):** the provider's own documentation (never invented text); `uv run baseballpy docs generate`
- **Inputs:** ADR 34; the current description coverage in docs/agents/PROJECT_MAP.md
- **Steps:** 1. list undescribed columns; 2. add cited text for each column the provider defines, with the source URL; 3. list the columns the provider does not define in the source page.
- **Done when:** `uv run python scripts/build_column_descriptions.py lahman` run, `docs generate --check` clean, coverage not lower than before.
- **Record:** tick 3.3; design.md S7.

### L-11 Docs, decisions, spec merge, archive
- **Change task:** `lahman-source-review 4.1`
- **Stage:** S7
- **Executor:** Claude
- **Files:** docs/sources/lahman.md, docs/DECISIONS.md, openspec/specs/lahman-database/spec.md, this change directory (moved to archive/), BACKLOG.md, EXECUTION_ORDER.md
- **Tools (reuse check):** uv run baseballpy docs generate (never hand-type counts)
- **Inputs:** design.md of this change
- **Steps:** 1. update the hand-written parts of the source page (keys, quirks, access, export, currency); 2. one ADR per decision; 3. merge the spec delta into openspec/specs; 4. run all gates; move the change to openspec/changes/archive/<date>-lahman-source-review; update BACKLOG, EXECUTION_ORDER, PROJECT_MAP.
- **Done when:** gates green, `openspec validate --specs` passes, change archived, scorecard row complete.
- **Record:** tick 4.1 and archive the change.
