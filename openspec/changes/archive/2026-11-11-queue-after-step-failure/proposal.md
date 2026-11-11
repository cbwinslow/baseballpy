# Proposal: a stage whose after-step failed is not done

## Why

`baseballpy run` marks a stage `done` when its download child exits 0. The after-step (compaction of the
finished stage, `child_compact_runner`) runs later in the background; if it fails, `_Background.settle`
only writes `after-stage step exited with N` into `last_error`. The stage stays `done`, the compaction is
never retried inside the round, `report.failed` stays empty and the exit code is 0. The real queue state
(2026-11-11) shows MLB 2018 to 2021 as `done` with `after-stage step exited with 1` (and 4294967295 for
2020); one of them (2019) ended with damaged compacted files nobody noticed for days. AGENTS.md section 15
rule 6 says a failed job is never reported as done.

## What

- A failed after-step sets the stage to `failed` (with the error text), so the existing retry machinery
  runs it again: the next pass of the same round (after `failed_wait`) or the next round.
- `run_queue` settles the last after-step before it computes the round's failures, so `report.failed`,
  the exit code and `baseballpy status` show it.
- The test that asserted the old behaviour changes with the rule; one requirement and scenario in
  `cli-and-ingest`; one ADR.

## Out of scope

Why the compaction failed (exit 1, 4294967295): the compaction lock (ADR 99) removed one cause; others are
read from the queue log when they happen. Making compaction unnecessary is `response-log-segments`.
