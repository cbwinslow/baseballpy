# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`baseballpy` ingests Statcast (Baseball Savant), the MLB Stats API, Lahman, the Chadwick Register and Retrosheet into typed Parquet (queried through DuckDB views). GPL-3.0-or-later (ADR 26; upstream data licenses in `docs/DATA_LICENSES.md`).

## Hard rules (every task, every agent; full text is `AGENTS.md` section 14)

1. **Preflight first:** find the task in `docs/agents/BACKLOG.md` (and its card in `docs/agents/tracks/`), read its OpenSpec change, list the files you will touch. No row, no change: open the change first.
2. **Tools before code:** run the reuse check of `docs/agents/TOOLING.md` (pyarrow, polars, duckdb, narwhals, msgspec, httpx/tenacity/aiolimiter, dlt, pydantic-settings, click/rich, hypothesis). `Grep` for an existing helper. Custom code needs one sentence of evidence for what the tool cannot do.
3. **Registry and data, not names:** no hard-coded dataset, endpoint or season lists; one declarative table plus one generic function; keep Protocol boundaries (`IngestAdapter`, `SinkProtocol`).
4. **OpenSpec always:** spec delta with a `Verified by` test, ADR per decision, tick `tasks.md`, evidence in `design.md`, archive finished changes.
5. **Small slices, evidence or not done:** one card per commit, the four gates plus `docs generate --check` and `openspec validate --specs`, command output pasted, "not verified" said plainly.

How the project is partitioned into tasks: `docs/agents/WORK_BREAKDOWN.md`. Current source under review: Chadwick (`docs/agents/tracks/01-chadwick.md`).

## The contract: read before changing anything

- `AGENTS.md` is the engineering contract (decoupling, full data preservation, rate limits, atomic writes, quarantine, audit logging). `openspec/project.md`, `openspec/specs/*` and `docs/DECISIONS.md` (ADRs) are the living specs.
- All work is an OpenSpec change under `openspec/changes/<name>/` (`proposal.md`, `design.md`, `tasks.md`, spec deltas). Execution order and rules: `openspec/changes/EXECUTION_ORDER.md`. Tick `tasks.md` as you go, merge deltas into `openspec/specs/*` and move finished changes to `openspec/changes/archive/<date>-<name>/`. Record decisions in `docs/DECISIONS.md`.
- **Never leave upstream data behind.** Every field, endpoint, group, level and file the provider offers is captured (typed column or `_extras`), even when another source has it. If something cannot be ingested, it stays registered as `unsupported` with probe evidence, or its raw bytes are kept; it is never silently skipped.
- **Owner rules:** no Claude `Agent`/workflow subagents (work linearly in the session); the one allowed delegate is `agy` (see below); Lahman comes only from `cbwinslow/lahman-database-csv` or user-supplied data, never `chadwickbureau/baseballdatabank`; commit after every green slice with conventional messages, do not push; run the gates after every section; manual/live checks are really run and summarised in the commit.

Autonomous runs: use `docs/agents/GOAL_SEEK_PROMPT.md` (loop with verification, audit and web-research protocol). What is left to do is the ordered queue `docs/agents/BACKLOG.md` (every open task of every change is in it; a test enforces that), mapped by `docs/agents/PROJECT_MAP.md` (`uv run python scripts/project_map.py` regenerates it); `docs/agents/NEXT_GOAL.md` is the standing prompt that works the queue.

## Design philosophy: decoupled, reusable, dynamic

Keep the codebase loosely coupled so a change in one place cannot break another: sources meet the rest of the code only through `baseballpy.ingest.IngestAdapter` (and sinks through `SinkProtocol`), enforced by `tests/test_ingest_contract.py` and `tests/test_architecture.py` (ADR 39); behavior comes from the dataset registry, generators and data, not from hard-coded dataset names or per-source special cases; prefer one small declarative table plus one generic function over several intertwined hand-written functions. When a fix seems to need a special case, look for the general mechanism that removes the case. `tests/test_architecture.py` enforces the import boundaries; do not weaken it.

## Search the web before building a workaround

When a problem appears (unreachable host, odd parameter, unreadable format, failing probe, a design question), web-search for how others solved it first (pybaseball, baseballr, sportsdataverse, Chadwick tools, the provider's GitHub, issues, docs) and record what you found in the OpenSpec design. Do this early and often; a workaround that was not compared with existing practice is a defect. Standard-mode search first, extended when thin.

## Delegating code to `agy` (Gemini)

`agy` is installed (`agy models`, `agy agents`). Claude designs, root-causes and reviews; `agy` (`gemini-3.8-flash-medium`) writes bulk code from a precise brief: `uv run python scripts/agy_delegate.py <brief.md> [--agent python-pro]`. Use it at your discretion for well-specified code, tests, fixtures and mechanical edits; always read the full diff and run the gates afterwards. Details, brief template and review protocol: `docs/agents/AGY_DELEGATION.md`.

## Commands

```bash
uv sync --all-extras
uv run pytest                                   # network is blocked (pytest-socket); live tests are opt-in
uv run pytest tests/test_mlb_stream.py::test_apply_patch_all_operations -v
uvx ruff check . && uvx ruff format .
uv run mypy --strict src                         # use `uv run`: bare `uvx mypy` lacks the deps and reports false errors
uv run baseballpy docs generate [--check]        # regenerates column dictionaries; tests fail on stale docs
```

The four gates are `pytest`, `ruff check`, `ruff format --check`, `mypy --strict src`; `tests/test_docsgen.py` and `tests/test_lake.py` also enforce docs and registry consistency. `openspec validate --specs` (CI job `specs`) checks that every spec requirement has a scenario; `tests/test_spec_scenarios.py` checks that every test a scenario cites exists.

## Architecture (needs several files to see)

- **Layers:** `sources/<source>/` (extract + normalize) -> strict Arrow schemas -> `ProcessedStore`/`RawStore` in `core/stores.py` -> DuckDB views in `database.py`. All HTTP goes through `core/http.py::HttpClient` (rate limit, HTTP/2, retries); never swallow exceptions; uncastable cells go to `core/quarantine.py`.
- **Lake layout v2** under `$BASEBALLPY_HOME`: `raw/<source>/<dataset>/[season=Y/]` (immutable upstream bytes + sha256 in a per-directory manifest), `processed/.../part-<chunk>.parquet` (zstd), `quarantine/`, `cache/http/`, `databases/baseball.duckdb` (views only), `logs/audit.jsonl`. `LakeConfig` path helpers never create directories.
- **Dataset registry:** `core/datasets.py` + `sources/catalog.py::register_all()` register every `DatasetSpec` (hundreds; the count grows with each regeneration) (schema, partition, keys, view, doc anchor). Views, docs generation and tests iterate the registry; nothing else hardcodes dataset names. Docs for each source are `docs/sources/<source>.md`; column dictionaries are generated between `<!-- BEGIN GENERATED:... -->` markers (`docsgen.py`), the rest is hand-written.
- **Generated schemas (never edit by hand):** `sources/lahman|chadwick|retrosheet/tables.py` (`scripts/gen_schemas.py`), `sources/statcast/lb_tables.py` (`scripts/gen_savant_schemas.py`), `sources/mlb_api/mlb_tables.py` + `stat_combos.py` (`scripts/gen_mlb_schemas.py`), fixtures under `tests/fixtures/{savant,mlb}/`. The generators probe the live API, widen types over samples, verify keys and write `docs/*_probe.json`. `--only NAME ...` merges into the generated files. Types come from data, never from column-name guessing; unknown columns land in `_extras` JSON with a one-time `schema_drift` warning.
- **Statcast:** `lb_catalog.py` is the leaderboard registry (one `LeaderboardDef` per variant; the season parameter differs per route and `year=` is silently ignored by some, so the probe compares payload hashes across seasons). Pitches: 5-day windows on a fixed per-year grid (`grid_windows`, so overlapping requests never duplicate pitches), bisected at Savant's 25,000-row cap, season windows from the MLB calendar; minor-league pitches (`minors=true`, 2021+) are the separate dataset `pitches_minors`; filtered queries are returned but never persisted.
- **MLB API:** hand-written datasets (`extractor.py`/`normalizer.py`) plus the declarative registry: `endpoints.py` (`MlbEndpoint`: path template, record path, fan-out scope, key) -> `flatten.py` (generic JSON flattening; `*` = list, `@` = dict values) -> `generic.py` (normalizer + paginated extractor) -> schemas in `mlb_tables.py`. Adding an endpoint = add it to `endpoints.py`, run the generator, add tests. All-time stat pools (`career*`, `statsSingleSeason*`, up to ~190k rows) are `heavy`: skipped unless `include_history`, refused above 20,000 rows. `stream.py` is the live streamer (timestamps + diffPatch, resumable watermark, `LiveEvent`).
- **Retrosheet/Chadwick/Lahman:** file lists come from the pinned GitHub git tree (`core/sources_lock.json`, `core/github_tree.py`); `chadwickpy` (GPL) is imported only in `retrosheet/_chadwick_adapter.py`.

## Shell and editing pitfalls on this machine (Windows, Git Bash)

- Backslashes in heredocs and inline `python - <<EOF` scripts get collapsed (`\n` becomes a real newline, `\\b` becomes a backspace character). Write code that contains escapes or regexes with the Write/Edit tools, or build them with `chr(92)`; check generated files for stray control characters.
- Background jobs: run the real command with `run_in_background` (a trailing `&` subshell is killed); stop them with TaskStop, never with broad `taskkill`/process kills. Long ingests write per-request records to `logs/audit.jsonl`: read that to see progress instead of waiting blind.
- `tests/` has no `__init__.py`; each test file defines its own helpers.
