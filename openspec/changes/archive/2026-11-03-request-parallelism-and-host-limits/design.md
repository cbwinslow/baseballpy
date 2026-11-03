# Design: request-parallelism-and-host-limits

## Baseline (before)
- Audit-log analysis of the 2024 MLB season run of 2026-11-02 (started before the concurrency
  commits of that day): 12,216 network requests, 3,234 s, 3.78 requests/s, 0.97 average in
  flight, mean latency 0.26 s. Each fan-out endpoint ran at about 0.95 in flight.
- Fixed-subset benchmark of the code at commit `348471a` (teams_season, team_roster_active,
  team_coaches, team_personnel, team_roster_40_man, MLB 2024, scratch lake): numbers below under
  "Evidence".
- `baseballpy probe`: one day of Savant pitches took 9.9 s; MLB API calls 0.1-0.3 s. With 4 in
  flight Savant is limited to about 0.4 requests/s (allowed 2.5); MLB is limited by its 8 req/s
  bucket, not by in-flight slots (4 / 0.26 s = 15 req/s).

## Decisions
- **Per-host in-flight limit.** `HttpClient._semaphore_for(host)`: `host_concurrency.get(host,
  max_concurrency)`. Created lazily on the client's own loop and reset with the loop. The
  connection pool size is derived from the largest limit (`max(20, 4 x largest)`).
- **Request-level pool for MLB.** One helper maps a request list through a pool of
  `max_concurrency` workers; the token bucket and the per-host semaphore stay the only gates, so
  the pool cannot exceed the host limit (AGENTS.md section 4: no unbounded fan-out).
- **Fail-fast kept.** Without `keep_going` the first failure sets a stop flag, queued requests
  are skipped and the first error is raised.
- **404 counter.** `missing` is thread-local by design; each worker returns its count and the
  caller sums them.
- **No new CLI flag.** The network limit stays `BASEBALLPY_RATE_MAX_CONCURRENCY` (and
  `BASEBALLPY_RATE_HOST_CONCURRENCY`); the CLI prints what applies.
- **Reuse check (TOOLING.md):** httpx/aiolimiter/asyncio already provide limiter and semaphore;
  `concurrent.futures` provides the pool. Nothing custom beyond the per-host dict.

## Evidence (2026-11-03)
- **Race found while benchmarking.** `ingest mlb_api -s 2024 -d teams_season -d team_roster_active ...` ran the four team endpoints at the same time as `teams_season`: each reported `completed, 0 rows` in 0.9 s because no teams were stored yet. The default of 4 parallel jobs (commit `3b92c10`) made a mis-ordered `--datasets` list lose data silently. Fixed by `Job.needs` (see ADR 57 and the `cli-and-ingest` requirement "Job Prerequisites").
- **MLB, code of `348471a` vs this change**, 30 teams of sport 1, MLB 2024, same machine and lake: four team endpoints in parallel (old code) 120 requests in 15 s, 7.9 requests/s, 3.7 in flight; one endpoint alone, 30 requests: old 4.31 s, new 3.87 s. Both sit on the 8 requests/s token bucket because the provider answered in 0.14-0.47 s; the in-endpoint pool matters when latency x rate exceeds one (the 2026-11-02 season run: 0.26 s, 0.97 in flight, 3.78 requests/s) or when one large endpoint is left running alone. The overlap itself is proved by `test_one_endpoints_requests_overlap_within_the_bound` (fails with the pool forced to 1).
- **Savant in-flight limit, live, 40-day ranges of 2024 (8 five-day windows each), cold cache:** limit 4: 154,054 rows in 92.8 s and 158,068 rows in 120.6 s (1.7 and 1.3 k rows/s); limit 8: 142,827 rows in 53.9 s (2.6 k rows/s). A first run (4: 92.8 s, then 8: 7.4 s on the same range) was discarded: re-running limit 4 on the same range took 8.0 s, so the second run measured Savant's server cache. No error or retry was seen at 8. Decision: Savant default 8, other hosts 4 (set `BASEBALLPY_RATE_SAVANT_CONCURRENCY=4` to go back).
- **Tests:** `tests/test_request_parallelism.py` (14), `tests/test_cli_ingest.py::test_the_cli_states_the_workers_and_the_real_network_limit`; two key tests were shown to fail without their fix (pool forced to 1 worker; one shared semaphore for all hosts).
- **Not verified:** a whole MLB season run with the new code (the request-level gain is proved by test and by the small runs above, not by a 50-minute run); Savant at limits above 8; the per-host limit for GitHub.
