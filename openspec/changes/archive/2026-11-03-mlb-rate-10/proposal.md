# Proposal: mlb-rate-10

## Problem
After ADR 57 the full 2024 MLB season ran at exactly the host rate (8 requests/s) from minute 15
to minute 35 of 38: that stretch is bound by the token bucket, not by threads or latency (ADR 58).
`AGENTS.md` section 4 allows 8-10 requests/s for `statsapi.mlb.com`; the code uses the low end.

## Solution
Default `RateLimitConfig.statsapi_rps` to 10.0 (still overridable with
`BASEBALLPY_RATE_STATSAPI_RPS`). Specs, source doc and ADR 59 say 10. Proof: a cold-season test
and a full 2024 season run at 10 with no errors and a measured speed-up; the change is reverted
to 8 if the provider answers 429 or errors appear.

## Scope
`src/baseballpy/core/config.py`, `openspec/specs/{concurrency-and-rate-limiting,mlb-api-ingestion}`,
`docs/sources/mlb_api.md`, `docs/ENDPOINT_CATALOG.md`, ADR 59, `tests/test_request_parallelism.py`.
