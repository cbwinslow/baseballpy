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

## Status (updated 2026-10-27)
- Done and archived (`archive/2026-10-27-*`): `harden-ingestion-core`, `restructure-data-lake`, `complete-source-coverage`, `statcast-minor-league-pitches`, `statcast-chunk-alignment` (found and fixed after the coverage change closed).
- `repo-hygiene-and-docs-sync`: tasks 1-3 done (license, coerce helpers, dependencies); 4-7 (lint policy, CI, docs rewrite, spec merge and archive) open.
- `unified-pipeline-and-cli`: complete and archived 2026-10-28 (spec `cli-and-ingest`).
- Proposed (not started), in suggested order: `catalog-completeness-audit` (needs `repo-hygiene-and-docs-sync` 5.1 for the weekly job), `retrosheet-box-accounts` (first task: obtain `boxfile.txt`), `column-descriptions-from-provider-metadata`, `historical-backfill-plan` (execution depends on `unified-pipeline-and-cli`).
- Done and archived since: `catalog-audit-first-run-fixes` (first audit run: 2 wrong `unsupported` verdicts, 3 roster types, 1 standings type, 6 game types), `agent-goal-seek-runbook` (`docs/agents/GOAL_SEEK_PROMPT.md`).
- Proposed since: `mlb-parameterized-stat-types` (26 stat types with no data; audit finding F-6). `catalog-completeness-audit` is partly implemented (library, CLI, evidence metadata): CI job and wider sampling remain.
- Done and archived since: `mlb-parameterized-stat-types` (ADR 38; combinations and `unsupported` entries live in `stat_combos.py`; the audit reports no unaccounted stat type). `retrosheet-box-accounts` is implemented as an interim (ADR 33) and stays open until the owner supplies `boxfile.txt`; no column names are guessed for `phline/prline/dline/pline/tline/line/event`.
- Done and archived since: `column-descriptions-from-provider-metadata` (ADR 34). Proposed: `column-descriptions-retrosheet-and-leaderboards` (retrosheet.org unreachable on 2026-10-27).
- 2026-10-28: archived `agy-delegation-and-agent-policy` and `mlb-sport-fanout-404`. Active: `verify-optin-paths` (per-game and per-player families verified on the homelab and their schemas widened; all-time pools, on-demand and game-feed runs in progress), `repo-hygiene-and-docs-sync` (4.3, 4.4, 5.3, 6.3, 7.2 done; 6.4 and 7.1 remain), `catalog-completeness-audit` (2.2 issue-opening step open), `historical-backfill-plan` (a 2015-2024 Statcast/Retrosheet/Lahman/Chadwick ingest is running on the homelab), `retrosheet-csv-bundles` (blocked: retrosheet.org times out from the PC and the homelab), `retrosheet-box-accounts` (needs `boxfile.txt`), `column-descriptions-retrosheet-and-leaderboards`.
- 2026-10-28: the remaining work is one ordered queue in `docs/agents/BACKLOG.md` (every open task of every change; a test fails if one is missing) with a generated overview in `docs/agents/PROJECT_MAP.md`; `docs/agents/NEXT_GOAL.md` is the standing prompt that works the queue. New change `spec-test-traceability` (39 of 89 spec scenarios cite no test). `verify-optin-paths` is down to the all-time pools run (running), the CLI check and the two non-unique `vs_player_*_opp_team` keys; the 2015-2024 window, the game feed and the on-demand datasets are verified.
- 2026-10-28 (later): `spec-test-traceability` is done and archived: every one of the 89 spec scenarios now ends with a `- Verified by` line and `tests/test_spec_scenarios.py::test_every_scenario_cites_a_test` enforces it. Also done: `baseballpy backfill` (B-07, B-08), the weekly audit issue step (B-11), the box-account live check (B-13), Statcast glossary descriptions (B-17), and the CSV-bundle consumer survey (B-22).
- 2026-10-29: owner rejected `retrosheet-csv-bundles` (ADR 41); archived unimplemented.
