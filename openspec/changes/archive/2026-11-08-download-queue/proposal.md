# Proposal: download-queue

## Why
The owner wants data to be downloading all the time, handled automatically, in Python only (no Task Scheduler, cron or systemd, so it works the same on Linux, macOS and Windows). Today a long download is a hand-written shell loop: when a run dies (three season runs ended with exit 139 and one with a MemoryError) nothing restarts it, nothing records what failed, and nothing starts the next round. Plans, resume and the disk checks already exist (`baseballpy backfill`, `baseballpy update`, ADR 82).

## What changes
- `baseballpy run PLAN`: a supervisor that works through the stages of a plan, one child process per stage attempt, so a crash or a memory spike ends only that attempt; a failed stage is retried with exponential backoff and jitter (`tenacity`) and the rest of the plan continues. With `--every 6h` it starts a new round after the interval and never exits until stopped; without it, it exits when the plan is done.
- A state file (`<home>/state/queue.json`) records the round, each stage's status, attempts and last error, so a restarted supervisor resumes the unfinished round and `baseballpy status` can show it.
- One supervisor at a time (an OS file lock, same mechanism as the host lock) and a clean stop on Ctrl-C or SIGTERM.
- `baseballpy backfill --stage NAME_OR_NUMBER` (repeatable) runs chosen stages of a plan; the supervisor uses it.

## Not changed
Plans, adapters, the host lock and the per-host rate limits. The queue adds no concurrency: the per-host caps still apply, and the host lock still allows one downloader per host.

## Impact
Spec: `cli-and-ingest` (new requirements). ADR 90. Code: `ingest/queue.py`, `cli_queue.py`, `ingest/backfill.py` (`select_stages`), `cli_backfill.py` (`--stage`), `core/hostlock.py` (generic named lock), `core/config.py` (`state_root`). Tests: `tests/test_queue.py`.
