# Design: compact-one-writer

## 1. Evidence (2026-11-11)

- `catalog layout --source mlb_api --json`: 9 ORPHAN_COMPACT findings on `game_boxscore_players`
  `season=2019/compact-0007..0015` ("lacks 211 chunk(s) its records point at"), 3 more of one chunk in
  2023 (`team_roster_all_time`, `team_roster_coach`, `award_recipients`).
- Footer check (`scratchpad/meta.py`): the rows of file 0010 (15,447) equal what the records say file
  0013 holds, 0013 equals 0016, 0014 equals 0017, 0015 equals 0018: the files hold chunk groups shifted
  by three numbers, and the three groups the records call 0007, 0008, 0009 (15,861 + 15,335 + 15,293
  rows) exist in no file. Two compactions chose the same numbers.
- File times: `compact-0013` 1794131473 and `compact-0016` 1794131520, `compact-0014`/`0017` and
  `0015`/`0018` the same way: both ranges were written in one window.
- Code: `core/compact.py` `_compact_group` (`next_index` from the folder) and `_cleanup` (deletes
  compact files no record points at).

## 2. Prior art and the reuse check (TOOLING.md)

- Designated tool: none for file locks. The project already has `core/hostlock.py` (an OS file lock,
  released when the process ends, even by a crash; ADR 77 neighbours, segment writers use it as
  `segments-<source>-<season>`). Reusing it adds no dependency. `fasteners`/`filelock` are only
  indirect dependencies and would need a change, an ADR and a TOOLING row.
- Web search: not needed for this slice; the pattern (advisory OS lock per writer target) is what
  `hostlock` already implements and what `segments.claim_season` uses.

## 3. Decision

- Lock name `compact-<source>-<dataset>` (the registry key, never a literal dataset list), folder
  `LakeConfig.locks_root`.
- `compact_dataset(..., dry_run=False)` claims it first and releases it in `finally`, so a long
  process (a test, a notebook) does not keep it. A dry run takes no lock.
- The claim is per process: two threads of one process compacting the same dataset are not
  stopped. The CLI maps one thread to one dataset, so this cannot happen there.
- Busy dataset: `HostBusyError` from `compact_dataset`; the CLI catches it per dataset, prints
  "skipped, busy" and exits 1 after the rest.
- Rejected: exclusive-create file names (does not stop `_cleanup` deleting a live run's new file, and
  the manifest save would still be last-writer-wins); a per-season lock (the manifest is per dataset);
  documentation only (the queue starts compactions on its own).

## 4. Tests

`tests/test_compact_lock.py`: a second process holding the lock makes `compact_dataset` raise
`HostBusyError` and leave every file and record unchanged; the same dataset compacts after the
holder ends (also by a crash); another dataset is not blocked; a dry run works while the lock is held;
the lock is free again after a normal run; the CLI skips a busy dataset and exits 1.

## 5. As built

- `core/hostlock.py`: `release_named(directory, name)` (new, small).
- `core/compact.py`: `compact_dataset` claims `compact-<source>-<dataset>` (not for a dry run) and
  releases it in `finally`; the old body moved to `_compact_dataset_locked`. A dataset with no
  processed folder returns before the lock.
- `cli_compact.py`: a busy dataset is skipped, listed ("skipped, busy"), and the command exits 1 after
  the others finish.
- Tests: `tests/test_compact_lock.py` (5 tests, written first and failing before the change).
- Deviation from section 3: none.

Live check (2026-11-11, real lake): a helper process held `compact-mlb_api-game_boxscore_officials`;
`baseballpy compact --source mlb_api --dataset game_boxscore_officials --jobs 1` printed
"skipped, busy (another process is compacting it): mlb_api.game_boxscore_officials", merged 0 chunks,
"Error: 1 dataset(s) were busy and skipped", exit 1 after 4.7 s, and changed no file.

## 6. The repair that found the defect (tasks 2.x)

Done by hand on 2026-11-11 before this change existed (a process slip: the work was started without the
change and board claim; it is recorded here, and the rule is now followed):

1. Backup of `processed/mlb_api/game_boxscore_players/season=2019` (64 MB) and the record file.
2. `compact-0007..0015.parquet` renamed to `*.bad` (not deleted).
3. `baseballpy ingest mlb_api -s 2019 -d games` refilled the chunks whose files were gone (about 50
   minutes; it may have used the network, not only the saved raw).
4. Check (`scratchpad/ver.py`): 225,837 rows = the records' `records_count` sum, 2,965 distinct games,
   0 duplicates on the registered key (`game_pk`, `teams_key`, `person_id`).
5. A real `compact` of the table followed (one job); its result is recorded when it ends.

Open: 2.2 (2023 orphans), 2.3 (eight tables), 2.4 (2011 games), and deleting the `*.bad` files and
the backup once the owner agrees.

## 7. Gate evidence (2026-11-11)

- `uv run pytest -q`: 1624 passed, 6 skipped after the backlog format fix (the first full run had one
  backlog-format failure in `tests/test_agent_runbooks.py`, fixed: done tasks carry no backticks).
- `uvx ruff check .`: All checks passed; `uvx ruff format --check .`: 747 files already formatted;
  `uv run mypy --strict src`: no issues in 180 source files; `docs generate --check`: up to date;
  `openspec validate --specs`: 22 passed, 0 failed.
- The change stays in `openspec/changes/` (not archived) until the repair tasks 2.2 to 2.4 are done.
