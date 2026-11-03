## MODIFIED Requirements

### Requirement: Single Shared HTTP Client
Every network fetch MUST go through `baseballpy.core.http.HttpClient`, applying a per-host token bucket, a per-host bounded in-flight limit, HTTP/2 pooling and jittered exponential retry. A slow host MUST NOT consume the in-flight slots of another host.

#### Scenario: Sync and async callers share limits
- **GIVEN** sync and async callers hitting `statsapi.mlb.com` concurrently at a configured 8 req/s
- **THEN** they share one limiter: after an initial burst of up to 8 requests (the bucket holds one second), the requests of all callers together are paced at 8 per second, and no more than `max_concurrency` are in flight at once.
- Verified by `tests/test_concurrency.py::test_sync_threads_and_async_callers_share_one_host_limiter` and `::test_concurrency_bound_holds_across_sync_and_async_callers`.

#### Scenario: A slow host does not block a fast one
- **GIVEN** `slow.example.com` holds every one of its `max_concurrency` slots for a long time
- **WHEN** a request is made to `fast.example.com`
- **THEN** it completes without waiting for the slow host, and each host is still bounded by its own limit.
- Verified by `tests/test_request_parallelism.py::test_a_slow_host_does_not_block_a_fast_one` and `::test_per_host_limits_are_bounded_separately`.

#### Scenario: Retry policy
- **WHEN** the server returns 429 with `Retry-After: 2`
- **THEN** the client waits at least 2 seconds and retries up to `max_retries`
- **AND** a 404 is never retried.
- Verified by `tests/test_hardening.py::test_http_retries_429_with_retry_after_then_succeeds and ::test_http_does_not_retry_404 and ::test_http_gives_up_after_max_retries`.

#### Scenario: Conditional request
- **GIVEN** a stored ETag and a 304 response
- **THEN** `HttpResult.not_modified` is true and no body is parsed.
- Verified by `tests/test_hardening.py::test_http_conditional_304`.

## ADDED Requirements

### Requirement: Host In-Flight Limit Is Configurable
`RateLimitConfig.max_concurrency` (default 4) MUST be the in-flight limit of every host except Baseball Savant, whose default is `savant_concurrency` (8: its pitch CSVs take seconds each, so 4 in flight cannot reach the 2.5 requests/second rate; measured in the change's design.md). `host_concurrency` (host to limit) MUST override both for single hosts. Raising a limit MUST NOT raise the host's token-bucket rate.

#### Scenario: A host override applies to that host only
- **GIVEN** `max_concurrency=2` and `host_concurrency={"a.example.com": 5}`
- **WHEN** many requests go to `a.example.com` and `b.example.com`
- **THEN** the peak in flight is at most 5 for a and at most 2 for b.
- Verified by `tests/test_request_parallelism.py::test_per_host_limits_are_bounded_separately`.

#### Scenario: Savant has its own default
- **WHEN** a client is built with the default configuration
- **THEN** its in-flight limit is 8 for `baseballsavant.mlb.com` and 4 for `statsapi.mlb.com` and `raw.githubusercontent.com`, `savant_concurrency` changes the Savant default and a `host_concurrency` entry wins over it.
- Verified by `tests/test_request_parallelism.py::test_savant_has_a_higher_default_in_flight_limit_than_other_hosts`.
