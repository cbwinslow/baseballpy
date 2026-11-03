# Proposal: request-parallelism-and-host-limits

## Problem (measured 2026-11-03 from `logs/audit.jsonl` and live probes)
1. **One request at a time inside an MLB endpoint.** `MlbEndpointExtractor.ingest` loops over an
   endpoint's requests (850 team requests, thousands of game or player requests) one by one.
   Parallelism exists only across endpoints. The 2024 season run (12,216 network requests,
   3,234 s) averaged 0.97 requests in flight and 3.8 requests per second against an allowed 8.
2. **One global in-flight limit for every host.** `HttpClient` has a single semaphore (default
   4) shared by Savant, the MLB API and GitHub. A slow Savant download (one day of pitches took
   9.9 s in `baseballpy probe`) holds slots that fast hosts need, and `ingest -c N` does not
   change it, so `-c auto` (up to 32 workers) cannot make the network faster.
3. **The CLI is silent about the real limit,** and the specs and `AGENTS.md` call the limit
   "global" while the intent (bounded fan-out per target host) is per host.

## Solution
1. `HttpClient` keeps one in-flight limit **per host** (`RateLimitConfig.max_concurrency` is the
   default for each host; `host_concurrency` overrides single hosts). The token bucket per host
   is unchanged.
2. The MLB request loops (`ingest`, `_ingest_raw_only`) run their requests on a bounded pool
   (size `max_concurrency`, never more than the per-host limit can use), keep fail-fast when
   `keep_going` is false, and aggregate the thread-local 404 counter.
3. `baseballpy ingest` prints the worker count and the network limit that applies, so the number
   the owner sees is the number that matters.
4. Statcast: measure Savant's in-flight limit live (4 vs more) and record the evidence; change a
   default only with that evidence.
5. Specs, `AGENTS.md` section 4, ADR 57 and docs say "per host".

## Scope
`src/baseballpy/core/{http,config}.py`, `src/baseballpy/sources/mlb_api/generic.py`,
`src/baseballpy/cli_ingest.py`, tests (`test_concurrency.py`, new `test_request_parallelism.py`),
specs `concurrency-and-rate-limiting`, `mlb-api-ingestion`, `cli-and-ingest`, `AGENTS.md`,
`docs/QUICKSTART.md`, `docs/CLI.md` (generated), ADR 57.
