# Tasks: Historical Backfill

- [x] 1. Plan and estimates <!-- id: 1 -->
  - [x] 1.1 Measure throughput per source on one old and one modern season (scratch home); record rows, bytes, seconds <!-- 2026-10-28 done for Lahman, Chadwick, Retrosheet and Statcast; MLB API 2024 did not finish (HTTP 500, then 403, BACKLOG B-29) so it stays open -->
  - [x] 1.2 Write the plan (`docs/BACKFILL.md`) with order, ranges, disk and time estimates, owner decision points <!-- 2026-10-28 MLB API row is a bound only: no modern season finished (1.1) -->
- [x] 2. Orchestration (after `unified-pipeline-and-cli`) <!-- id: 2 -->
  - [x] 2.1 `baseballpy backfill` with plan file, progress summary, `--max-gb`, free-space pre-flight <!-- 2026-10-28 `ingest/backfill.py` (TOML plan, stages become `Selection`s, no source names), `cli_backfill.py`, `tests/test_backfill.py` (16 tests); a plan is not yet written, see 1.2 -->
  - [x] 2.2 Interruption/resume test with respx <!-- 2026-10-28 `test_resume_with_the_real_adapter_fetches_only_what_is_incomplete` (real Lahman adapter, respx, Ctrl-C simulated in the main thread) -->
- [ ] 3. Execution (manual, owner-approved) <!-- id: 3 -->
  - [ ] 3.1 Run the backfill into the real home; record the summary in `docs/BACKFILL.md`
  - [ ] 3.2 Run `catalog audit` and `catalog status`; fix MISSING findings
