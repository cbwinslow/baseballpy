# concurrency-and-rate-limiting Specification

## Purpose
Defines concurrency boundaries, host-specific token-bucket rate limiting, and exponential retry backoff policies for network extractors in `baseballpy`.

## Requirements

### Requirement: Host-Specific Token Bucket Rate Limiting
The system MUST route all HTTP requests through host-specific token bucket limiters to prevent IP blocks and 429 errors.
- Default limits:
  - `baseballsavant.mlb.com`: 2.5 requests/second
  - `statsapi.mlb.com`: 8.0 requests/second
  - `raw.githubusercontent.com`: 15.0 requests/second

#### Scenario: High-volume concurrent season query
- **GIVEN** a request to fetch 30 weeks of Statcast pitch data
- **WHEN** scheduled across async worker tasks
- **THEN** requests are rate-limited to 2.5 requests/sec and bounded by an `asyncio.Semaphore(max_concurrency=4)`.

### Requirement: Jittered Exponential Backoff
The system MUST automatically retry failed requests on HTTP 408, 425, 429, 500, 502, 503, 504 and connect timeout errors using exponential backoff with randomized jitter up to `max_retries` (default 5).

#### Scenario: Transient errors retry up to the limit
- **WHEN** a request fails with a transport error or a retryable status
- **THEN** it is retried, honoring `Retry-After`, and the client gives up after `max_retries`
- Verified by `tests/test_hardening.py::test_http_retries_transport_errors, ::test_http_gives_up_after_max_retries and ::test_http_retries_429_with_retry_after_then_succeeds`.

### Requirement: Single Shared HTTP Client
Every network fetch MUST go through `baseballpy.core.http.HttpClient`, applying a per-host token bucket, a global bounded semaphore, HTTP/2 pooling and jittered exponential retry.

#### Scenario: Sync and async callers share limits
- **GIVEN** sync and async callers hitting `statsapi.mlb.com` concurrently at a configured 8 req/s
- **THEN** they share one limiter: after an initial burst of up to 8 requests (the bucket holds one second), the requests of all callers together are paced at 8 per second, and no more than `max_concurrency` are in flight at once.
- Verified by `tests/test_concurrency.py::test_sync_threads_and_async_callers_share_one_host_limiter` and `::test_concurrency_bound_holds_across_sync_and_async_callers`.

#### Scenario: Retry policy
- **WHEN** the server returns 429 with `Retry-After: 2`
- **THEN** the client waits at least 2 seconds and retries up to `max_retries`
- **AND** a 404 is never retried.

#### Scenario: Conditional request
- **GIVEN** a stored ETag and a 304 response
- **THEN** `HttpResult.not_modified` is true and no body is parsed.
