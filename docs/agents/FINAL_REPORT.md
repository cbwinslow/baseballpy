# Final report of the backlog run (2026-10-28)

Written because `NEXT_GOAL.md` asks for it once nothing is READY. The run stopped here; what is left
needs the owner or an external host.

## Verified (command, result)

- `uv run pytest`: 981 passed, 5 skipped (before the last doc-only commits; after them the targeted
  tests, `ruff check`, `ruff format`, `mypy --strict src` and `tests/test_agent_runbooks.py` were rerun and are clean).
- `baseballpy backfill <plan> --dry-run --max-gb 15` on the plan in `docs/BACKFILL.md`: 96 jobs, 9.7 GB estimated.
- `baseballpy catalog audit`: "No findings." (earlier in the run).
- Homelab throughput probe: `docs/BACKFILL.md` (Lahman, Chadwick, Retrosheet, Statcast).
- All 89 spec scenarios cite a test (`tests/test_spec_scenarios.py`).

## Not verified

- A complete modern MLB API season: the 2024 run failed (HTTP 500, then 403). The MLB row of `docs/BACKFILL.md` is a bound.
- Real regeneration of the MLB schemas with the new key probe (B-03); the all-time pools (B-01).
- The first GitHub run of the audit workflow (B-11).

## Needs the owner (docs/agents/BACKLOG.md section H)

1. `statsapi.mlb.com` answers 403 to our User-Agent since 2026-10-28 21:57 UTC (B-29): wait and retry, or use a plain `baseballpy/<version>` agent.
2. (Rejected by the owner on 2026-10-29: `retrosheet-csv-bundles`, ADR 41.)
3. Supply `boxfile.txt` or retrosheet.org access (B-14, B-18).
4. Permanent lake location and backfill ranges (B-09).
5. When to push (about 55 unpushed commits) and whether to tag a release.
6. The `cbwdellr720-lan` host-key mismatch.

## Homelab scratch cleanup

Kept on purpose so the MLB runs can resume: `~/baseballpy-scratch` and `/tmp/bbpy.bundle` on `cbwdellr720`,
and a local `bbpy.bundle` in the session scratchpad. Remove them when the MLB work is done or on request.

## Commits

`b0de322`, `b072ef1`, `31176bc`, `f44be05`, `7f5d18d`, `60c1f95`, `4ab2609`, `cc97f14`, `84302da`.
