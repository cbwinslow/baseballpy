# Next goal (paste after `/goal`)

Follow `docs/agents/GOAL_SEEK_PROMPT.md` exactly (read it first, plus `AGENTS.md`, `CLAUDE.md`, `openspec/project.md`, `docs/DECISIONS.md` and `openspec/changes/EXECUTION_ORDER.md`). Its loop and its sections 0.6-0.8 (decoupled/dynamic design, search before any workaround, delegate bulk code to `agy`) apply to everything below.

GOAL
Finish the remaining descriptions with whatever Retrosheet material is reachable, then build the pipeline and CLI so the whole library runs end to end, keeping every provider item ingested or `unsupported` with evidence.

SCOPE (in order; commit after every green slice, never push)
1. **Retrosheet descriptions, with real exploration.** Only the GitHub mirror is reachable (`retrosheet.org` refuses connections). Explore `chadwickbureau/retrosheet` (branches `master`, `official`, README, any docs) fully. Web-search for alternative primary sources: how `sportsdataverse`, `baseballr` (GitHub source), `pybaseball`, `pyretrosheet` and the Chadwick documentation obtain or document game logs, schedule, rosters, reference tables, discrepancies and box accounts; look for mirrors or packages that ship the format documents (`glfields.txt`, `boxfile.txt`, `csvcontents.html`, `eventfile.htm`) or an MCP/API that serves them. Cite whatever you find in `column-descriptions-retrosheet-and-leaderboards/design.md`, extend `scripts/build_column_descriptions.py` (decoupled: one builder per source reading a source table, no per-dataset special cases), raise the coverage baseline, and archive the change if complete. If nothing citable exists, record the search trail and stop this item; never invent descriptions or column names (`retrosheet-box-accounts` stays open for `boxfile.txt`).
2. **`unified-pipeline-and-cli`** (open change, not started): `Pipeline`/`Job` core driven by the dataset registry, `ingest <source>` / `ingest all` with `--dry-run`, `catalog status`, `doctor`, resume after interruption. Read `openspec/changes/unified-pipeline-and-cli/{proposal,design,tasks}.md` first, search for how comparable pipelines (dlt, pybaseball, Dagster-style asset registries) structure this, then design it so sources plug in through the registry and Protocols with zero per-source branches. Delegate implementation of well-specified modules and tests to `agy`; Claude reviews every diff and runs the gates.
3. **`repo-hygiene-and-docs-sync`** items 4-7 as time allows (lint policy, CI workflow files, docs rewrite, spec verification and archive).
4. After each item run `uv run baseballpy catalog audit`; re-verify any `unsupported` entry you touch (bare route first, then one parameter at a time, record `tried` and `verified_on`).

CONSTRAINTS
- OpenSpec change first for anything not covered; ADR for each decision; spec deltas merged; finished changes archived; `EXECUTION_ORDER.md` kept current.
- No Claude `Agent`/workflow subagents; `agy` delegation allowed (`docs/agents/AGY_DELEGATION.md`). Never push; no destructive git; stop only background jobs you started.
- Web-search early and often when blocked; record what others did before writing a workaround.
- Write escape-heavy code with Write/Edit or `chr(92)`, not heredocs.
- Never claim "verified" without command output.

DONE WHEN
Item 1 is archived or its search trail is recorded as exhausted; item 2 is implemented, tested, committed and archived with a clean `ingest all --seasons 2023` dry run and a live run in a scratch `BASEBALLPY_HOME` that resumes after interruption; gates and audit are green; the final report lists verified, not verified and needs-owner items.
