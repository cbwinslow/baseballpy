# Tasks: compact-one-writer

Order: 1.1 -> 1.2 -> 1.3 -> 1.4. Tasks 2.x record the data repair that found the defect (already
done or in progress by hand; they map the work and keep its evidence).

- [x] 1.1 Tests first: `tests/test_compact_lock.py` (second process refused and nothing changed;
  free after the holder ends or crashes; other datasets not blocked; dry run allowed; lock free after a
  normal run; CLI skips a busy dataset and exits 1). They fail before the change.
  Done when the tests fail for the missing lock.
- [x] 1.2 `core/hostlock.py`: `release_named`; `core/compact.py`: claim and release in
  `compact_dataset`; `cli_compact.py`: skip and report a busy dataset.
  Done when 1.1 passes and `tests/test_compact.py`, `tests/test_hostlock.py` still pass.
- [x] 1.3 Docs and records: ADR 99, `lake-access` requirement, `compact` docstring and
  `docs/DATA_WORKFLOW.md`, evidence in `design.md`.
  Done when `docs generate --check` and `openspec validate --specs` pass.
- [x] 1.4 Gates and live check: pytest, ruff check, ruff format --check, mypy --strict; a real
  `baseballpy compact --dataset game_boxscore_officials` while a second one is refused.
  Done when output is pasted in `design.md` and the change is archived.
- [x] 2.1 Repair `mlb_api.game_boxscore_players` season 2019 (rows rebuilt from the saved raw; 225,837
  rows, 2,965 games, 0 duplicates on the registered key). Done: evidence in `design.md` section 6.
- [ ] 2.2 Repair the three season-2023 orphans (`team_roster_all_time`, `team_roster_coach`,
  `award_recipients`). Done when `catalog layout --source mlb_api` shows no ORPHAN_COMPACT.
- [ ] 2.3 Compact the eight mixed-shape MLB game tables one at a time with row-count checks.
  Done when `catalog layout --source mlb_api` shows no MIXED_SCHEMA.
- [ ] 2.4 The 2011 stage: probe the HTTP 500 games and record them as empty with evidence.
  Done when the queue plan no longer retries them.
