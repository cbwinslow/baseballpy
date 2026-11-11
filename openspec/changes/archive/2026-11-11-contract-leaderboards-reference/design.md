# Design: contract-leaderboards-reference

## 1. Evidence (2026-11-11)

- `StatcastLeaderboardExtractor.ingest_all(years=[2024])` over `SUPPORTED` with the recorded pages in
  `tests/fixtures/savant` and `RetrosheetSource.ingest_reference()` after `ingest_season` leave a lake that
  satisfies `assert_lake_contract` before and after compaction.
- Reuse: `tests/lake_contract.py`, the existing leaderboard fixtures and the Retrosheet `full_season` repo.

## 2. As built

Tests only: `test_every_statcast_leaderboard_download_has_the_lake_shape` and the reference ingest added to
`test_a_fresh_retrosheet_download_has_the_lake_shape`. Gates: see the commit.

## 3. Gate evidence (2026-11-11)

pytest 1640 passed, 6 skipped (one run also counted a stale project map caused by a draft change added while the
run was in progress; regenerated); ruff check and format clean; mypy --strict no issues in 180 files; docs generate
--check up to date; openspec validate --specs 22 passed.
