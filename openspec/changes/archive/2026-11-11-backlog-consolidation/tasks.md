# Tasks: backlog-consolidation

Order: 1.1 -> 1.5. No spec delta: this change moves and marks records only.

- [x] 1.1 Archive `shared-raw-bytes` and `batched-chunk-writes` unmerged into `openspec/changes/archive/`;
  correct the wording of `response-log-segments` task 10.2 (B-391).
  Done when `openspec/changes/` no longer holds them and the backlog tests pass.
- [x] 1.2 `download-throughput` 2.3 and 2.5 are closed as superseded by ADR 95 (rows B-337, B-339 marked SUPERSEDED).
  Done when the tasks are ticked with the reason and the backlog tests pass.
- [x] 1.3 Defer the `market-sources` and `fangraphs-and-bref` rows (status DEFERRED, with the reason) and note it
  in `EXECUTION_ORDER.md`.
  Done when no row of those changes says OPEN.
- [x] 1.4 Remove `HANDOFF_2026-10-30.md`, `HANDOFF_B43.md`, `FINAL_REPORT.md` and `GOAL_LAKE_REPAIR.md`
  from `docs/agents/`; fix the references; regenerate the project map.
  Done when `grep` finds no reference outside the archive and history.
- [x] 1.5 ADR 102, gates (pytest, ruff, format, mypy, docs, openspec validate), archive this change, commit.
  Done when the evidence is in `design.md`.
