# Design: backlog-consolidation

## 1. Evidence (2026-11-11)

- Backlog count by status (script over `docs/agents/BACKLOG.md`): 406 rows; DONE 334 (328 plain, 6 written
  `DONE:`), READY 27, OPEN 16, SUPERSEDED 11, OWNER 5, EXTERNAL 3, LONG 3, blocked-by-another-row 6.
  The `DONE:` and "after ..." forms are the table's own style (details after the status), not defects.
- `openspec/changes/`: 15 active folders, 78 archived. The two drafts `shared-raw-bytes` and
  `batched-chunk-writes` say "Superseded (2026-11-08) by `response-log-segments` (ADR 95) ... archive when that
  closes"; their 11 rows are already SUPERSEDED.
- `docs/agents/`: `HANDOFF_B43.md` says "SUPERSEDED (2026-10-29)"; `HANDOFF_2026-10-30.md` and
  `FINAL_REPORT.md` are dated status reports from 2026-10-29 and 10-30; `GOAL_LAKE_REPAIR.md` (2026-11-11) is
  replaced by the change `compact-one-writer` and the contract's section 15.
- References to the retired files: `docs/agents/BACKLOG.md` row B-43 and `docs/DECISIONS.md` (ADR 44 era text)
  name `HANDOFF_B43.md`; `openspec/changes/compact-one-writer/proposal.md` names `GOAL_LAKE_REPAIR.md`.
- `download-throughput` 2.3 asks for cheaper normalization of per-game payloads and 2.5 for a speed rerun after
  2.2/2.3; ADR 95 removes the repeated parse (a response is parsed once) and the per-game small files, which
  were most of the per-game time (ADR 92, 93).

## 2. Decisions

- Archive, do not delete, and do not merge the drafts' spec deltas (they were never right).
- Deferred is a status, not an archive: the market and FanGraphs/BRef rows keep their cards.
- Git history keeps the retired files; a "retired" note is not needed.
- No new documents (owner directive 2026-11-11).

## 3. Reuse check

No tool applies (housekeeping). `scripts/project_map.py` regenerates the map; the backlog tests keep rows and
tasks in step.

## 4. As built

- Archived unmerged: `shared-raw-bytes`, `batched-chunk-writes` (now `archive/2026-11-11-*-superseded`).
- Superseded: `download-throughput` 2.3 and 2.5 (rows B-337, B-339).
- Deferred: 8 rows of `market-sources` (6) and `fangraphs-and-bref` (2).
- Removed: `HANDOFF_2026-10-30.md`, `HANDOFF_B43.md`, `FINAL_REPORT.md`, `GOAL_LAKE_REPAIR.md`; references fixed
  in `BACKLOG.md` (B-43), `DECISIONS.md` and `compact-one-writer/proposal.md`.
- ADR 102. Gates (2026-11-11): pytest 1626 passed, 6 skipped; ruff check clean; ruff format 754 files
  already formatted; mypy --strict no issues in 180 files; docs generate --check up to date;
  openspec validate --specs 22 passed.
