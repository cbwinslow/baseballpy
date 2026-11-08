# Proposal: download-throughput

## Why
The owner wants every download to run as fast as it can, checked at intervals, with adjustments made when it does not. The first overnight measurement (2026-11-08) shows the per-game MLB download at about 3 requests per second against a rate limit of 10, so it runs at about 30% of what the host allows.

## What was measured (evidence, 2026-11-08)
- The host is not the limit. A probe of 60 boxscore requests through the project's own client, with the download running at the same time, ran at 11.3 requests per second with 4 requests in flight and 11.5 with 12. The rate-limit bucket (10 per second), not the server, ended the probe.
- In-flight allowance is not the limit. The download with 4 in flight: 2.9 req/s, answers in 1.2 s. With 12 in flight: 2.9 req/s, answers in 3.95 s. More requests in flight only made each one wait longer, the same finding as ADR 59. The default of 4 stays.
- The limit is the program's own work between requests. One stored game-sized chunk takes about 96 ms on its own (profile of `ProcessedStore.put` on a 611-column boxscore table: 55 ms in `pyarrow.parquet.write_table`, 14 ms in the manifest save, about 10 ms in file open and `fsync`); there are 13 chunks per game. Writing 50 games in one `write_table` call took 133 ms, about 2.7 ms per game, so batching is worth about 20 times on the wide tables. `fsync` is not the cost (no difference with it switched off).
- The machine has 56 logical CPUs and the download uses 1.6 of them.

## What changes
- `baseballpy speed` and a speed watch in `baseballpy run` (`--speed-every`, default 10 minutes): measure requests per second against the cap, the answer time and the in-flight use from the audit log, and name the limit (the rate limit, the host pushing back, idle capacity so the wait is local, or a slow host). Measure and advise only: no knob is changed automatically, because the measurement above shows the knob that exists (in-flight) does not help.
- Tasks to remove the real limit: batched chunk writes, cheaper normalization of the live feed, and (an owner decision) worker processes that share the host's rate limit.

## Impact
Spec: `cli-and-ingest`. ADR 92. Code: `ingest/speed.py`, `cli_speed.py`, `cli_queue.py`. Tests: `tests/test_speed.py`.
