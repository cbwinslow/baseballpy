# Change Proposal: Historical Backfill Plan and Runbook

## Context & Motivation
The sources can each ingest a season, but nothing defines or measures "ingest all of history": which seasons per source, in what order, how long it takes, how much disk it needs, and how it resumes. The owner wants everything ingested; the plan has to be explicit and measured before running tens of hours of downloads.

## Proposed Changes
1. A backfill plan per source with season ranges and measured throughput: Statcast pitches 2008-present (and `pitches_minors` 2021-present), leaderboards (all variants x first season), MLB Stats API (per season, all sports; `ingest_history` once), Retrosheet 1871-present, Lahman and Chadwick (single snapshots), the `/gf` feed (opt-in per season).
2. Measured baselines recorded in the change: MLB 2024 sports 1 and 11 with 3 games = 1,438 requests, 181,816 rows in 439 s; minor-league Statcast week = 35,352 rows in about 45 s; Statcast MLB week about 26,000 rows in about 45 s; Retrosheet season about 110 s with 4 workers; leaderboards 366 files in 140 s. The plan extrapolates and states disk and time per source.
3. A resumable orchestration entry point (`baseballpy backfill --plan plan.yaml [--from-season --to-season --sources ...]`) that depends on `unified-pipeline-and-cli`: runs jobs in the documented order, writes a progress/summary file, tolerates interruption (manifests already provide resume).
4. Disk and rate guardrails: pre-flight free-space check against the estimate, per-host rate limits unchanged, `--max-gb` stop.

## Out of Scope
The `Pipeline`/CLI framework itself (unified-pipeline-and-cli); running the full backfill (a separate, owner-approved manual task recorded in this change's tasks).

## Impact
Docs + an orchestration command after the CLI lands. Recorded as ADR 36.
