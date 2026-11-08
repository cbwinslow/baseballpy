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
| B-14 | `retrosheet-box-accounts 1.1`: the official `boxfile.txt` | OWNER / EXTERNAL (file blocked from the build env; code verified, interim parser in `box_parser.py` keeps all untyped kinds losslessly in `box_records`; retry when the owner supplies the file or `retrosheet.org` is reachable) | the file is supplied by the owner or retrosheet.org becomes reachable (`curl -I https://www.retrosheet.org/` from the homelab; retry once per session); stored with the Retrosheet notice under `docs/sources/` and the layouts reconciled in `design.md` |
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
| B-36 | mlb-stats-route-406-and-deep-pools 3.2: regenerate the team_stats_year_by_year schemas | DONE (route answers 200; 8 datasets regenerated with --only, 78 new typed stat columns) | fields such as stat.flyHits are typed columns, test added, no full generator run |
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

## N. MLB live feed and pool completion (owner approved the full plan, 2026-10-31)

Two changes from the 2026-10-31 investigation, both closed in this section, plus the audit-trail
verification (B-192–B-194) that closes the telemetry question for every MLB download path. The
single-season family stays blocked; the season-by-season rebuild is B-191 (its own change, not a task of
the finished one). B-190 is the schema-drift regeneration the live split run found.

| ID | Task | Status | Done when |
|---|---|---|---|
| B-178 | mlb-live-feed-projection 1.1: field-set table and parent-key expansion | DONE | `LIVE_FIELD_SETS` holds the five measured sets, a bare string is a set name, an unknown name lists the valid ones, every dotted path expands to all parent keys; the three named tests pass |
| B-179 | mlb-live-feed-projection 1.2: `snapshot()` and `snapshot_bytes()` | DONE | one request, no watermark, `timecode` validated, audit event, `SnapshotError` + quarantine on a missing container; the five named tests pass with fixtures, no network |
| B-180 | mlb-live-feed-projection 1.3: the stream refuses a projection | DONE | `stream_live_events`/`stream_events` raise `ValueError` naming `diffPatch` and `snapshot`; the test passes |
| B-181 | mlb-live-feed-projection 1.4: live check of every set | DONE | all five sets answer 200, are smaller than 663,043 bytes and carry the keys they promise; numbers under "As built" in `design.md` |
| B-182 | mlb-live-feed-projection 1.5: docs, ADR 54, spec merge, archive | DONE | the projection section is in `docs/sources/mlb_api.md`, the delta is merged, the change is archived, gates green |
| B-183 | mlb-pool-fallback-completion 2.1: list-encode multi-value hydrate parameters | DONE | `HYDRATE_LIST_PARAMS`/`_hydrate_value` bracket-encode `group`, `type`, `sitCodes` and `metrics`, an empty one is omitted; a mocked `vr,vl` answer stores two split codes (two named tests) |
| B-184 | mlb-pool-fallback-completion 2.2: per-stat-type revision for split pools | DONE | `MLB_STAT_TYPE_REVISIONS` keys `statSplits`/`statSplitsAdvanced` on the endpoint's `stats` parameter (revision 2), every other MLB dataset keeps 1; a part written under revision 1 is stale, a non-split part is still served (test passes) |
| B-185 | mlb-pool-fallback-completion 2.3: refuse a stat type with no person equivalent | DONE | a 406 on `statsSingleSeason` raises `PoolFallbackUnavailableError` naming the type, the measured evidence and the design section; the people route is not called, no empty part is stored, a `keep_going` run reports it (test passes) |
| B-186 | mlb-pool-fallback-completion 2.4: halve a hydrate batch on 414 | DONE | a 414 halves the batch and asks for the same players again, down to one id where the error propagates; every 200 page is kept raw under a unique `.hydrate.pN.json` name (two tests) |
| B-187 | mlb-pool-fallback-completion 2.5: live proof of every split pool | DONE | all 10 `stats_stat_splits_*` pools stored on a scratch lake (2025, sport 1, 1,470 players, 10 hydrate pages each) with 0 errors and 0 quarantine; the busiest subject's codes equal the person route's for `statSplits` and `statSplitsAdvanced`; rows, pages, MB, seconds and the single-season block are under "As built" in `design.md` |
| B-188 | mlb-pool-fallback-completion 2.6: probe covers the fallback shape | DONE | the new canary sends `sitCodes=[vr,vl]` with the fallback text, answered 200 in a live `baseballpy probe --season 2025` and is visible in the CLI table; the test passes |
| B-189 | mlb-pool-fallback-completion 2.7: docs, ADR 55, spec merge, archive | DONE | the pool section is in `docs/sources/mlb_api.md`, ADR 53's consequences are updated, the delta is merged, the change is archived, gates green |
| B-190 | mlb-schema-drift-regeneration: Regenerate the typed schemas through the hydrate fallback | DONE | stats_stat_splits_* carry gameType, numTeams and sport.abbreviation as typed columns instead of _extras, generated by scripts/gen_mlb_schemas.py from hydrate payloads; probe JSON, fixtures and mlb_tables.py committed, anti-drift test passes, docs generate --check green |
| B-191 | Season-by-season rebuild of the single-season pools (new, design D5) | READY (needs its own change: season enumeration, first season, era-sport mapping) | `stats_stats_single_season_*` and `..._advanced_*` are built from `/v1/sports/{id}/players?season=Y` plus `type=[season],season=Y` in hydrate batches, with rows, requests and the 503 block recorded; the pools stop depending on the refused deep-offset direct route |
| B-192 | mlb-api-audit-trail 3.1: one test per MLB download path | DONE | `tests/test_mlb_audit.py` reads the events back for a declarative endpoint (cold and cached), a raw-only endpoint, the pool fallback, a projected snapshot, a finished stream and a refused request; all six pass |
| B-193 | mlb-api-audit-trail 3.2: Telemetry section in `docs/sources/mlb_api.md` | DONE | every operation the code emits is listed once with what it records, plus the three reader commands |
| B-194 | mlb-api-audit-trail 3.3: spec merge, archive, gates | DONE | the delta is merged into the mlb-api-ingestion spec, the change is archived, gates green |

## O. Cross-source catalog audit and master coverage matrix

| ID | Task | Status | Done when |
|---|---|---|---|
| B-195 | cross-source-catalog-audit 1.1: master coverage scanner | DONE | scripts/master_coverage_audit.py parses reference files and extracts capabilities mapped to DATASETS |
| B-196 | cross-source-catalog-audit 1.2: master coverage matrix | DONE | docs/MASTER_COVERAGE_MATRIX.md generated with domain mappings, dataset names, endpoints, and evidence notes |
| B-197 | cross-source-catalog-audit 1.3: coverage matrix tests | DONE | tests/test_coverage_matrix.py passes asserting 100% of DATASETS and external references accounted for |
| B-198 | cross-source-catalog-audit 1.4: spec merge, archive, gates | DONE | spec delta merged, change archived, all gates green |

## P. V1 Coverage, completeness, and smart concurrency (`v1-coverage-and-smart-concurrency`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-199 | v1-coverage-and-smart-concurrency 1.1: author proposal, design, tasks, spec deltas | DONE | proposal.md, design.md, tasks.md, spec deltas in place, openspec validate passes |
| B-200 | v1-coverage-and-smart-concurrency 1.2: smart concurrency for MLB API hydrate batches and season endpoints | DONE | hydrate batches in _pool_pages_by_hydrate and season endpoints run concurrently bounded by max_concurrency and 8 req/s token bucket |
| B-201 | v1-coverage-and-smart-concurrency 1.3: concurrency verification across Statcast and Retrosheet | DONE | Statcast and Retrosheet multi-chunk / multi-season runs verified with bounded workers and rate limit adherence |
| B-202 | v1-coverage-and-smart-concurrency 1.4: `baseballpy catalog coverage` expected-vs-held CLI command | DONE | command outputs expected vs held games, % held, missing IDs, and copy-paste remediation commands |
| B-203 | v1-coverage-and-smart-concurrency 1.5: tests, documentation, gates, spec merge, and archive | DONE | unit/integration tests pass, all gates green, spec deltas merged into openspec/specs, change archived |

## Q. V1 Ergonomics, auto-sync, and end-to-end verification (`v1-ergonomics-and-e2e-verification`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-204 | v1-ergonomics-and-e2e-verification 1.1: author proposal, design, tasks, spec deltas | DONE | proposal.md, design.md, tasks.md, spec deltas in place, openspec validate passes |
| B-205 | v1-ergonomics-and-e2e-verification 1.2: automatic DuckDB catalog sync on ingest | DONE | baseballpy ingest automatically updates DuckDB views upon completion with --sync-db/--no-sync-db, test passes |
| B-206 | v1-ergonomics-and-e2e-verification 1.3: catalog coverage --fix auto-remediation | DONE | catalog coverage --fix executes remediation jobs directly and updates coverage report, test passes |
| B-207 | v1-ergonomics-and-e2e-verification 1.4: live end-to-end test on 2024 MLB data | DONE | live ingest of 2024 season and sample games completes, DuckDB views queryable via SQL, coverage verifies |

| B-208 | v1-ergonomics-and-e2e-verification 1.5: tests, gates, documentation, spec merge, and archive | DONE | all gates green, spec deltas merged into openspec/specs, change archived |

## R. Auto-concurrency and intra-source parallelism (`auto-concurrency-and-intra-source-parallelism`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-209 | auto-concurrency-and-intra-source-parallelism 1.1: centralized `resolve_concurrency` utility | DONE | `src/baseballpy/core/concurrency.py` provides `resolve_concurrency` with CPU detection, cap, and validation |
| B-210 | auto-concurrency-and-intra-source-parallelism 1.2: auto-concurrency in `run_jobs` runner | DONE | `src/baseballpy/ingest/runner.py` accepts `concurrency=None`/`"auto"` and resolves dynamically |
| B-211 | auto-concurrency-and-intra-source-parallelism 1.3: CLI option updates in `cli_ingest.py` | DONE | `--concurrency` defaults to auto, displays resolved worker count in UI |
| B-212 | auto-concurrency-and-intra-source-parallelism 1.4: unit and property tests | DONE | tests in `tests/test_auto_concurrency.py` verify resolution across simulated CPU counts and boundaries |
| B-213 | auto-concurrency-and-intra-source-parallelism 1.5: docs, gates, spec merge, and archive | DONE | docs generated, all gates green, spec deltas merged, change archived |






## S. Statcast season bounds (`statcast-season-bounds`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-214 | statcast-season-bounds 1.1: delete stray pre-2008 data | DONE (87 season folders and 122 manifest entries removed from the owner's lake on 2026-11-03, owner approved) | the pre-2008 season folders and manifest entries are gone |
| B-215 | statcast-season-bounds 1.2: `seasons.py` and the entry points | DONE | every Statcast entry point applies the bound before any request, tests pass |
| B-216 | statcast-season-bounds 1.3: adapter skips, unstarted season skipped | DONE | `skipped` job with reason, test passes |
| B-217 | statcast-season-bounds 1.4: docs, ADR 56, spec merge, live check, archive | DONE | gates green, a named 1850/1990 run makes zero requests, change archived |

## T. Request parallelism and per-host limits (`request-parallelism-and-host-limits`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-218 | request-parallelism-and-host-limits 1.1: per-host in-flight limits in `HttpClient` | DONE | `host_concurrency` and `savant_concurrency` in `RateLimitConfig`, one semaphore per host, tests pass |
| B-219 | request-parallelism-and-host-limits 1.2: MLB request-level parallelism | DONE | `_map_requests` pool in `ingest` and `_ingest_raw_only`, fail-fast and 404 sum tested |
| B-220 | request-parallelism-and-host-limits 1.3: CLI states workers and network limit, docs | DONE | ingest header shows both, QUICKSTART and CLI docs updated, test passes |
| B-221 | request-parallelism-and-host-limits 1.4: tests that prove it | DONE | 14 tests in `tests/test_request_parallelism.py`, mutation-checked |
| B-222 | request-parallelism-and-host-limits 1.5: benchmark before and after | DONE | numbers in the change's design.md (found the job-ordering race) |
| B-223 | request-parallelism-and-host-limits 1.6: Savant in-flight measured live | DONE | cold-cache 4 vs 8 recorded, default 8 chosen |
| B-224 | request-parallelism-and-host-limits 1.7: specs, AGENTS.md, ADR 57, gates, archive | DONE | specs merged, ADR 57, gates green, change archived |

## U. MLB drift warnings once per dataset (`mlb-drift-warn-once`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-225 | mlb-drift-warn-once 1.1: warn once per dataset and field | DONE | the MLB normalizer uses `warn_drift_once`, one warning for five identical payloads (test), scenario cites the test |

## V. Adaptive per-host concurrency (`adaptive-host-concurrency`, rejected after measurement)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-226 | adaptive-host-concurrency 1.1: `AdaptiveGate` | DONE (built, discarded: ADR 58) | the gate and its tests were built and mutation-checked, then removed after the live results |
| B-227 | adaptive-host-concurrency 1.2: wire into the client, config and pools | DONE (built, discarded: ADR 58) | as above |
| B-228 | adaptive-host-concurrency 1.3: live Savant test | DONE | adaptive 16 vs pinned 8: same rows per second, 0 back-offs (design.md of the archived change) |
| B-229 | adaptive-host-concurrency 1.4: live MLB tests | DONE | rate-bound pools unaffected; `stats_leaders` not faster with adaptive (40.9 s vs 31.9 s mean wall) |
| B-230 | adaptive-host-concurrency 1.5: decision, ADR 58, archive | DONE | ADR 58 written, no code or spec change, change archived |

## W. MLB host rate 10 requests/second (`mlb-rate-10`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-231 | mlb-rate-10 1.1: cold-season test of 8 vs 10 | DONE | 4 cold-season runs, 0 errors, 10/s about 20% faster (design.md) |
| B-232 | mlb-rate-10 1.2: default, specs, doc, test, ADR 59 | DONE | default 10.0, specs and source doc say 10, test passes |
| B-233 | mlb-rate-10 1.3: full 2024 season run at 10 | DONE | zero errors, time recorded in design.md |
| B-234 | mlb-rate-10 1.4: gates and archive | DONE | gates green, change archived |

## X. Provider partial answers (new, found 2026-11-03)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-235 | detect valid-but-partial provider answers for fixed-size endpoints | DONE (change `verify-small-answers`, owner chose the verify option 2026-11-03) | low-volume small answers are fetched twice and the largest kept; see B-236..B-239 |

## Y. Verify small answers (`verify-small-answers`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-236 | verify-small-answers 1.1: settings and `_verified_get` | DONE | `verify_max_requests`, `verify_max_bytes`, the verified fetch used by low-volume single requests |
| B-237 | verify-small-answers 1.2: tests | DONE | four tests in `tests/test_verify_small_answers.py` pass, one mutation-checked |
| B-238 | verify-small-answers 1.3: live check and extra-request count | DONE | the standings request verified live, extra requests of a season counted in design.md |
| B-239 | verify-small-answers 1.4: spec, doc, ADR 60, gates, archive | DONE | spec merged, ADR 60, gates green, change archived |

## Z. Retrosheet parallel parsing (`retrosheet-parallel-parse`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-240 | retrosheet-parallel-parse 1.1: default workers from the CPU count, cap 16 | DONE | default `min(cpus, 16)`, tests unaffected (in-process unless asked) |
| B-241 | retrosheet-parallel-parse 1.2: one persistent shared pool, bounded window, ordered results | DONE | four pool tests pass |
| B-242 | retrosheet-parallel-parse 1.3: build steps of a season together | DONE (measured, not needed, not built) | see the change's design.md |
| B-243 | retrosheet-parallel-parse 1.4: before and after on real seasons | DONE | season and multi-season times in design.md, every table equal to the single-core run |
| B-244 | retrosheet-parallel-parse 1.5: spec, docs, ADR 61, gates, archive | DONE | gates green, change archived |
| B-245 | project-local-data-folder 1.1-1.4: default `.baseballpy` in the project folder, ignore, tests, docs, ADR 62 | DONE | `tests/test_default_home.py` passes |
| B-246 | readable-lake-names 1.1-1.4: short part names, clash guard, `_manifest.json`, tests, docs, ADR 63 | DONE | `tests/test_part_names.py` passes |
| B-247 | tolerant-box-cells 1.1-1.3: bad box-account cells to NULL + quarantine, tests, ADR 64, 22 seasons re-run | DONE | 22 of 22 seasons completed, `catalog audit` clean |
| B-248 | underscore-table-names 1.1-1.4: one underscore name per table, naming test, ADR 65, how-to guide, Lahman reloaded | DONE | `tests/test_table_names.py` passes |
| B-249 | season-calendar 1.1-1.3: seasons exist once their first day arrives, calendar-based `all_seasons`, January tests, ADR 66 | DONE | `tests/test_season_calendar.py` passes |
| B-250 | audit-speed-check 1.1-1.4: `http_request` audit events, `audit speed` command, tests, ADR 67 | DONE | `tests/test_audit_speed.py` passes |
| B-251 | lahman-folder-case 1.1-1.3: any spelling resolves to one folder, migrate uses registry names, case-sensitive test run (fix for the Linux CI failures) | DONE | full suite passes in a case-sensitive folder |

## AA. Code tightening (`code-tightening`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-252 | code-tightening 1.1: `parse_seasons` and `run_jobs` split into helpers | DONE | gates green, complexity count 7 to 5 |
| B-253 | code-tightening 1.2: `ingest_cmd` and `migrate.retrosheet` split into helpers | DONE | complexity count 5 to 3, gates green |
| B-254 | code-tightening 1.3: `requests_for` and `parse_box_text` split into helpers | DONE | old and new compared: 2,184 request sets and 428 real box files identical |
| B-255 | code-tightening 1.4: `StatcastAdapter.run` split into one method per task | DONE | 7,680 stubbed runs identical, complexity check clean |
| B-256 | code-tightening 1.5: spec, ADR 69, gates, archive | DONE | change archived |
| B-257 | mlb-backfill-fixes 1.1-1.2: fast manifest saves, request duration inside the slot, big-manifest test | DONE | `tests/test_hardening.py::test_a_big_manifest_with_many_busy_writers_never_times_out` passes |
| B-258 | mlb-backfill-fixes 1.3: gates, commit, re-run season 2011 | DONE | 2011 completed (2,637 rows added), re-run peaked at 4 of 4 in flight |
| B-259 | mlb-stats-route-memory 1.1-1.2: remember a refused `/v1/stats` for an hour, test, spec, ADR 68 | DONE | `tests/test_mlb_coverage.py::test_a_refused_stats_route_is_asked_once_then_retested_after_an_hour` passes |


## AB. Modelling data needs (`modelling-data-needs`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-260 | modelling-data-needs 1.1: verify the "have" column against the lake | DONE | row counts and gaps per dataset verified against lake and written into design.md |
| B-261 | modelling-data-needs 1.2: owner grilling, decisions D1 to D6 | DONE | closed out per owner directive (out of project scope; belongs in sabermetricspy) |
| B-262 | modelling-data-needs 1.3: open one change per missing source | DONE | closed out per owner directive |
| B-263 | modelling-data-needs 1.4: as-of rule as a spec requirement with a test | DONE | closed out per owner directive |
| B-265 | modelling-data-needs 1.5: sweep the feed per season for the first pregame stamp | DONE | closed out per owner directive |
| B-264 | modelling-data-needs 1.6: spec, ADR, gates, archive | DONE | change archived |

## AC. Market sources (`market-sources`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-266 | market-sources 1.1: owner decisions M1 to M4 | DONE | decisions recorded in design.md (M1 all MLB markets, M2 API downloaders first) |
| B-267 | `market-sources 1.2`: probe and research both APIs | OPEN | evidence in design.md |
| B-268 | market-sources 1.3: measure the homelab MLB subset, pick the transfer route | DONE | numbers and route in design.md (Kalshi candles 213M / 1.4GB, Polymarket 604M / 0.9GB) |
| B-269 | market-sources 2.1: Kalshi trades and candlesticks code, per open date, opt-in (ADR 71) | DONE | 3 real dates: 6,078 requests, 0 retries, 346,259 trades and 18,061 candles, none in _extras |
| B-270 | market-sources 2.2: Polymarket source (catalog, hourly prices), ADR 77 | DONE | tests/test_polymarket.py (13), tests/test_infer_types.py (3); real run 11,653 events, 233,923 markets, 467,846 outcomes |
| B-271 | `market-sources 3.1`: one-time import of the homelab MLB subset | OPEN | typed Parquet in the lake, sample checked against the APIs |
| B-272 | `market-sources 3.2`: close the gap to today | OPEN | no missing days between import and now |
| B-273 | `market-sources 4.1`: docs, specs, ADRs, gates, archive | OPEN | change archived |
| B-274 | market-sources 2.1 part 1: Kalshi catalog (series, events, markets), signing, decimal types, ADR 70 | DONE | 189 series, 55,197 events, 900,555 markets in the lake, speed audit clean, 13 Kalshi tests pass |
| B-275 | market-sources 2.3: run the full Kalshi trades and candlesticks backfill, tune the speed | DONE | all 447 open dates complete (110,994,885 trades, 14,903,320 candles, compacted to 11 files) |
| B-276 | `market-sources 2.4`: contract check of the Kalshi routes against the official OpenAPI spec | OPEN | a test or command flags new and removed routes |
| B-277 | market-sources: one baseballpy process per host (OS file lock), ADR 72 | DONE | tests/test_hostlock.py: second process refused, crash frees the host, opt-out works |

## AD. Lake access and compaction (`lake-access-and-compaction`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-278 | lake-access-and-compaction 1.1: views without union_by_name, schema equality test | DONE | count 2.1 to 1.3 s, season 5.4 to 4.6 s; bulk rows go through read (2.0 s); db sync over 15 min until compaction |
| B-279 | lake-access-and-compaction 1.2: baseballpy.read and baseballpy.sql with recipes, ADR 73 | DONE | tests/test_access.py (7 tests): read equals sql, join, read-only; all 14,971,703 pitches by 121 columns in 2.0 s |
| B-280 | lake-access-and-compaction 2.1: compact command, ADR 74 | DONE | 9 tests; real lake 400,000 files to about 4,300, db sync 15 min to 20 s, MLB season with all chunks downloaded 6 h to 57 s with no request |
| B-281 | lake-access-and-compaction 2.2: compressed raw files and compress-raw command, ADR 75 | DONE | raw 30.87 GB to 6.10 GB; cache check ok on all 252,542 files; tests/test_raw_compress.py (7) |
| B-282 | lake-access-and-compaction 2.3: offline layout check catalog layout, ADR 76 | DONE | tests/test_layout_audit.py (7); real lake: no failing finding, 9 Retrosheet datasets advise small row groups |
| B-283 | lake-access-and-compaction 3.1: run on the lake and record sizes and times | DONE | numbers in the design of the change (compaction, gzip, queries) |
| B-284 | lake-access-and-compaction 3.2: spec, ADR, docs, gates, archive | DONE | specs lake-access and caching-and-invalidation, ADR 73 to 76, change archived |
| B-285 | lake-access-and-compaction: manifest parsed only when its file changed (three MLB seasons failed with MemoryError and took about 6 h each) | DONE | tests/test_atomic.py: 50 lookups, zero parses, other writers still seen |
| B-286 | coverage audit saw only part- files and guessed 31 Statcast windows; now counts download records and the cached calendar (found by the on-track review) | DONE | tests/test_coverage_audit.py, tests/test_compact.py: Statcast 2024 shows 51 of 51 |
| B-287 | `market-sources 2.5`: Polymarket trades (v2), live snapshots, batch price route | OPEN | owner decision on trader identities; trades or an unsupported verdict with probe evidence |
| B-288 | fangraphs-and-bref 1.1 to 1.3: Baseball-Reference WAR from its published files, FanGraphs not downloaded, ADR 78 | DONE | tests/test_bref.py (7), tests/test_slow_hosts.py (3); real run 126,547 + 57,884 rows, 0 extra requests |
| B-289 | fangraphs-and-bref 2.1: import of the FanGraphs tables held on the homelab (owner said yes), ADR 79 | DONE | tests/test_fangraphs.py (9); 1,219,323 rows equal to the homelab, column totals compared |
| B-290 | `fangraphs-and-bref 2.2`: Baseball-Reference daily WAR archive as an opt-in dataset | OPEN | WAR as of each day, 2018 onward |
| B-291 | fangraphs-and-bref 3.1: slow honest FanGraphs downloader for leaderboards and projections, `--option` switch, ADR 80 | DONE | tests/test_fangraphs_download.py (16); live: 35 requests all 200, 2024 batting equals the homelab copy in 478 columns |
| B-292 | `fangraphs-and-bref 3.2`: downloaders for guts and park factors (web pages), prospects and splits (POST) | OPEN | each dataset downloadable or recorded as not possible with evidence |

## AE. Agent coordination and audit rotation (`agent-coordination-and-audit-rotation`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-293 | agent-coordination-and-audit-rotation 1.1: `baseballpy agent` CLI (`claim`, `release`, `board`), ADR 81 | DONE | tests in `tests/test_agent_cli.py` pass (5/5); claims and releases update both `AGENT_BOARD.md` and `agent_log.jsonl`; 4-hour stale lock detection |
| B-294 | agent-coordination-and-audit-rotation 1.2: `baseballpy audit rotate` and 100 MB automatic threshold, ADR 81 | DONE | tests in `tests/test_audit_rotate.py` pass (4/4); audit log rotated and gzipped when >= 100 MB or via CLI command |
| B-295 | agent-coordination-and-audit-rotation 1.3: OpenCode model default and synergized workflow contract, ADR 81 | DONE | `scripts/opencode_delegate.py` defaults to `opencode/deepseek-v4.1-flash-free`; `AGENTS.md` and `CLAUDE.md` link OpenSpec, Backlog, and Agent Board together |
| B-296 | lake-workflows-and-cli 1.1 to 1.7: `status`, `update`, built-in plans, `current` seasons, manifest-based scan, blank/NaN cells, statcast export path, ADR 82 | DONE | tests/test_workflows.py (10); `status` for 480 datasets in 17.6 s (the footer scan did not finish in 110 s) |
| B-297 | fresh-install-verification 1.1 to 1.3: clean-room install check, newer-DuckDB catalog rebuild, `arrow` backend, pandas message, group hint, ADR 83 | DONE | tests/test_workflows.py (18 in all); wheel installed in an empty venv and used with an empty lake |
| B-298 | folder-and-name-audit 1.1 to 1.3: naming rules written and tested, `UNKNOWN_FOLDER` layout check, README lake drawing, ADR 84 | DONE | tests/test_naming_rules.py (5); audit of 480 datasets and the real lake found 0 violations |
| B-299 | folder-and-name-audit 1.4: stale `raw/mlb_api/standings_postseason` deleted (38 files, 0 records) and the Kalshi private key moved out of the project folder, with the owner's approval | DONE | 0 non-empty files checked before deleting; the key file no longer exists in the repository folder |
| B-300 | mlb-game-levels: `--option sports=` for the per-game MLB download (default major leagues), ADR 85 | DONE | tests/test_mlb_game_levels.py (4); dry runs show `sports=1`; a typo is refused while planning |
| B-301 | mlb-game-memory 1.1: find why a 16,000-game MLB season run ends in `MemoryError` (seen 2026-11-07 after 7.9 h, in the manifest save) | DONE (msgspec zero-copy binary serialization in atomic.py, test_manifest_large_entry_msgspec_roundtrip) | a long game run keeps its memory flat; a test or measurement shows it |
| B-302 | retrosheet-box-accounts 2.4: parse historical qualifiers (Option A: rbi_qualifier, attendance_qualifier, empty strings as null, accept NaN in float columns); drain quarantine | DONE | tests in test_retrosheet_box.py verify qualifiers; 428 raw files parsed cleanly; 0 quarantined records in lake |
| B-303 | mlb-stats-route-406-and-deep-pools 3.3: regenerate the 61 MLB schemas with schema drift in _extras via gen_mlb_schemas.py --only | DONE (142 endpoints gained typed name_slug and similar columns; 25 league-wide stats_* kept unchanged because the 406 cut their sampling) | 61 drifted datasets have typed columns for nameSlug and stats; _extras is empty in fresh samples |
| B-304 | lake-access: compacted files are written by column name so a schema that gained columns does not break rewrites, ADR 86 | DONE | tests/test_compacted_schema.py (3); 2025 major-league games ran 150 s past the old failure point |
| B-305 | lake-schema-evolution 1.1 to 1.4: reads and views survive files written under an older schema; `compact` rewrites mixed-schema files and moves `_extras` values into their typed columns; `db sync` warns; ADR 87 | DONE | tests/test_schema_evolution.py (10), tests/test_access.py; gates green except failures from other agents' unfinished atomic.py work |
| B-306 | `lake-schema-evolution 1.5`: run `baseballpy compact` on the real lake when no ingest is running | OPEN | `catalog layout` has no MIXED_SCHEMA; `read("award_recipients")` returns slugs for all rows |
| B-307 | `lake-schema-evolution 1.6`: gates, merge the spec delta, archive the change | OPEN (after B-306) | change archived, `openspec validate --specs` green |
| B-308 | mlb-game-memory: review and finish the B-301 fix: narrow exceptions, no silent fallback, spec delta, ADR 88, memory measurement | DONE | tests/test_atomic.py (8); 50,000-entry manifest saves in 0.08 s with about 15 MB extra memory |
| B-309 | mlb-stats-route-406-and-deep-pools 3.4: type the fields still landing in `_extras` for the game feed, schedule_postseason, draft_prospects, team_affiliates and rosters (sampled from games that carry them) | DONE (review details and injuryType typed; rare fields without a sampled carrier and the 406 stats_* stay in `_extras`, listed in design.md) | `schema_drift` keys seen in the logs have typed columns, except the stats_* datasets blocked by the 406 (B-30) |
| B-310 | repo-hygiene-and-docs-sync: make main's CI green again: commit the finished B-302 work, fix the NaN-versus-null-token clash it caused, regenerate the project map and coverage matrix | DONE | 1501 tests pass locally; CI result checked after the push |

## AF. Crosswalk suite (`crosswalk-suite`)

| ID | Task | Status | Done when |
|---|---|---|---|
| B-311 | `crosswalk-suite 1.1`: unified game, team, venue crosswalk views and python helpers (bb.games, bb.teams, bb.venues, bb.players) | OPEN | views in DuckDB and python accessors verified with tests in test_crosswalk.py |
| B-311 | crosswalk tests (`tests/test_crosswalk.py`) read the owner's real lake but the test home is isolated, so they fail anywhere without that lake; they are marked `live` for now. Give them small fixture data (a few players, teams, venues, games) so they run in the default gates | OPEN | the 5 tests pass in an empty home without the `live` marker |
| B-312 | cross-platform-support 1.1 to 1.5: LF line endings and `.gitattributes`, `spawn` worker processes, UTF-8 console, an enforcing test, ADR 89 | DONE | tests/test_portability.py (9); full suite 1509 passed |
| B-314 | `cross-platform-support 1.6`: README platforms section, CHANGELOG, gates, CI green on ubuntu and windows, merge the spec delta, archive | OPEN | change archived after CI is green |
| B-313 | `download-queue 1.1`: `select_stages` and `baseballpy backfill --stage` | OPEN | see the change's tasks.md |
| B-315 | `download-queue 1.2`: named single-instance lock, `LakeConfig.state_root` | OPEN | see the change's tasks.md |
| B-316 | `download-queue 1.3`: `ingest/queue.py`: state file, rounds, retries with tenacity, stop event, child-process runner | OPEN | see the change's tasks.md |
| B-317 | `download-queue 1.4`: `baseballpy run` command, CLI docs regenerated | OPEN | see the change's tasks.md |
| B-318 | `download-queue 1.5`: tests/test_queue.py and a dry run against the built-in daily plan | OPEN | see the change's tasks.md |
| B-319 | `download-queue 1.6`: status shows the queue; README, CHANGELOG, ADR 90, gates, spec merge, archive | OPEN | see the change's tasks.md |
