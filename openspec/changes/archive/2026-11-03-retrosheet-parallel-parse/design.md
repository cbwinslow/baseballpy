# Design: retrosheet-parallel-parse

## Baseline (before)
One 2022 season, default settings (in-process parsing, steps in sequence): 236.5 s, 628,348
rows. Steps: download 25 s, events 102.7 s, events_postseason 1.7 s, boxscores 32.7 s,
box_accounts 2.6 s, daily_splits 69.0 s, substitutions 19.1 s, the rest under 1 s.

## Measured scaling (same season, a fresh lake each time)
| parse workers | season job | note |
|---|---|---|
| 0 (in process) | 236.5 s | baseline |
| 16 | 70.7 s | events 15.6 s, daily splits 12.4 s, boxscores 9.7 s; steps still in sequence |
| 32 | 87.1 s | slower: a new pool of 32 processes is started for every step |
All 15 stored tables are identical (`pyarrow Table.equals`) to the single-core run for 16 and 32.

## Decisions
- Cap 32: the measured best (48 no better); peak extra memory 6.5 GB for five seasons at 32
  workers; the setting stays, so a machine can choose otherwise.
- Persistent shared pool: a module-level executor started on first use and shut down at exit;
  the pool is recreated when the worker count changes. Bounded in-flight window per stream.
- Ordering: results are yielded in input order, so stored row order is unchanged.

## Evidence (2026-11-03, 56 logical CPUs, 96 GB RAM)
- **Shared persistent pool, one 2022 season, fresh lake each time:** 8 workers 49.2 s; 16 workers 37.4 s; 32 workers 35.6 s (baseline in-process 236.5 s; per-step pools at 16: 70.7 s, at 32: 87.1 s). Steps at the default: events 15.1 s (includes starting the pool), boxscores 2.9 s, box accounts 2.6 s, daily splits 5.5 s.
- **Five seasons (2018-2022) together, fresh lake:** 16 workers 117 s; 32 workers 98 s; 48 workers 103 s (the same five seasons one after another in process would take about 1,185 s).
- **Memory:** peak extra use 6.5 GB (free memory 61.4 GB to 54.9 GB) for the five-season run at 32 workers.
- **Identical data:** all 22 datasets with data of the 2022 season stored with the default pool and with the five-season run equal (`Table.equals`, same row order) the single-process run; the earlier 16- and 32-worker runs of all 15 then-built tables were equal as well.
- **Tests:** `tests/test_retrosheet_pool.py` (4): the default follows the CPU count with a cap and an explicit value, even 0, wins; pooled equals in-process in order and reuses one pool; a stream never runs more than 2 x workers ahead; a failing file raises and the queued files are never submitted. The existing pooled-versus-serial test asks for `parse_workers=0` explicitly; the test fixtures pin in-process parsing unless a test asks for a pool.
- **Task 1.3 not built:** running the build steps of one season at the same time could save about 10 s of 37 s for a single-season run, but when several seasons run (the runner already runs jobs in parallel) the shared pool is already full, and the steps share state in the source object. Not needed for the measured goal; revisit only if single-season latency matters.
- **Not verified:** a 12-season run, behaviour on a machine with few cores (the default follows the CPU count), the effect on machines with less memory.
