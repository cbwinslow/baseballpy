# concurrency-and-rate-limiting Specification

## Purpose
Defines concurrency boundaries, host-specific token-bucket rate limiting, and exponential retry backoff policies for network extractors in `baseballpy`.

## Requirements

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

### Requirement: Jittered Exponential Backoff
The system MUST automatically retry failed requests on HTTP 408, 425, 429, 500, 502, 503, 504 and connect timeout errors using exponential backoff with randomized jitter up to `max_retries` (default 5).

#### Scenario: Transient errors retry up to the limit
- **WHEN** a request fails with a transport error or a retryable status
- **THEN** it is retried, honoring `Retry-After`, and the client gives up after `max_retries`
- Verified by `tests/test_hardening.py::test_http_retries_transport_errors, ::test_http_gives_up_after_max_retries and ::test_http_retries_429_with_retry_after_then_succeeds`.

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

### Requirement: Bounded Hydrate Batch Concurrency
When a high-volume request requires player hydration batches (such as split stat pools under HTTP 406 fallback), the extractor MUST execute batch downloads concurrently using bounded concurrency up to `max_concurrency` while strictly routing through the host rate limiter.

#### Scenario: Hydrate batches execute concurrently within rate limit
- **GIVEN** an MLB endpoint requiring 10 hydrate batches of player IDs
- **WHEN** the fallback extraction is executed
- **THEN** batches are downloaded concurrently across worker tasks and bounded by the host rate limiter (10 req/s) with zero 429 errors.
- Verified by `tests/test_concurrency.py::test_hydrate_batches_execute_concurrently`.

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

### Requirement: One Process Per Host
The per-host rate and in-flight caps are kept per process, so a process MUST claim a host with an operating-system file lock the first time it asks it something, a second process asking the same host MUST be refused with a clear message (unless `BASEBALLPY_RATE_ALLOW_PARALLEL_PROCESSES` is set), a claim MUST end with its process however the process ends, and other hosts MUST NOT be blocked.

#### Scenario: A second process is refused and a crash frees the host
- **GIVEN** one process holds a host
- **WHEN** another process asks the same host, then the holder ends abruptly
- **THEN** the second is refused with `HostBusyError`, a different host is not blocked, and after the crash the host can be claimed again.
- Verified by `tests/test_hostlock.py::test_a_second_process_is_refused_until_the_first_ends_even_by_a_crash`.

#### Scenario: The client claims on first use and can opt out
- **WHEN** an `HttpClient` with a lock folder asks a host another process holds
- **THEN** it is refused, a client with `allow_parallel_processes` is not, and a client with no lock folder never claims.
- Verified by `tests/test_hostlock.py::test_the_http_client_claims_a_host_on_first_use_and_the_opt_out_skips_the_claim` and `tests/test_hostlock.py::test_a_client_without_a_lock_folder_never_claims`.
