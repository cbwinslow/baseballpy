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
| B-04 | `verify-optin-paths 7`: final report and archive | READY | B-01..B-03 done; report lists verified / not verified / needs-owner; change archived under `openspec/changes/archive/<date>-verify-optin-paths/` with spec deltas merged |
| B-29 | MLB Stats API answers HTTP 403 to our User-Agent (new, found 2026-10-28) | DONE (ADR 40) | owner chose the pybaseball agent on 2026-10-28; was: see section H item 6: until it is resolved B-01, B-03 and the MLB part of B-05 cannot finish; no workaround (such as a different User-Agent) is applied without the owner's decision |
| B-30 | MLB Stats API answers HTTP 406 to every league-wide v1/stats request (new, found 2026-10-29) | EXTERNAL | probed from this PC and the homelab: stats=season, with or without playerPool/limit/sitCodes or a browser User-Agent, gives 406; v1/teams and v1/people/{id}/stats give 200; it worked earlier on 2026-10-29. Retest later (one request per hour at most); when it answers 200 again re-run the 15 failed pools (3 had provider 503 on deep offsets: smaller pages or a per-season split) and do not mark the 12 stat_splits pools unsupported without a 200-control. Never run the full gen_mlb_schemas.py while it persists (phase 1 wrote an empty combo table) |

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
| B-12 | `repo-hygiene-and-docs-sync 6.4`: merge deltas and archive | after B-01, B-03 (EXTERNAL), B-09, B-14, B-20 (OWNER) | every other change is archived or explicitly deferred by the owner; `openspec validate --specs` 14 of 14 (or more); `EXECUTION_ORDER.md` current |
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

## F. Retrosheet CSV bundles (`retrosheet-csv-bundles`)

Proposal and reachability evidence exist; nothing is implemented. The Retrosheet ingest keeps pulling
from retrosheet.org only (owner rule); code as if no user is blocked.

| ID | Task | Status | Done when |
|---|---|---|---|
| B-20 | `retrosheet-csv-bundles 0`: owner approval | OWNER | the owner says in chat to implement the change |
| B-21 | `retrosheet-csv-bundles 1`: read the CSV overview and contents pages | EXTERNAL | pages read (retrosheet.org or an owner-supplied copy for exploration only); file names, columns, licence in `design.md` |
| B-22 | retrosheet-csv-bundles 2: how others consume the bundles | DONE | R `retrosheet`, `calestini/retrosheet`, `jerryword/retrosheet-csv`, Chadwick: findings and links in `design.md` |
| B-23 | `retrosheet-csv-bundles 3`: generator and strict schemas | after B-20, B-21 | a `scripts/gen_*` script downloads one small season, widens types, writes schemas and registers datasets with keys |
| B-24 | `retrosheet-csv-bundles 4`: adapter wiring | after B-23 | new task names through `IngestAdapter`, no change to existing ones; `unsupported` entries carry `tried` and `verified_on` |
| B-25 | `retrosheet-csv-bundles 5`: tests, docs, descriptions, licence | after B-24 | no-network tests, docs section, official column descriptions, licence note |
| B-26 | `retrosheet-csv-bundles 6`: live check, gates, archive | after B-25 | one season ingested, gates green, change archived |

## G. Standing stewardship (repeat; not tasks)

Run after every item and whenever idle: `uv run baseballpy catalog audit` and `catalog status --gaps`;
the four gates plus `docs generate --check` and `openspec validate --specs`; re-verify any
`unsupported` entry touched; turn `schema_drift` warnings from real runs into regenerations; keep
`EXECUTION_ORDER.md` and this file current; `uv run python scripts/project_map.py --check`.

## H. Owner decisions pending (ask once, then continue with everything else)

1. Approve or reject `retrosheet-csv-bundles` (B-20).
2. Supply `boxfile.txt`, or say retrosheet.org is reachable from a machine you can use (B-14, B-18, B-21).
3. Name the permanent lake location and approve backfill ranges (B-09).
4. Decide when to push and whether to tag a first release (nothing has been pushed; versioning is in `docs/RELEASING.md`).
5. The host-key mismatch of `cbwdellr720-lan` (use `cbwdellr720` until fixed).
6. Decide how to handle `statsapi.mlb.com` returning 403 to the User-Agent `baseballpy (+https://github.com/cbwinslow/baseballpy)` (B-29): from this PC and the homelab, the same URL answers 200 to `curl/8`, `baseballpy/0.1` and `python-httpx/0.27`, and Savant is unaffected. It began after about 3 h of continuous MLB API requests (first as 500s, then 403s), so it may be a temporary block on that client or a rule against it; I did not change the User-Agent, because that would sidestep a block MLB may have put there on purpose.
