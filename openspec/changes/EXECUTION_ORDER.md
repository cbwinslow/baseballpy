# Execution Order and Runbook (for the implementing agent)

Rules for the run (token-saving, per owner request):
- **Do not spawn subagents or workflows.** Work linearly in the main session; read files with targeted `Read`/`Grep`; run commands directly.
- Commit after each numbered section group (conventional commits). Do not push unless asked.
- After each change: `uv run pytest -m "not live"`, `uvx ruff check .`, `uvx ruff format --check .`, `uvx mypy --strict src`. Fix before moving on.
- Tick `tasks.md` boxes as you go; if you discover the spec is wrong, edit the spec/design in the same commit and note it in the ADR.
- Any task that says **Manual** must actually be run (live network) and its observed output summarized in the commit message or `docs/examples/`.
- Open questions that block progress: (1) license — default GPL-3.0-or-later per ADR 26, proceed unless owner says Apache-2.0; (2) Lahman source — decided: ONLY `cbwinslow/lahman-database-csv` or user-supplied data; never `chadwickbureau/baseballdatabank` (data stops ~2023).

## Order (dependencies)
1. `harden-ingestion-core` tasks 1 → 10 (HTTP, freshness, quarantine, manifest/atomic, audit, sinks, lazy singletons, property tests).
2. `repo-hygiene-and-docs-sync` tasks 1-3 and 5 (license, helpers `core/coerce.py`, dependency changes, CI) — can interleave with step 1.
3. `restructure-data-lake` tasks 1-6 (LakeConfig, registry skeleton, stores, DB rewrite, migration, pinned refs).
4. `complete-source-coverage` task 0, then sources in this order: **Chadwick (5) → Lahman (3) → Retrosheet (4) → Statcast (2) → MLB API (1)** (smallest to largest; MLB last because it is the biggest). Each source: fixtures → tests → live probe → docs generation.
5. `unified-pipeline-and-cli` tasks 1-4 (framework can start after coverage task 0; wire each source's `JobPlanner` as it lands), then task 5-6.
6. `repo-hygiene-and-docs-sync` tasks 4, 6, 7 (lint policy tightening, docs rewrite, spec merge, archive).

## Definition of done (whole program)
- All five changes' tasks checked; all deltas merged into `openspec/specs/*`; changes moved to `openspec/changes/archive/`.
- `baseballpy ingest all --seasons 2023` into an empty `BASEBALLPY_HOME` completes; `baseballpy catalog status` shows no `MISSING` (except rows marked `unsupported` with probe evidence); `baseballpy db sync` builds a view for every ingested dataset; `baseballpy doctor` is clean.
- `docs/sources/*.md` contain generated column dictionaries for every dataset; `baseballpy docs check` passes.
- CI workflow files exist; coverage ≥ 85%; architecture-boundary tests pass.
