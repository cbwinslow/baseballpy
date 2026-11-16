# Proposal: easy-downloads

## Why
- The owner wants a user to import the library, run a few commands and get all the data they need where they need it,
  with as much of the work as possible done by the library, and nothing left in scratch scripts.
- An audit on 2026-11-16 found that the library already has plans (`backfill`, `run`, `update`, built-in `daily` and
  `full`, disk guards, resume, retries), but: (1) a plan stage cannot carry source options, so "all levels of MLB games"
  (`--option sports=all`) could only be run by hand or in a script; (2) there is no Python function for downloading:
  everything is a command line; (3) plans run seasons oldest first although recent seasons matter most.

## What changes
1. Plan stages accept `options` (the same `name = value` pairs as `ingest --option`), and plan stages run seasons newest
   first. Built-in plan `minors`: MLB games at every level from 2021 on (and `minors-all` from 2008).
2. A Python interface in the top-level package: `baseballpy.download(source, seasons, datasets, **options)`,
   `baseballpy.update()` and `baseballpy.backfill(plan)`, which plan, run, check the disk, sync the DuckDB views and return
   a report; the same code the commands use.
3. The docs say the few commands (and the Python lines) a user runs; the scratch scripts of the session are replaced by
   these.

## Not in this change
- New sources or datasets; a graphical interface; scheduling outside `baseballpy run --every`.

## Impact
- Spec: `cli-and-ingest`. ADR 144. Code: `ingest/backfill.py`, `ingest/plans/`, `baseballpy/easy.py`, `__init__.py`.
- Rollback: additive; plans without `options` and the commands behave as before (only the season order changes).
