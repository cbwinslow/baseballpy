# Track 1: Chadwick Register (first source under review)

OpenSpec change: `openspec/changes/chadwick-source-review/`. Spec: `openspec/specs/chadwick-register/`.
Docs: `docs/sources/chadwick.md`. Code: `src/baseballpy/sources/chadwick/` (adapter, extractor,
normalizer, register, schema, generated `tables.py`). Method: `docs/agents/WORK_BREAKDOWN.md`.

Why first: smallest source, and `AGENTS.md` 3A routes every player-ID resolution through it. Four
datasets are registered (`register`, `register_names`, `register_links`, `register_countries`); the
upstream repository is `chadwickbureau/register`, files under `data/` at a pinned SHA
(`core/sources_lock.json`).

Status 2026-10-29 (final, incl. the audit change chadwick-complete-access): ALL cards C-01 to C-14 are done and the change is archived (openspec/changes/archive/2026-10-29-chadwick-source-review). Earlier status: C-01 to C-04 were done (evidence in the change's `design.md`). Results:
- CONFIRMED: `ChadwickAdapter.KNOWN_DATASETS = {"register"}` rejects `register_names`, `register_links`
  and `register_countries`; the job also builds a 9.6 s Python index just to count rows (C-09, C-10).
- CONFIRMED bug: `resolve_id` returns the `key_bbref` value for `BBREF_MINORS` and cannot start from
  `BBREF_MINORS`, `NPB` or `WIKIDATA` (C-11).
- CONFIRMED: the index is a 526,894-row Python loop; `PlayerRecord.key_npb` is typed `str` but is `int`;
  duplicate ids would be overwritten silently (C-12).
- CONFIRMED: hand-typed nickname table and an 11 s fuzzy search where DuckDB/Polars can do it (C-13).
- CONFIRMED gap: the upstream README is not kept, and the spec calls `key_person` the UUID (C-14).
- REFUTED: the asyncio/threads mix is the project design (sync `HttpClient`, thin `to_thread` wrapper).
- Schema and types match the real data; no drift; no duplicate ids at this pin (C-03).

### C-01 Inventory the upstream repository against the registry
- **Change task:** `chadwick-source-review 1.1`
- **Stage:** S1
- **Executor:** Claude
- **Files:** `docs/sources/chadwick.md` (hand-written part only), `openspec/changes/chadwick-source-review/design.md`
- **Tools (reuse check):** `core/github_tree.py` (git tree listing), `HttpClient`; no new fetch code.
- **Inputs:** pinned SHA in `core/sources_lock.json`; the four registered datasets; `docs/references/` excerpts.
- **Steps:** 1. list every file in `data/` at the pinned SHA; 2. map each file to a dataset, or mark it uncovered; 3. list upstream documentation of the columns (repo README, `docs/`); 4. record in `design.md` an inventory table: file, rows, dataset, status.
- **Done when:** every file in `data/` is mapped or listed as a gap with a reason; `uv run baseballpy catalog status --gaps` output for chadwick pasted in `design.md`.
- **Record:** tick 1.1; evidence in `design.md` section "S1 inventory".

### C-02 Verify and fix adapter conformance (suspected hard-coded dataset list)
- **Change task:** `chadwick-source-review 1.2`
- **Stage:** S2
- **Executor:** Claude decides the design, then agy for the code slice (review the full diff)
- **Files:** `src/baseballpy/sources/chadwick/adapter.py`, `tests/test_ingest_adapters.py` (chadwick cases), `tests/test_cli_ingest.py` if needed
- **Tools (reuse check):** the dataset registry (`core/datasets.py`) is the only list of dataset names.
- **Inputs:** `uv run baseballpy ingest chadwick --datasets register_names --help`-style dry run result; `ingest/adapters.py` for how the other adapters derive names.
- **Steps:** 1. reproduce with a mocked loader: does `plan(Selection(datasets=["register_names"]))` raise; 2. derive known names from the registry for source `chadwick`; 3. decide: one job per dataset or one job that loads all four (shared download), documented in `design.md`; 4. test both the accepted and the unknown-name path.
- **Done when:** `uv run pytest tests/test_ingest_adapters.py tests/test_ingest_contract.py tests/test_architecture.py -q` passes; no dataset name string remains in `adapter.py`.
- **Record:** tick 1.2; design note; ADR only if the job granularity changes.

### C-03 Compare the generated schema with real data
- **Change task:** `chadwick-source-review 1.3`
- **Stage:** S3
- **Executor:** Claude
- **Files:** `openspec/changes/chadwick-source-review/design.md`; `scripts/gen_schemas.py --only chadwick` only if a mismatch is proven (then regenerate, never hand-edit `tables.py`)
- **Tools (reuse check):** `pyarrow.csv`/Polars to profile the raw shard files, not a Python loop.
- **Inputs:** `sources/chadwick/tables.py` (types), one downloaded shard, `docs/sources/chadwick.md` dictionary.
- **Steps:** 1. profile each column of the four datasets: null rate, distinct count, min/max, sentinel-looking values; 2. compare with the declared Arrow type; 3. list era quirks (placeholder IDs, `0`, empty strings, dates with partial precision); 4. check `_extras` is empty on the pinned SHA and drift is logged once.
- **Done when:** a table in `design.md` with one row per column group and a verdict; every mismatch has a follow-up card or a regeneration commit.
- **Record:** tick 1.3.

### C-04 Review the code against the designated tools and the decoupling rules
- **Change task:** `chadwick-source-review 1.4`
- **Stage:** S4
- **Executor:** Claude (review), agy (mechanical migrations it approves)
- **Files:** read all of `src/baseballpy/sources/chadwick/`; edit only files a follow-up card names
- **Tools (reuse check):** `TOOLING.md` rows: HTTP, CSV/Parquet parsing, dataframe-agnostic code, concurrency.
- **Inputs:** `AGENTS.md` sections 2, 4, 7, 8; `tests/test_architecture.py`.
- **Steps:** 1. list per module what it does and which designated tool covers it; 2. flag: sync/async mixing in `extractor.py`, per-row Python in `register.py` (index build, `PlayerRecord`), any swallowed exception, any non-atomic write; 3. for each flag choose "migrate" (new card) or "tool cannot" (one sentence of evidence); 4. no code change in this card.
- **Done when:** `design.md` has the per-module table; every "migrate" has a numbered follow-up task in `tasks.md` and a BACKLOG row.
- **Record:** tick 1.4; add follow-up tasks.

### C-05 Close the spec and test gaps
- **Change task:** `chadwick-source-review 2.1`
- **Stage:** S5
- **Executor:** agy for tests (brief from C-02 to C-04 results), Claude reviews
- **Files:** `openspec/changes/chadwick-source-review/specs/chadwick-register/spec.md` (delta), `tests/test_chadwick.py`, `tests/test_chadwick_coverage.py`
- **Tools (reuse check):** `respx` for HTTP, `hypothesis` for the name/ID lookups, fixtures under `tests/fixtures/`.
- **Inputs:** current spec requirements (4) and the findings of C-01 to C-04.
- **Steps:** 1. one scenario per finding that changed behavior, each ending with a `- Verified by` line; 2. property test: any ID in the fixture register round-trips through `resolve_id` both ways; 3. confirm unit tests make no network call.
- **Done when:** `uv run pytest tests/test_spec_scenarios.py tests/test_chadwick.py tests/test_chadwick_coverage.py -q` and `openspec validate --specs` pass.
- **Record:** tick 2.1; spec delta stays in the change until archive.

### C-06 Live verification on a scratch home
- **Change task:** `chadwick-source-review 3.1`
- **Stage:** S6
- **Executor:** Claude
- **Files:** none in the repo (scratch `BASEBALLPY_HOME` outside it); evidence into `design.md`
- **Tools (reuse check):** the CLI (`baseballpy ingest chadwick`, `catalog audit`, `audit tail`); no ad hoc scripts committed.
- **Inputs:** free disk space on `C:` (about 120 GB free since 2026-10-29; check with df first).
- **Steps:** 1. `BASEBALLPY_HOME=<scratch> uv run baseballpy ingest chadwick`; 2. row counts per dataset from `audit.jsonl` and DuckDB views vs the upstream file line counts; 3. resolve a handful of known players (for example MLBAM 660271 to `ohtas001`); 4. rerun to prove resume/idempotence (no re-download at the same SHA); 5. delete the scratch home.
- **Done when:** counts, timings, resolved IDs and the second-run result are pasted into `design.md`; `catalog audit` clean for chadwick.
- **Record:** tick 3.1.

### C-07 Check export through every sink
- **Change task:** `chadwick-source-review 3.2`
- **Stage:** S7
- **Executor:** Claude
- **Files:** `design.md` only (the CSV sink is Track 6a and is not built here)
- **Tools (reuse check):** `SinkProtocol` implementations in `sinks/` (Parquet, DuckDB, Polars, dlt).
- **Inputs:** the processed `register` table from C-06.
- **Steps:** 1. write the register through each existing sink into scratch destinations; 2. read it back and compare row counts and schema; 3. record what fails or is lossy; 4. list the CSV/Postgres gap for Track 6a.
- **Done when:** a sink-by-sink result table in `design.md`; gaps copied to the Track 6a notes in `WORK_BREAKDOWN.md`.
- **Record:** tick 3.2.

### C-08 Docs, decisions and close
- **Change task:** `chadwick-source-review 4.1`
- **Stage:** S7
- **Executor:** Claude
- **Files:** `docs/sources/chadwick.md`, `docs/DECISIONS.md`, `openspec/specs/chadwick-register/spec.md`, the change directory (moved to `archive/`)
- **Tools (reuse check):** `uv run baseballpy docs generate` for dictionaries; never hand-type counts.
- **Inputs:** results of C-01 to C-07.
- **Steps:** 1. update hand-written parts of the source page; 2. ADR for each decision; 3. merge the spec delta; 4. run all gates; 5. archive the change and update `EXECUTION_ORDER.md`, `BACKLOG.md`, regenerate `PROJECT_MAP.md`.
- **Done when:** all gates green, `openspec validate --specs` passes, change archived.
- **Record:** tick 4.1 and move the change.

## Cards created by the review (fixes; code changes start here)

### C-09 Split ingest from the lookup index
- **Change task:** `chadwick-source-review 5.1`
- **Stage:** S4
- **Executor:** Claude designs the function boundary, agy writes it (Claude reviews the full diff)
- **Files:** `src/baseballpy/sources/chadwick/register.py`, new `src/baseballpy/sources/chadwick/ingest.py`, `tests/test_chadwick_coverage.py`
- **Tools (reuse check):** `ChadwickExtractor`, `ChadwickNormalizer`, `ProcessedStore` already exist; reuse them, add no new fetch or write code.
- **Inputs:** `ChadwickRegister.load` (the extract, normalize, store part) and the S4 table in `design.md`.
- **Steps:** 1. move extract, normalize and store of all four datasets into one function that returns rows per dataset; 2. `ChadwickRegister.load` calls it, then builds the index; 3. keep the public API unchanged.
- **Done when:** `uv run pytest tests/test_chadwick.py tests/test_chadwick_coverage.py tests/test_architecture.py -q` passes and the new function runs without constructing `ChadwickRegister` (asserted by a test).
- **Record:** tick 5.1.

### C-10 Registry-driven adapter with per-dataset jobs
- **Change task:** `chadwick-source-review 5.2`
- **Stage:** S2
- **Executor:** agy (Claude reviews the full diff)
- **Files:** `src/baseballpy/sources/chadwick/adapter.py`, `tests/test_ingest_adapters.py`, `tests/test_cli_ingest.py`
- **Tools (reuse check):** the dataset registry (`core/datasets.py`) supplies the names; the function of C-09 does the work.
- **Inputs:** `ingest/types.py` (`Selection`, `make_job`); the Lahman adapter as the pattern (one job per table).
- **Steps:** 1. known names = registry datasets of source `chadwick`; 2. one job per selected dataset (all four by default); 3. `run` reports that dataset's rows; 4. unknown names still raise `ValueError` listing the registry names.
- **Done when:** `uv run baseballpy ingest chadwick -d register_names --dry-run` plans one job; `uv run pytest tests/test_ingest_adapters.py tests/test_ingest_contract.py -q` passes; no dataset name literal remains in `adapter.py`.
- **Record:** tick 5.2; note the job granularity in `design.md` (ADR only if the owner wants a different one).

### C-11 `resolve_id` through an explicit column map
- **Change task:** `chadwick-source-review 5.3`
- **Stage:** S4
- **Executor:** agy (Claude reviews the full diff)
- **Files:** `src/baseballpy/sources/chadwick/register.py` (`resolve_id`, `resolve`), `src/baseballpy/sources/chadwick/schema.py` only if a helper map belongs there, `tests/test_chadwick.py`
- **Tools (reuse check):** `PlayerIdType` is already the enum of columns; derive the map from it, no string matching.
- **Inputs:** the failing cases in `design.md` S4 (MLBAM 660271 to BBREF_MINORS must be `otani-000sho`; lookups from BBREF_MINORS, NPB, WIKIDATA must work).
- **Steps:** 1. test first for all nine id types in both directions on a small fixture register; 2. one map from `PlayerIdType` to column and Python type; 3. unknown or unsupported types raise `ValueError`.
- **Done when:** `uv run pytest tests/test_chadwick.py -q` passes with a property test that every non-null id round-trips through `resolve_id`.
- **Record:** tick 5.3.

### C-12 Vectorised lookup index and honest record types
- **Change task:** `chadwick-source-review 5.4`
- **Stage:** S4
- **Executor:** Claude designs, agy writes (Claude reviews the full diff)
- **Files:** `src/baseballpy/sources/chadwick/register.py`, `tests/test_chadwick.py`, `tests/test_chadwick_coverage.py`
- **Tools (reuse check):** `pyarrow.compute` or Polars for id lookups; `narwhals` for dataframe-agnostic code; no Python loop over 526,894 rows.
- **Inputs:** S4 timing (index build 9.6 s) and the duplicate check in S3.
- **Steps:** 1. build lookups from the id columns with Arrow or Polars (only non-null ids); 2. refuse or log a duplicate id instead of overwriting; 3. `PlayerRecord` fields typed like the schema (`key_npb: int`), built on demand from a row; 4. keep the public methods.
- **Done when:** the load of the cached register plus first lookup takes under 3 s on this PC (measured, pasted in `design.md`) and `uv run pytest tests/test_chadwick.py tests/test_chadwick_coverage.py -q` passes with a duplicate-id test.
- **Record:** tick 5.4.

### C-13 Data-driven nicknames and vectorised name search
- **Change task:** `chadwick-source-review 5.5`
- **Stage:** S4
- **Executor:** Claude (needs the owner's OK on the behavior change), agy for the code
- **Files:** `src/baseballpy/sources/chadwick/register.py`, `tests/test_chadwick.py`
- **Tools (reuse check):** Polars string expressions, DuckDB `jaro_winkler_similarity`, the `name_nick` column and `register_names`.
- **Inputs:** the spec scenario "Typo resolves with fuzzy search" (`Aron Juge` finds `Aaron Judge`) must keep passing; owner decision on dropping `COMMON_NICKNAMES`.
- **Steps:** 1. ask the owner (one question); 2. replace the hand table with data from `name_nick` and `register_names` or document why a fallback list stays; 3. vectorise substring and fuzzy search; 4. compare results on a fixed name list before and after.
- **Done when:** fuzzy search on the full register runs under 2 s (measured) and `uv run pytest tests/test_chadwick.py -q` passes.
- **Record:** tick 5.5; ADR if the nickname source changes.

### C-14 Keep the upstream README, correct spec and docs
- **Change task:** `chadwick-source-review 5.6`
- **Stage:** S1
- **Executor:** Claude
- **Files:** `src/baseballpy/sources/chadwick/extractor.py` (one extra raw file), `docs/sources/chadwick.md`, `openspec/changes/chadwick-source-review/specs/chadwick-register/spec.md`, `tests/test_chadwick_coverage.py`
- **Tools (reuse check):** `RawStore.put` and the git-tree listing already in the extractor; no new fetch path.
- **Inputs:** README facts and S3 quirks in `design.md` (`key_uuid` primary key, short key re-use, `tsncardS`, orphan `names.csv` row, `key_bbref_minors` always populated).
- **Steps:** 1. store `README.md` under `raw/chadwick/` with its sha256 (not a dataset); 2. spec delta: `key_uuid` is the UUID and primary key, `key_person` is the short key; 3. docs: quirks and key-stability note; 4. test for the raw README.
- **Done when:** `uv run pytest tests/test_chadwick_coverage.py tests/test_spec_scenarios.py -q` passes and `openspec validate --specs` is clean.
- **Record:** tick 5.6.
