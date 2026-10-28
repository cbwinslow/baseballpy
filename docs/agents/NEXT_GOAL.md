# Next goal (paste after `/goal`)

Follow `docs/agents/GOAL_SEEK_PROMPT.md` exactly (read it first, plus `AGENTS.md`, `CLAUDE.md`, `openspec/project.md`, `docs/DECISIONS.md` (ADRs 25, 33, 34, 38, 39) and `openspec/changes/EXECUTION_ORDER.md`). Its loop and its sections 0.6-0.8 (decoupled/dynamic design, search before any workaround, delegate bulk code to `agy`) apply to everything below.

GOAL
Finish the CLI and pipeline so the whole library runs end to end from one command surface, then close the remaining description gaps, keeping every provider item ingested or `unsupported` with evidence.

STATE AT START
- `baseballpy.ingest` (types, selection, runner) and one `IngestAdapter` per source exist and are tested; `ingest`, `catalog list|show|status` and `doctor` commands exist. ADR 39: the enforced boundaries are `SinkProtocol`, `StreamExtractorProtocol`, `LiveEventConsumerProtocol`, `IngestAdapter` and the import-boundary tests; do not re-add extractor/normalizer conformance wrappers.
- Retrosheet ingest code pulls from retrosheet.org and its existing proper locations. Never change it, and never point anything at the owner's temporary homelab folder. The host may be unreachable from this machine; code as if no user is blocked. Temporary local scripts may supply files for your own exploration only and must never be committed.

SCOPE (in order; commit after every green slice, never push)
1. **Finish `unified-pipeline-and-cli`** (read `openspec/changes/unified-pipeline-and-cli/{proposal,design,tasks}.md`, tick `tasks.md` to match reality first, since the top-level checklist is stale against the A-E notes):
   - `get_config()`/`reset_config()` (P-4) with tests for env precedence and no implicit `.env`.
   - Command groups `db sync|shell|query|views`, `stream` (live and `--replay`), `quarantine list|show|replay`, `refs update|show`, `migrate-layout`, and `audit` filters, each as its own module registered the way `cli_ingest.py` and `cli_catalog.py` are, with `CliRunner` tests for every command and exit code. Search first for how comparable CLIs (dlt, pybaseball, dagster, dbt) lay these out and record it in the design.
   - `docs/CLI.md` generated from click help (`docs generate`, stale-docs test must pass), README CLI section, QUICKSTART around `ingest`/`catalog`/`db`.
   - Manual checks, really run and summarised in the commit: `ingest all --seasons 2023 --dry-run`; a real run in a scratch `BASEBALLPY_HOME` interrupted with Ctrl-C and resumed (run the command with `run_in_background`, stop it with TaskStop, read `logs/audit.jsonl`); live statcast pitches adapter for one short window; `stream --replay` run twice is idempotent. Mind the scratch drive (about 1.8 GB free).
   - Final ADR 25 text, merge the spec delta into `openspec/specs/core-protocols/spec.md`, archive the change.
2. **`column-descriptions-retrosheet-and-leaderboards`**: re-try the documented upstream sources first (they may be reachable now); extend `scripts/build_column_descriptions.py` one builder per source table, raise the coverage baseline, keep citing the real retrosheet.org URLs. For Savant leaderboards (glossary matched 13/701), look at the leaderboard pages' own column help and the csv-docs cards. If nothing citable exists, record the search trail and stop; never invent descriptions or column names. `retrosheet-box-accounts` stays open for `boxfile.txt`.
3. **Retrosheet yearly CSV bundles**: confirm in the code whether `*csvs.zip` from the retrosheet.org downloads page is ingested; if not, write an OpenSpec change (proposal, design, tasks) that adds it through the existing downloader and registry, without touching other Retrosheet behavior. Implement only if the owner approves the change in chat.
4. **`repo-hygiene-and-docs-sync`** items 4-7 as time allows (lint policy, CI workflow files, docs rewrite, spec verification and archive), then the weekly audit CI job from `historical-backfill-plan`.
5. After each item run `uv run baseballpy catalog audit`; re-verify any `unsupported` entry you touch (bare route first, then one parameter at a time, record `tried` and `verified_on`).

CONSTRAINTS
- OpenSpec change first for anything not covered; ADR for each decision; spec deltas merged; finished changes archived; `EXECUTION_ORDER.md` kept current.
- No Claude `Agent`/workflow subagents; `agy` delegation allowed (`docs/agents/AGY_DELEGATION.md`): write a precise brief per module, read the whole diff, run the four gates plus `docs generate --check`, and say in the commit body that `agy` wrote the first draft. Two failed delegations of one task means Claude writes it.
- Never push; no destructive git; stop only background jobs you started.
- Web-search early and often when blocked; record what others did before writing a workaround.
- Write escape-heavy code with Write/Edit or `chr(92)`, not heredocs.
- Never claim "verified" without command output; report skipped and unverified items plainly.

DONE WHEN
Item 1 is implemented, tested, committed and archived with the manual checks above run and recorded; item 2 is archived or its search trail is recorded as exhausted; item 3 is a written change (implemented only if approved); gates and audit are green; the final report lists verified, not verified and needs-owner items.
