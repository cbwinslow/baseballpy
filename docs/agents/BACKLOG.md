# Backlog: everything left to finish the project

This is the single, ordered work queue. Every open task of every OpenSpec change appears here as
`` `<change> <task number>` ``; `tests/test_agent_runbooks.py` fails when an open task is missing,
so nothing can be left unmapped. Pick work from here; do not infer work from memory.

How to use it (the loop is in `GOAL_SEEK_PROMPT.md`, the standing instruction in `NEXT_GOAL.md`):

1. Take the first item whose status is **READY** and whose dependencies are done. Items marked
   **LONG** are started in the background first (homelab, `run_in_background`), then the next READY
   item is worked on while they run.
2. An item is finished only when its *Done when* holds with command output you ran. Tick the task in
   its `tasks.md`, record evidence in the change's `design.md`, commit, and update this file's status.
3. **OWNER** items need a decision or a file only the owner can give. Ask once (one short list), do
   everything else, and never stall on them.
4. New work found on the way becomes a new OpenSpec change, a task here and an entry in this file.

Status words: READY (start now), LONG (hours; background), OWNER (needs the owner), EXTERNAL (needs a
host that is unreachable; retry, do not work around), DONE-WHEN-LAST (closes the change after the rest).

## A. Finish the opt-in verification (`verify-optin-paths`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-01 | verify-optin-paths 3: all-time pools | DONE: 42 of 57 pools ingested, 15 failures recorded with root cause in design.md (provider 503 on deep offsets; league v1/stats 406, B-30) | all 57 pools in the homelab scratch `home` are INGESTED or recorded failing with root cause and fix; `stats_stats_single_season_hitting` is re-run with the 180 s page timeout (fix in `0d9c59d`) and either ingests or has a new root cause; every `schema_drift` warning in `optin3.err` is regenerated (`scripts/gen_mlb_schemas.py --only NAME`) or recorded; results added to `design.md` |
| B-02 | verify-optin-paths 6: CLI knobs | DONE (finished tasks are written without backticks so the test ignores them) | `ingest mlb_api --datasets games\|history\|people_stats` and `--limit` are in `docs/CLI.md`, covered by `CliRunner` tests, and `catalog status --gaps` notes name working commands (already built: confirm nothing else is missing, then tick) |
| B-03 | verify-optin-paths 8: unique keys for the two `vs_player_*_opp_team` datasets | DONE: KEY_OVERRIDES in endpoints.py, key_unique_per_request true for both in docs/mlb_probe.json, live check summarised in the commit | the payload's split dimensions are identified from a real response, the key is extended in `endpoints.py`, schemas regenerated, `key_unique_per_request` is true for both in `docs/mlb_probe.json`, test added |
| B-04 | verify-optin-paths 7: final report and archive | DONE (final report in design.md; archived 2026-10-30) | B-01..B-03 done (the pool failures and the schema_drift leftovers moved to mlb-stats-route-406-and-deep-pools, B-31..B-36); report lists verified / not verified / needs-owner; change archived under `openspec/changes/archive/<date>-verify-optin-paths/` with spec deltas merged |
| B-29 | MLB Stats API answers HTTP 403 to our User-Agent (new, found 2026-10-28) | DONE (ADR 40) | owner chose the pybaseball agent on 2026-10-28; resolved 2026-10-28; the 406 of 2026-10-29 on league-wide v1/stats is a different problem (B-30) |
| B-30 | MLB Stats API answers HTTP 406 to every league-wide v1/stats request (new, found 2026-10-29) | EXTERNAL | probed from this PC and the homelab: stats=season, with or without playerPool/limit/sitCodes or a browser User-Agent, gives 406; v1/teams and v1/people/{id}/stats give 200; it worked earlier on 2026-10-29. Retest later (one request per hour at most); when it answers 200 again re-run the 15 failed pools (3 had provider 503 on deep offsets: smaller pages or a per-season split) and do not mark the 12 stat_splits pools unsupported without a 200-control. Impact: the per-season default stats_* datasets use the same route, so every MLB season ingest lacks them while it lasts (work is in B-31..B-36). Never run the full gen_mlb_schemas.py while it persists (phase 1 wrote an empty combo table) |

## B. Historical depth and backfill (`historical-backfill-plan`)

The 2015-2024 window ran on the homelab on 2026-10-28 (63 jobs, 2.62 h, 7.5 GB, resume 46 s): the
numbers are in `verify-optin-paths/design.md`.

| ID | Task | Status | Done when |
|---|---|---|---|
| B-05 | historical-backfill-plan 1.1: throughput per source | DONE (all five sources; MLB API 2024 after ADR 40) | rows, bytes and seconds for one old and one modern season per source, taken from `hist.jsonl` / the audit log of the homelab lake (re-run an old season such as 1990 in a scratch home if the window has none), written to `docs/BACKFILL.md` |
| B-06 | historical-backfill-plan 1.2: the plan | DONE (`docs/BACKFILL.md`; the MLB API row is only a bound) | `docs/BACKFILL.md` has the order, ranges, disk and time estimates for the full history (1871-today) per source, and a short list of owner decision points (permanent location, ranges, schedule) |
| B-07 | historical-backfill-plan 2.1: `baseballpy backfill` | DONE | command with a plan file, progress summary, `--max-gb` and free-space pre-flight, built on `run_jobs` (no source special cases), `docs/CLI.md` regenerated, tests with respx |
| B-08 | historical-backfill-plan 2.2: interruption and resume test | DONE | respx test: interrupt mid-plan, re-run, only incomplete chunks fetched |
| B-09 | `historical-backfill-plan 3.1`: run the backfill into the real home | OWNER | owner names the permanent lake location and approves the ranges; the run's summary is in `docs/BACKFILL.md` |
| B-10 | `historical-backfill-plan 3.2`: audit and status after the backfill | OWNER | after B-09: `catalog audit` clean and `catalog status --gaps` lists only datasets the provider does not publish |

## C. Audit and repository (`catalog-completeness-audit`, `repo-hygiene-and-docs-sync`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-11 | catalog-completeness-audit 2.2: open an issue on audit findings | DONE in code and tests; the real GitHub run is OWNER (needs a push and Actions enabled, section H item 4) | `live.yml` step uses `gh issue create`/`gh issue comment` (permission `issues: write`, one open issue titled by a fixed marker so findings update it), written and YAML-parsed; a test checks the step exists; the first real run on GitHub is listed as not verified until the owner enables Actions |
| B-12 | `repo-hygiene-and-docs-sync 6.4`: merge deltas and archive | after B-04, B-10, B-16, B-19, B-37, B-38 (OWNER / EXTERNAL) | every other change is archived or explicitly deferred by the owner; `openspec validate --specs` 14 of 14 (or more); `EXECUTION_ORDER.md` current |
| B-27 | spec-test-traceability 1: cite or write a test for each of the 39 uncited scenarios | DONE | per spec, every scenario ends with a `Verified by` line naming a test that asserts its THEN clause (write the missing mocked tests first; a claim nothing can check is removed from the spec); `uv run python scripts/project_map.py` shows the cited-test counts rising |
| B-28 | spec-test-traceability 2: enforce it | DONE (change archived) | `tests/test_spec_scenarios.py` fails for any scenario without a citation; gates green; change archived |

## D. Retrosheet box accounts (`retrosheet-box-accounts`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-13 | retrosheet-box-accounts 4.3: live check on the 2015-2024 lake | DONE | on the homelab lake `home_hist`: every `gamelogs` game is in `box_games`, the extra rows (All-Star, postseason) are explained, no quarantine, counts in `design.md` |
| B-14 | `retrosheet-box-accounts 1.1`: the official `boxfile.txt` | OWNER / EXTERNAL | the file is supplied by the owner or retrosheet.org becomes reachable (`curl -I https://www.retrosheet.org/` from the homelab; retry once per session); stored with the Retrosheet notice under `docs/sources/` and the layouts reconciled in `design.md` |
| B-15 | `retrosheet-box-accounts 2.3`: typed datasets for the remaining kinds | after B-14 | one strict dataset per record kind still in `box_records`, layouts taken only from the document, generator or spec-driven, tests per kind, `box_records` keeps unknown kinds only |
| B-16 | `retrosheet-box-accounts 1.2`: final ADR and spec merge | after B-14 and B-15 (OWNER / EXTERNAL) | ADR 33 updated for the final layout, spec delta merged, change archived |

## E. Column descriptions (`column-descriptions-retrosheet-and-leaderboards`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-17 | column-descriptions-retrosheet-and-leaderboards 2.1: Savant leaderboard column definitions | DONE (17 exact-name columns; the rest stay undescribed) | web search (Baseball Savant glossary and leaderboard pages, pybaseball and baseballr docs, the CSV "Download" headers), cited definitions added to `docs/columns/statcast.json` with the source URL per entry; undefined columns stay undescribed (never invented); the search trail is in `design.md`; `docs generate` run |
| B-18 | `column-descriptions-retrosheet-and-leaderboards 1.3`: schedule, rosters, reference tables, discrepancies, box accounts | EXTERNAL | the Retrosheet format documents are read from retrosheet.org (retry; also the `web.archive.org` copy and the R `retrosheet`/`baseballr` docs); only cited text is added; if none is citable the search trail is recorded and the task is closed as "no citable source" |
| B-19 | `column-descriptions-retrosheet-and-leaderboards 3.1`: gates and baseline | after B-14 and B-15 (OWNER / EXTERNAL; their columns are still to describe) | gates green, description coverage per source stated in the commit |

## F. Retrosheet CSV bundles (rejected)

The owner rejected `retrosheet-csv-bundles` on 2026-10-29 (ADR 41): extra code for data the Retrosheet
event-file ingest already covers. Archived without implementation; nothing to do here.

## G. Standing stewardship (repeat; not tasks)

Run after every item and whenever idle: `uv run baseballpy catalog audit` and `catalog status --gaps`;
the four gates plus `docs generate --check` and `openspec validate --specs`; re-verify any
`unsupported` entry touched; turn `schema_drift` warnings from real runs into regenerations; keep
`EXECUTION_ORDER.md` and this file current; `uv run python scripts/project_map.py --check`.

## H. Owner decisions pending (ask once, then continue with everything else)

1. Supply `boxfile.txt`, or say retrosheet.org is reachable from a machine you can use (B-14, B-18).
2. Name the permanent lake location and approve backfill ranges (B-09). Stages 1-3 of `docs/BACKFILL.md` can run as soon as you do; the MLB stage waits on B-30.
3. Decide when to push (96 unpushed commits, only on this PC plus a homelab bundle; CI has never run) and whether to tag a first release (versioning is in `docs/RELEASING.md`).
4. The host-key mismatch of `cbwdellr720-lan` (use `cbwdellr720` until fixed).

## I. League-wide MLB stats and loose ends (`mlb-stats-route-406-and-deep-pools` and two closers)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-31 | mlb-stats-route-406-and-deep-pools 1.1: research the 406 | DONE (design.md; no report found, idea: record the Accept header on the next retest) | sources (pybaseball, MLB-StatsAPI, baseballr issues) and findings in the change's design.md |
| B-32 | `mlb-stats-route-406-and-deep-pools 1.2`: retest the route | EXTERNAL (one request per hour at most; still 406 on 2026-10-30, control 200) | the date league-wide v1/stats answers 200 again, with a v1/teams control, is recorded |
| B-33 | mlb-stats-route-406-and-deep-pools 2.1: generator guard and 406 as provider error | DONE | an empty combo table is never written, a 406 is logged and not marked unsupported, tests |
| B-34 | mlb-stats-route-406-and-deep-pools 2.2: smaller pages or per-season split for the three deep pools | DONE (adaptive halving of the page after a 5xx, respx test; live run waits for the 406 to clear, B-35) | respx tests; the pools page without 503 in a later live run |
| B-35 | `mlb-stats-route-406-and-deep-pools 3.1`: re-run the 15 failed pools and a modern season | after B-32 and B-34 (LONG, homelab) | rows and errors recorded in design.md |
| B-36 | `mlb-stats-route-406-and-deep-pools 3.2`: regenerate the team_stats_year_by_year schemas | READY (confirm the route answers 200 first) | fields such as stat.flyHits are typed columns, test added, no full generator run |
| B-37 | catalog-completeness-audit 4.2: ADR 35, spec merge, archive | DONE | ADR 35 exists, the catalog-audit spec is in openspec/specs, the change is archived |
| B-38 | `historical-backfill-plan 3.3`: ADR 36, backfill spec merge, archive | after B-10 | ADR 36 exists, the backfill spec is merged, the change is archived |

## J. dlt as the core (`dlt-pipeline-core`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-39 | dlt-pipeline-core 1.1: brief and registry-driven dlt resource factory for three endpoints | DONE: scripts/dlt_spike.py (agy first draft, reviewed, 2 tests) | resources for teams, schedule (one day) and people_stats_season_hitting (three people) exist, gates green |
| B-40 | dlt-pipeline-core 1.2: load into DuckDB and Parquet and compare | DONE: three endpoints, 5 live requests, compared | columns, types, row counts and code size compared with the current path, about 20 requests |
| B-41 | dlt-pipeline-core 1.3: record what dlt replaced and what it could not | DONE: findings in design.md | findings in design.md |
| B-42 | dlt-pipeline-core 2.1: ADR 42 adopt or reject | DONE: ADR 42 | ADR 42 cites the numbers |
| B-43 | dlt-pipeline-core 3.1: DltAdapter behind IngestAdapter (design REJECTED by the owner 2026-10-29; redesign first, see docs/agents/HANDOFF_B43.md) | DONE (superseded by ADR 44 and export-workflow, B-76..B-85) | a new design the owner approves: existing tools used better (Arrow interchange, SinkProtocol sinks incl. CSV, dlt, narwhals), uniform and registry-driven |
| B-44 | dlt-pipeline-core 3.2: retire flatten, _extras and drift paths replaced by contracts | DONE (superseded by ADR 44 and export-workflow, B-76..B-85) | tests, docs generate, gates green |
| B-45 | reference-docs 3: cross-check endpoints and column types against the reference docs | DONE (routes cross-checked by `scripts/endpoint_crosscheck.py`; the references document parameters, not response column types, so types stay confirmed by live-probed samples) | `docs/references/ENDPOINT_CROSSCHECK.md` lists every registry endpoint with its documented route and types in each reference and any disagreement with the live-probed schema |

## K. Source-by-source review (owner request 2026-10-29; method in `docs/agents/WORK_BREAKDOWN.md`)

One source is open at a time, in this order: Chadwick, Lahman, Retrosheet, Statcast, MLB API. Each
source has a change `<source>-source-review` and a card file in `docs/agents/tracks/`. Rows for the
next source are added when the owner opens it. The older sections above keep their rows; where a row
touches a source under review, do it inside that source's track.

| ID | Task | Status | Done when |
|---|---|---|---|
| B-46 | project-replan-and-agent-rails 2.1: AGENTS.md section 14, CLAUDE.md hard rules, prompt pointers | DONE | `tests/test_agent_rails.py` passes; `GOAL_SEEK_PROMPT.md` and `NEXT_GOAL.md` point at section 14 and `TOOLING.md` |
| B-47 | project-replan-and-agent-rails 2.2: rails test and `agent-runbooks` spec delta | DONE | test file and delta exist, scenarios cite their tests, `openspec validate --specs` passes |
| B-48 | project-replan-and-agent-rails 3.1: backlog fix and reorder | DONE | duplicate row gone, section K present, `test_agent_runbooks.py` passes |
| B-49 | project-replan-and-agent-rails 3.2: EXECUTION_ORDER and project.md drift | DONE | status lines current, `openspec/project.md` names real modules, AGENTS.md paths use `$BASEBALLPY_HOME` |
| B-50 | project-replan-and-agent-rails 3.3: gates, merge deltas, archive | DONE | all gates green with output, change archived |
| B-51 | chadwick-source-review 1.1: inventory upstream vs registry (card C-01) | DONE (findings in design.md) | see the card |
| B-52 | chadwick-source-review 1.2: adapter conformance, no hard-coded dataset names (card C-02) | DONE (findings in design.md) | see the card |
| B-53 | chadwick-source-review 1.3: generated schema vs real data (card C-03) | DONE (findings in design.md) | see the card |
| B-54 | chadwick-source-review 1.4: code review against the designated tools (card C-04) | DONE (findings in design.md) | see the card |
| B-55 | chadwick-source-review 2.1: spec and test gaps (card C-05) | DONE | see the card |
| B-56 | chadwick-source-review 3.1: live verification on a scratch home (card C-06) | DONE | see the card |
| B-57 | chadwick-source-review 3.2: export through every sink (card C-07) | DONE | see the card |
| B-58 | chadwick-source-review 4.1: docs, ADRs, spec merge, archive (card C-08) | DONE | see the card |
| B-59 | chadwick-source-review 5.1: split ingest from the lookup index (card C-09) | DONE | see the card |
| B-60 | chadwick-source-review 5.2: registry-driven adapter, per-dataset jobs (card C-10) | DONE | see the card |
| B-61 | chadwick-source-review 5.3: resolve_id explicit column map, BBREF_MINORS bug (card C-11) | DONE | see the card |
| B-62 | chadwick-source-review 5.4: vectorised index, duplicate guard, record types (card C-12) | DONE | see the card |
| B-63 | chadwick-source-review 5.5: data-driven nicknames, vectorised search (card C-13) | DONE | see the card |
| B-64 | chadwick-source-review 5.6: keep the upstream README, correct spec and docs (card C-14) | DONE | see the card |
| B-65 | data-workflow-standard 1.1: owner picks the update-check rule and the dlt role (design.md decisions A and B) | DONE (ADR 43 and 44, 2026-10-29) | two ADRs written; B-43 brainstorm can build on them |
| B-66 | data-workflow-standard 2.1: manifest records an upstream fingerprint per raw file | DONE | `RawStore.put` takes it, tests, git sources store the tree blob SHA |
| B-67 | data-workflow-standard 2.2: one shared `is_current()` for every source | DONE | per-source checks replaced one source at a time inside the source tracks, tests |
| B-68 | data-workflow-standard 2.3: `baseballpy cache check` | DONE | verifies sha256 of local files and lists files whose upstream fingerprint changed, CliRunner test, `docs/CLI.md` regenerated |
| B-69 | data-workflow-standard 3.1: `docs/DATA_WORKFLOW.md` | DONE | five-step workflow, cache folders and overrides, every read and export path, linked from README and ARCHITECTURE |
| B-70 | data-workflow-standard 2.4: ingest jobs report skipped work in the audit log (cache_hit) | DONE | a cached rerun logs cache_hit=true; test added |
| B-71 | data-workflow-standard 2.5: Lahman records fingerprints and decides with is_current() (done by lahman-source-review 5.1 and 5.2 = B-90 and B-91; tick both tasks when they finish) | DONE | upstream.is_current used, blob fingerprints in the raw manifests, `cache check --upstream` shows no unfingerprinted Lahman file |
| B-72 | data-workflow-standard 2.6: Retrosheet records fingerprints and decides with is_current() | DONE (retrosheet-source-review 5.1, 5.2; ADR 48) | same as B-71 for Retrosheet |
| B-73 | data-workflow-standard 2.7: Statcast records fingerprints and decides with is_current() | DONE (statcast-source-review 5.1, 5.2; ADR 52) | content or ETag fingerprints recorded, time-to-live kept for how often to ask |
| B-74 | data-workflow-standard 2.8: MLB API records fingerprints and decides with is_current() | DONE (mlb_api-source-review 5.1, 5.2; ADR 43, 49) | same as B-73 for the MLB API |
| B-75 | chadwick-complete-access 1.1-3.1: process-wide register cache, full PlayerRecord, access to all four datasets, cited descriptions, docs, spec merge | DONE (archived 2026-10-29) | Chadwick has no open tasks; remaining Chadwick-adjacent work is only B-43 (export command, CSV/PostgreSQL) and the Retrosheet use of the Chadwick software tools |

## L. Export workflow, Chadwick as the model (`export-workflow`, replaces B-43 and B-44)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-76 | export-workflow 1.1: owner answers decisions A to D, ADR 46 | DONE | four answers recorded, ADR 46 written |
| B-77 | export-workflow 2.1: `exports/` tier in LakeConfig and path rules | DONE | paths from design.md, override env var, tests |
| B-78 | export-workflow 2.2: CSV sink with `.schema.json` sidecar | DONE | Arrow round trip through CSV equals the original table, tests |
| B-79 | export-workflow 2.3: typed dlt database sink | DONE | explicit column types and registry key passed to dlt; replace/append/merge tests on DuckDB and embedded Postgres |
| B-80 | export-workflow 2.4: `export_dataset()` with verify and audit | DONE | rows and schema read back, audit event written, tests |
| B-81 | export-workflow 2.5: `baseballpy export` command | DONE | CliRunner tests, `docs/CLI.md` regenerated |
| B-82 | export-workflow 3.1: round-trip tests for all four targets | DONE | Parquet, CSV, DuckDB, embedded Postgres; Postgres skipped when `pgserver` is absent |
| B-83 | export-workflow 4.1: export all Chadwick datasets to every target | DONE | numbers and comparison recorded in design.md |
| B-84 | export-workflow 4.2: export section of `docs/DATA_WORKFLOW.md` and the source-onboarding checklist | DONE | page written, exceptions listed |
| B-85 | export-workflow 5.1: spec delta merged, ADR, archive | DONE | change archived, specs validate |

## Source review: Lahman (`lahman-source-review`, track 2)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-86 | lahman-source-review 1.1: Inventory the provider against the registry (card L-01) | DONE (findings in design.md S1-S4) | see the card |
| B-87 | lahman-source-review 1.2: Check registry and adapter conformance (card L-02) | DONE (findings in design.md S1-S4) | see the card |
| B-88 | lahman-source-review 1.3: Compare the generated schema with real data (card L-03) | DONE (findings in design.md S1-S4) | see the card |
| B-89 | lahman-source-review 1.4: Review the code against the designated tools and decoupling rules (card L-04) | DONE (findings in design.md S1-S4) | see the card |
| B-90 | lahman-source-review 5.1: Record upstream fingerprints for every raw file (card L-05) | DONE | see the card |
| B-91 | lahman-source-review 5.2: Decide currency with is_current() at every cache tier (card L-06) | DONE | see the card |
| B-92 | lahman-source-review 5.3: Keep the provider's documentation files (card L-07) | DONE | see the card |
| B-93 | lahman-source-review 5.4: Review the second way in (user-supplied files); N/A if the source has none (card L-08) | DONE | see the card |
| B-94 | lahman-source-review 5.5: Make every dataset and column reachable from Python (card L-09) | DONE | see the card |
| B-95 | lahman-source-review 2.1: Close the spec and test gaps (card L-10) | DONE | see the card |
| B-96 | lahman-source-review 3.1: Live verification on a clean scratch home (card L-11) | DONE | see the card |
| B-97 | lahman-source-review 3.2: Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (card L-12) | DONE | see the card |
| B-98 | lahman-source-review 3.3: Cited column descriptions (card L-13) | DONE | see the card |
| B-99 | lahman-source-review 4.1: Docs, decisions, spec merge, archive (card L-14) | DONE | see the card |
| B-100 | lahman-source-review 5.6: Quality checks independent of load order, every id column, visible to users (card L-15) | DONE | see the card |
| B-101 | lahman-source-review 5.7: Pin the table-name lists together with a test; case-insensitive names (card L-16) | DONE | see the card |
| B-102 | lahman-source-review 5.8: One consistent raw manifest entry per file; remove unused extractor code (card L-17) | DONE | see the card |
| B-103 | lahman-source-review 5.9: Ingest jobs report cache hits (card L-18) | DONE | see the card |
| B-104 | data-workflow-standard 2.9: `cache check --upstream` says so when nothing could be compared | DONE | message fixed, CliRunner test |

## Source review: Retrosheet (`retrosheet-source-review`, track 3)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-105 | retrosheet-source-review 1.1: Inventory the provider against the registry (card R-01) | DONE | see the card |
| B-106 | retrosheet-source-review 1.2: Check registry and adapter conformance (card R-02) | DONE | see the card |
| B-107 | retrosheet-source-review 1.3: Compare the generated schema with real data (card R-03) | DONE | see the card |
| B-108 | retrosheet-source-review 1.4: Review the code against the designated tools and decoupling rules (card R-04) | DONE | see the card |
| B-109 | retrosheet-source-review 5.1: Record upstream fingerprints for every raw file (card R-05) | DONE | see the card |
| B-110 | retrosheet-source-review 5.2: Decide currency with is_current() at every cache tier (card R-06) | DONE | see the card |
| B-111 | retrosheet-source-review 5.3: Keep the provider's documentation files (card R-07) | DONE | see the card |
| B-112 | retrosheet-source-review 5.4: Review the second way in (user-supplied files); N/A if the source has none (card R-08) | DONE | see the card |
| B-113 | retrosheet-source-review 5.5: Make every dataset and column reachable from Python (card R-09) | DONE | see the card |
| B-114 | retrosheet-source-review 2.1: Close the spec and test gaps (card R-10) | DONE | see the card |
| B-115 | retrosheet-source-review 3.1: Live verification on a clean scratch home (card R-11) | DONE | see the card |
| B-116 | retrosheet-source-review 3.2: Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (card R-12) | DONE | see the card |
| B-117 | retrosheet-source-review 3.3: Cited column descriptions (card R-13) | DONE | see the card |
| B-118 | retrosheet-source-review 4.1: Docs, decisions, spec merge, archive (card R-14) | DONE | see the card |
| B-119 | retrosheet-source-review 5.6: Store every event field chadwickpy emits and key events on (GAME_ID, EVENT_ID) (card R-15) | DONE | see the card |
| B-120 | retrosheet-source-review 5.7: One declarative dataset-to-producer map: every registry name works with --datasets, one download per ingest (card R-16) | DONE | see the card |
| B-121 | retrosheet-source-review 5.8: No silent loss in game logs and rosters: quarantine short rows, keep extra fields in _extras (card R-17) | DONE | see the card |
| B-122 | retrosheet-source-review 5.9: Box parser: keep repeated info keys, safe dates, BoxParseError for bad numbers (card R-18) | DONE | see the card |
| B-123 | retrosheet-source-review 5.10: Shared stores: an empty rebuild removes the stale Parquet; stale .part files cleaned in processed/; quarantine follows the source's lake (card R-19) | DONE | see the card |
| B-124 | retrosheet-source-review 5.11: Export streams one season at a time (card R-20) | DONE | see the card |
| B-125 | retrosheet-source-review 5.12: Really stream box scores and box accounts; count rows without re-reading Parquet (card R-21) | DONE | see the card |
| B-126 | retrosheet-source-review 5.13: Data-quality checks across datasets, shown by catalog status (card R-22) | DONE | see the card |
| B-127 | retrosheet-source-review 5.14: boxscores_batting has no unique key (card R-23) | DONE | see the card |
| B-128 | retrosheet-source-review 5.15: Audit-log and time every Retrosheet operation (card R-24) | DONE | see the card |
| B-129 | retrosheet-source-review 5.16: rosters key is not unique; add a roster column (card R-25) | DONE | see the card |
| B-130 | retrosheet-source-review 5.17: substitutions key is not unique; add SUB_FLD_CD (card R-26) | DONE | see the card |
| B-131 | retrosheet-source-review 5.18: box_starters key is not unique; add position (card R-27) | DONE | see the card |
| B-132 | retrosheet-source-review 3.4: Processed chunks are not rebuilt when the schema changes (card R-28) | DONE | see the card |
| B-138 | retrosheet-source-review 5.19: Event text fields: missing means NULL so CSV round-trips; parser revision replaces older chunks (card R-29) | DONE | see the card |

## dlt processed-tier spike (`dlt-processed-tier-spike`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-133 | dlt-processed-tier-spike 1.1: ingest Lahman with the current path into a scratch lake and record the numbers | DONE | see design.md |
| B-134 | dlt-processed-tier-spike 1.2: write the dlt loader script for the same tables | DONE | see design.md |
| B-135 | dlt-processed-tier-spike 1.3: compare layout, types, row equality, seconds, code size | DONE | see design.md |
| B-136 | dlt-processed-tier-spike 1.4: schema change, interrupt and resume, repeat run, partition layout, what is lost | DONE | see design.md |
| B-137 | dlt-processed-tier-spike 2.1: ADR 50, recommendation, TOOLING.md, archive | DONE | see design.md |

## Source review: Statcast (`statcast-source-review`, track 4)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-139 | statcast-source-review 1.1: Inventory the provider against the registry (card S-01) | DONE | see the card |
| B-140 | statcast-source-review 1.2: Check registry and adapter conformance (card S-02) | DONE | see the card |
| B-141 | statcast-source-review 1.3: Compare the generated schema with real data (card S-03) | DONE | see the card |
| B-142 | statcast-source-review 1.4: Review the code against the designated tools and decoupling rules (card S-04) | DONE | see the card |
| B-143 | statcast-source-review 5.1: Record upstream fingerprints for every raw file (card S-05) | DONE | see the card |
| B-144 | statcast-source-review 5.2: Decide currency with is_current() at every cache tier (card S-06) | DONE | see the card |
| B-145 | statcast-source-review 5.3: Keep the provider's documentation files (card S-07) | DONE | see the card |
| B-146 | statcast-source-review 5.4: Review the second way in (user-supplied files); N/A if the source has none (card S-08) | DONE | see the card |
| B-147 | statcast-source-review 5.5: Make every dataset and column reachable from Python (card S-09) | DONE | see the card |
| B-148 | statcast-source-review 2.1: Close the spec and test gaps (card S-10) | DONE | see the card |
| B-149 | statcast-source-review 3.1: Live verification on a clean scratch home (card S-11) | DONE | see the card |
| B-150 | statcast-source-review 3.2: Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (card S-12) | DONE | see the card |
| B-151 | statcast-source-review 3.3: Cited column descriptions (card S-13) | DONE | see the card |
| B-152 | statcast-source-review 4.1: Docs, decisions, spec merge, archive (card S-14) | DONE | see the card |
| B-153 | statcast-source-review 5.6: Audit-log and time the game-feed fetch and season ingest (card S-15) | DONE | see the card |
| B-154 | statcast-source-review 5.7: Export read-back: dictionary columns of several stored parts (card S-16) | DONE | see the card |

## Source review: MLB API (`mlb_api-source-review`, track 5)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-155 | mlb_api-source-review 1.1: Inventory the provider against the registry (card M-01) | DONE | see the card |
| B-156 | mlb_api-source-review 1.2: Check registry and adapter conformance (card M-02) | DONE | see the card |
| B-157 | mlb_api-source-review 1.3: Compare the generated schema with real data (card M-03) | DONE | see the card |
| B-158 | mlb_api-source-review 1.4: Review the code against the designated tools and decoupling rules (card M-04) | DONE | see the card |
| B-159 | mlb_api-source-review 5.1: Record upstream fingerprints for every raw file (card M-05) | DONE | see the card |
| B-160 | mlb_api-source-review 5.2: Decide currency with is_current() at every cache tier (card M-06) | DONE | see the card |
| B-161 | mlb_api-source-review 5.3: Keep the provider's documentation files (card M-07) | DONE | see the card |
| B-162 | mlb_api-source-review 5.4: Review the second way in (user-supplied files); N/A if the source has none (card M-08) | DONE | see the card |
| B-163 | mlb_api-source-review 5.5: Make every dataset and column reachable from Python (card M-09) | DONE | see the card |
| B-164 | mlb_api-source-review 2.1: Close the spec and test gaps (card M-10) | DONE | see the card |
| B-165 | mlb_api-source-review 3.1: Live verification on a clean scratch home (card M-11) | DONE | see the card |
| B-166 | mlb_api-source-review 3.2: Export checklist (docs/DATA_WORKFLOW.md, Onboarding a source) (card M-12) | DONE | see the card |
| B-167 | mlb_api-source-review 3.3: Cited column descriptions (card M-13) | DONE | see the card |
| B-168 | mlb_api-source-review 4.1: Docs, decisions, spec merge, archive (card M-14) | DONE | see the card |
| B-169 | mlb_api-source-review 5.6: No hard-coded default season; standings honour refresh (card M-15) | DONE | see the card |
| B-170 | mlb_api-source-review 5.7: One refused request must not abort the season job (card M-16) | DONE | see the card |
| B-171 | mlb_api-source-review 5.8: Registered keys unique on real rows (card M-17) | DONE | see the card |
| B-172 | mlb_api-source-review 5.9: `--datasets` accepts any registered dataset name (card M-18) | DONE | see the card |
| B-173 | mlb_api-source-review 5.10: Empty text is NULL; parser revision (card M-19) | DONE | see the card |
| B-174 | mlb_api-source-review 5.11: Remaining non-unique keys (card M-20) | DONE | see the card |
| B-175 | mlb_api-source-review 5.12: team_stats_expected_statistics_hitting recorded unsupported (card M-21) | DONE | see the card |
| B-176 | mlb_api-source-review 5.13: League-wide pools survive the provider's 406 (card M-22) | DONE | see the card |
| B-177 | mlb_api-source-review 5.14: baseballpy probe (card M-23) | DONE | see the card |
