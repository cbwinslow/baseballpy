# Design: download-queue

## Reuse check (docs/agents/TOOLING.md)
- Plans, stages, resume, disk checks: `ingest/backfill.py` (used, extended with `select_stages`).
- Retry with backoff and jitter: `tenacity` (`Retrying`, `wait_exponential_jitter`, a `sleep` that listens to the stop event). Nothing is hand-written.
- Process supervision: stdlib `subprocess`. Evidence: no designated tool covers supervising a child process; `dlt` and `click` do not. A scheduler library (APScheduler, Prefect, Airflow) would add a heavy dependency for "run this again in six hours".
- State file: `msgspec` (ADR 88) written with `atomic_write`.
- Single instance: the OS file lock of `core/hostlock.py` generalised to a named lock.

## Decisions
- D1 One child process per stage attempt. A crash (exit 139) or `MemoryError` ends that attempt only; memory is returned to the OS between stages.
- D2 Exit codes of `backfill` decide what happens: 0 done; 1 failed jobs, retry; 2 stopped by `--max-gb` or low disk, do not retry (a retry would stop the same way), the queue stops and says why; 130 interrupted, the queue stops.
- D3 A failed stage never blocks the next one. After its retries it is marked failed, and the next round tries it again.
- D4 `--every` is measured from the start of a round. A round that takes longer than the interval starts the next one at once.
- D5 The supervisor runs the child with `sys.executable -c "from baseballpy.cli import main; main()"`, so it needs no console script on `PATH` and works the same on every OS.
- D6 Stop: Ctrl-C or SIGTERM sets a stop event; the supervisor terminates the child (`terminate`, then `kill` after 30 seconds) and records the stage as interrupted. Everything is resumable, so nothing is lost.
- D7 Restart: if the state file shows an unfinished round of the same plan, the supervisor continues it and skips stages already done.

## Web check
APScheduler and Celery-style schedulers solve distributed or cron-like jobs; Prefect and Dagster need a server. For one machine, one plan and "retry and repeat", a small supervisor around the existing resumable plan is what `pybaseball`-style projects do by hand and is enough.

## Evidence
Filled in as built.
