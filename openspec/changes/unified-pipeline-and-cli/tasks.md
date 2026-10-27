# Tasks: Unified Pipeline and CLI

Prerequisites: harden tasks 1-7; restructure tasks 1-4; coverage task 0 (registry + schema tools). CLI commands for
datasets appear as their coverage sections land; this change builds the framework and commands against whichever datasets are registered.

- [ ] 1. Pipeline core (P-1, P-6) <!-- id: 1 -->
  - [ ] 1.1 `baseballpy/pipeline.py`: `Job`, `JobStatus`, `JobResult`, `RunReport`, `Pipeline.run/run_many/plan/run_sync`
  - [ ] 1.2 `DatasetSpec.make_extractor/make_normalizer/depends_on` hooks in `core/datasets.py`
  - [ ] 1.3 Per-source `JobPlanner`s (statcast windows, leaderboard variants, MLB fan-outs, Retrosheet seasons×datasets, Lahman tables, Chadwick files)
  - [ ] 1.4 Selection parser (`2023`, `2015-2024`, `2015,2018`, `all`), topological ordering
  - [ ] 1.5 Cancellation/resume semantics (`CANCELLED`, `.part` cleanup)
  - [ ] 1.6 Convert existing `*Source` classes into thin facades; public function names unchanged
- [ ] 2. Protocol conformance (P-5) <!-- id: 2 -->
  - [ ] 2.1 Add `extract`/`extract_async` to Lahman, leaderboards, MLB extractors; `schema`/`normalize`/`normalize_stream` to all normalizers; fix `stream_events(game_pk, ...)`
  - [ ] 2.2 `tests/test_protocol_contract.py` (signature-level)
- [ ] 3. Config (P-4) <!-- id: 3 -->
  - [ ] 3.1 `get_config()`/`reset_config()`; `pipeline` section; `BASEBALLPY_ENV_FILE`
  - [ ] 3.2 Tests (env precedence, no implicit `.env`)
- [ ] 4. CLI package (P-2, P-3) <!-- id: 4 -->
  - [ ] 4.1 Split `cli.py` into `cli/` package; keep entry point and existing commands working
  - [ ] 4.2 `ingest <source>` and `ingest all` with `--dry-run`, `--json`, progress, exit codes
  - [ ] 4.3 `catalog list|show|status`
  - [ ] 4.4 `db sync|shell|query|views`
  - [ ] 4.5 `stream`
  - [ ] 4.6 `docs generate|check`
  - [ ] 4.7 `audit` filters (`--source --since --status`)
  - [ ] 4.8 `quarantine list|show|replay`
  - [ ] 4.9 `migrate-layout`, `refs update|show`, `doctor [--clean]`
  - [ ] 4.10 `CliRunner` tests for every command and exit code
- [ ] 5. Verification <!-- id: 5 -->
  - [ ] 5.1 `uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uvx mypy --strict src`
  - [ ] 5.2 Manual: dry-run then real `ingest all --seasons 2023` in a scratch home; interrupt with Ctrl-C mid-run, re-run, verify resume; `catalog status` has no MISSING rows; `doctor` clean
  - [ ] 5.3 Manual: `stream` a live game (or the most recent Final game replayed via `--replay`) and verify JSONL events + upsert into DuckDB are idempotent when run twice
- [ ] 6. Docs <!-- id: 6 -->
  - [ ] 6.1 ADR 25; README CLI section; QUICKSTART rewritten around `ingest`/`catalog`/`db`; `docs/CLI.md` generated from click help (`docs generate`)
  - [ ] 6.2 Merge spec delta into `openspec/specs/core-protocols/spec.md`

## As-built plan (design section 8)
- [ ] A. `ingest/types.py`, `ingest/selection.py`, `ingest/runner.py` + tests (delegated to agy, reviewed)
- [ ] B. `ingest/adapters.py` Protocol + registry; one adapter per source (statcast, mlb_api, lahman, chadwick, retrosheet)
- [ ] C. CLI `ingest`, `catalog status`, `doctor` + CliRunner tests
- [ ] D. Manual: dry run, live run into a scratch home, interrupt and resume

## Status (2026-10-27)
Not started. Prerequisites are met: the dataset registry, per-source extractors and `ingest_season`/`ingest_all`/`ingest_reference`/`ingest_history`/`ingest_people_stats` entry points exist for all five sources (`complete-source-coverage`), so the `Pipeline`/`Job` layer and the `ingest`, `catalog status`, `stream` and `doctor` commands can wrap them. `catalog status` should report `raw_only` and `unsupported` endpoints from the probes.
