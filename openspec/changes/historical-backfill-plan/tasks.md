# Tasks: Historical Backfill

- [ ] 1. Plan and estimates <!-- id: 1 -->
  - [ ] 1.1 Measure throughput per source on one old and one modern season (scratch home); record rows, bytes, seconds
  - [ ] 1.2 Write the plan (`docs/BACKFILL.md`) with order, ranges, disk and time estimates, owner decision points
- [ ] 2. Orchestration (after `unified-pipeline-and-cli`) <!-- id: 2 -->
  - [ ] 2.1 `baseballpy backfill` with plan file, progress summary, `--max-gb`, free-space pre-flight
  - [ ] 2.2 Interruption/resume test with respx
- [ ] 3. Execution (manual, owner-approved) <!-- id: 3 -->
  - [ ] 3.1 Run the backfill into the real home; record the summary in `docs/BACKFILL.md`
  - [ ] 3.2 Run `catalog audit` and `catalog status`; fix MISSING findings
