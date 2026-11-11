# Proposal: one compaction at a time per dataset

## Why

On 2026-11-08 two compactions of `mlb_api.game_boxscore_players` season 2019 ran at the same time
(the file times of `compact-0007..0015` and `compact-0016..0018` overlap). `compact_dataset` picks
the next file number by looking at the folder (`core/compact.py`, `next_index = max(indices) + 1`),
so both runs chose the same numbers and the later write replaced the earlier file. The download
records then pointed at files that held other games: about 46,000 rows (roughly 630 games) were
missing and about 43,000 were stored twice. Queries on that table were wrong, and the queue still
said "done". `_cleanup` makes it worse: it deletes every `compact-*` file the records do not yet
point at, which is exactly what a second run's brand-new file looks like.

The module docstring already says "run it when no ingest is running", but nothing enforces it, and
the download queue starts compactions by itself.

## What

- Reuse the operating-system file lock of `core/hostlock.py` (`claim_named`, already used for hosts,
  the queue and the segment writers). `compact_dataset` takes the lock `compact-<source>-<dataset>`
  in `LakeConfig.locks_root` before it touches a file (not for `--dry-run`, which only reads) and
  gives it back when it ends. A second compaction of the same dataset is refused with a clear
  message and changes nothing; other datasets are not blocked.
- Add `release_named` to `core/hostlock.py` (the module only had `release_all`).
- `baseballpy compact` reports a refused dataset as "skipped, busy" and exits non-zero after the
  other datasets are done.
- One requirement in `lake-access`, one ADR, docs.

## Out of scope

- Ingest versus compact in one dataset (separate decision; the docstring rule stays).
- Repairing the damaged data: that is the lake-repair work (the repair tasks 2.1 to 2.4 below), recorded
  as tasks B-401 to B-404 so it is mapped, not as code.
- A detector for "file holds other chunks than the records say": `catalog layout` already reports it
  (ORPHAN_COMPACT "lacks N chunk(s)").
