# Proposal: consolidate the backlog and the agent files

## Why

The owner asked (2026-11-11) to get organised: archive what is outdated and no longer relevant, and use
what exists instead of writing new documents. Measured today: `docs/agents/BACKLOG.md` has 406 rows (328
done, 27 ready, 16 open, 11 superseded, 5 waiting on the owner, 3 external, 3 long runs), 15 active
change folders and 78 archived ones, and four dated agent files that describe a state that no longer exists.

## What

1. **Archive the two superseded drafts** `shared-raw-bytes` and `batched-chunk-writes` unmerged (their
   proposals say "archive when `response-log-segments` closes"; the replacement is decided and its rows
   are in the backlog, so keeping them active only adds noise). Their evidence stays in the archive.
2. **Mark two throughput tasks superseded** (`download-throughput` 2.3 cheaper normalization, 2.5 rerun
   speed): ADR 95 (parse once, store once) replaces them.
3. **Defer the market and FanGraphs/Baseball-Reference rows** (`market-sources` 1.2, 2.4, 2.5, 3.1, 3.2, 4.1
   and `fangraphs-and-bref` 2.2, 3.2): not the MLB core; status DEFERRED, nothing deleted, nothing
   archived, so they can resume later.
4. **Retire four stale agent files** from `docs/agents/` (`HANDOFF_2026-10-30.md`, `HANDOFF_B43.md`,
   `FINAL_REPORT.md`, `GOAL_LAKE_REPAIR.md`); they stay in git history. Fix the two references to them.
5. ADR 102 records the decisions; no new document is added.

## Out of scope

No code, no data, no schema. No row is deleted. Tasks that wait for the owner or an external host
(`OWNER`, `EXTERNAL`) and the `response-log-segments` tasks stay as they are. No spec delta (no behaviour
changes).
