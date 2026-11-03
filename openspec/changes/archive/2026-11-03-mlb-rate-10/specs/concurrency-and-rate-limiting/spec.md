## MODIFIED Requirements

### Requirement: Host-Specific Token Bucket Rate Limiting
The system MUST route all HTTP requests through host-specific token bucket limiters to prevent IP blocks and 429 errors.
- Default limits:
  - `baseballsavant.mlb.com`: 2.5 requests/second
  - `statsapi.mlb.com`: 10.0 requests/second
  - `raw.githubusercontent.com`: 15.0 requests/second

#### Scenario: Default host rates
- **WHEN** a `RateLimitConfig` is built with no overrides
- **THEN** its per-host rates are 2.5, 10.0 and 15.0 requests/second for Savant, the MLB Stats API and GitHub, and `statsapi_rps` overrides the MLB one.
- Verified by `tests/test_request_parallelism.py::test_default_host_rates_are_the_documented_ones`.

#### Scenario: High-volume concurrent season query
- **GIVEN** a request to fetch 30 weeks of Statcast pitch data
- **WHEN** scheduled across async worker tasks
- **THEN** requests are rate-limited to 2.5 requests/sec and bounded by the host's in-flight limit (an `asyncio.Semaphore`, 8 for Savant by default, 4 for other hosts).
- Verified by `tests/test_hardening.py::test_http_rate_limit_spaces_requests and ::test_http_semaphore_bounds_concurrency` and `tests/test_concurrency.py::test_concurrency_bound_holds_across_sync_and_async_callers`.
