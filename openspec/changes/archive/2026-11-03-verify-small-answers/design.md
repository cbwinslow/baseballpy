# Design: verify-small-answers

## Decisions
- **Where:** the one place a single non-paginated request is made (`_get_paginated`'s plain
  branch); `ingest` passes `verify` when the endpoint's whole call has at most
  `verify_max_requests` requests. No endpoint names are involved.
- **Largest wins.** Differing valid answers: keep the largest body (ties: the latest). A partial
  answer is a subset of the full one; a legitimate update between two fetches changes the size
  by little and in the same direction as newer data, so the rule never prefers the partial one.
- **Cost bound.** Only answers below `verify_max_bytes` are re-fetched, only for calls with at
  most `verify_max_requests` requests: standings, reference lists, small lookups. Measured
  below.
- **Not done here:** per-team fan-outs, paginated pools and the hydrate fallback are not
  verified (a repeat would multiply their cost); Statcast and the git sources have their own
  fingerprint checks (ADR 43).
- **Reuse check (TOOLING.md):** nothing in httpx, tenacity or aiolimiter compares two answers;
  `collections.Counter`-free comparison of two byte strings is the whole mechanism.

## Evidence (2026-11-03)
- **Cost, from the audit log of the full 2024 season at 10 requests/s:** 133 endpoints, 12,309 network requests; 53 endpoints make at most 5 requests each, 86 requests in all, so verification adds at most 86 requests = 0.7 percent of a season (an upper bound: an answer above 1,000,000 bytes is not repeated).
- **Live:** `standings_by_organization` for 2024 against the real API, forced refresh: 1 request in the call, 2 HTTP calls, both 570,237 bytes (identical), 200 rows, no warning. (The provider's data moves during the day: 201 rows earlier today, 200 now; the bytes of the two calls agree.)
- **Tests:** `tests/test_verify_small_answers.py` (4): partial then full answers keep all 11 rows after 3 requests with the warning; identical answers cost exactly 2 requests; big, many (limit 2 against 3 requests: 3 calls; limit 3: 6 calls), disabled and non-200 answers are not repeated; three different bodies keep the largest. With the verify flag forced off all 4 fail; restored, all 4 pass.
- **Not verified:** that the provider's partial answer is reproducible (it happened once in two full runs and never in 5 plus 2 later fetches), so the live proof of the "partial replaced by full" path is the mocked test, not a real partial answer. Per-team fan-outs, paginated pools and the hydrate fallback are not covered (a repeat would multiply their cost).
