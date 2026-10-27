# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`baseballpy` ingests Statcast (Baseball Savant), the MLB Stats API, Lahman, the Chadwick Register and Retrosheet into typed Parquet (queried through DuckDB views). GPL-3.0-or-later (ADR 26; upstream data licenses in `docs/DATA_LICENSES.md`).

## The contract: read before changing anything

- `AGENTS.md` is the engineering contract (decoupling, full data preservation, rate limits, atomic writes, quarantine, audit logging). `openspec/project.md`, `openspec/specs/*` and `docs/DECISIONS.md` (ADRs) are the living specs.
- All work is an OpenSpec change under `openspec/changes/<name>/` (`proposal.md`, `design.md`, `tasks.md`, spec deltas). Execution order and rules: `openspec/changes/EXECUTION_ORDER.md`. Tick `tasks.md` as you go, merge deltas into `openspec/specs/*` and move finished changes to `openspec/changes/archive/<date>-<name>/`. Record decisions in `docs/DECISIONS.md`.
- **Never leave upstream data behind.** Every field, endpoint, group, level and file the provider offers is captured (typed column or `_extras`), even when another source has it. If something cannot be ingested, it stays registered as `unsupported` with probe evidence, or its raw bytes are kept; it is never silently skipped.
- **Owner rules:** no subagents or workflows (work linearly in the session); Lahman comes only from `cbwinslow/lahman-database-csv` or user-supplied data, never `chadwickbureau/baseballdatabank`; commit per section with conventional messages, do not push; run the gates after every section; manual/live checks are really run and summarised in the commit.

Autonomous runs: use `docs/agents/GOAL_SEEK_PROMPT.md` (loop with verification, audit and web-research protocol).

## Commands

```bash
uv sync --all-extras
uv run pytest                                   # network is blocked (pytest-socket); live tests are opt-in
uv run pytest tests/test_mlb_stream.py::test_apply_patch_all_operations -v
uvx ruff check . && uvx ruff format .
uv run mypy --strict src                         # use `uv run`: bare `uvx mypy` lacks the deps and reports false errors
uv run baseballpy docs generate [--check]        # regenerates column dictionaries; tests fail on stale docs
```

The four gates are `pytest`, `ruff check`, `ruff format --check`, `mypy --strict src`; `tests/test_docsgen.py` and `tests/test_lake.py` also enforce docs and registry consistency.

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
