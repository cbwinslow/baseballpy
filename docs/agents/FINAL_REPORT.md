# Status report (2026-10-29)

Replaces the report of 2026-10-28, which predated ADR 40 and the pools run. The next work is the
backlog (`BACKLOG.md`); what is left needs the owner, an external host, or the new change
`mlb-stats-route-406-and-deep-pools`.

## Verified (command, result)

- `uv run pytest`: 985 passed, 5 skipped; `ruff check`, `ruff format --check` and `mypy --strict src`
  clean (run for commit `1729921`; the later commits are documentation only and re-ran the runbook tests).
- Homelab, 2026-10-28/29: default `ingest all`, per-game and per-player families, on-demand datasets,
  the 2015-2024 window with resume, MLB API 1990 and 2024 (654,821 rows, 3,061 s after ADR 40);
  numbers in `docs/BACKFILL.md`, evidence in `openspec/changes/archive/2026-10-30-verify-optin-paths/design.md`.
- All-time pools: 42 of 57 ingested (2,265,447 rows); 15 failed with root causes recorded (B-01 done).
- The two `vs_player_*_opp_team` keys are unique on live data (B-03 done, `KEY_OVERRIDES`).
- All 89 spec scenarios cite a test (`tests/test_spec_scenarios.py`).

## Not verified

- League-wide `v1/stats` answers HTTP 406 to every request from this PC and the homelab (B-30): the
  15 failed pools, the per-season `stats_*` datasets of any new season and the `team_stats_year_by_year_*`
  schema drift cannot be finished until it answers 200.
- The first GitHub run of CI and of the weekly audit workflow (nothing has been pushed).
- A full-history backfill has never run; only the measured seasons exist.
- The MLB 2024 commit `1d54fbf` records rows, seconds and size only, not failed jobs, quarantine or drift.

## Needs the owner (BACKLOG section H)

1. `boxfile.txt`, or retrosheet.org reachable from a machine you can use (B-14, B-18).
2. The permanent lake location and backfill ranges (B-09); stages 1-3 can then run.
3. When to push (96 unpushed commits) and whether to tag a release.
4. The `cbwdellr720-lan` host-key mismatch.

## Decided this session

- ADR 40: default User-Agent is pybaseball's. ADR 41: the Retrosheet CSV bundles are not ingested.

## Known bookkeeping gaps (tracked)

- ADR 35 and ADR 36 are cited by finished tasks and absent from `docs/DECISIONS.md` (B-37, B-38).
- `retrosheet-box-accounts`, `column-descriptions-retrosheet-and-leaderboards` and `historical-backfill-plan`
  still wait on external or owner items (B-09, B-10, B-14..B-19).

## Homelab scratch cleanup

Kept on purpose until the MLB work is done: `~/baseballpy-scratch` and `/tmp/bbpy.bundle` on
`cbwdellr720`, and a local `bbpy.bundle` in the session scratchpad. Remove them on request.
