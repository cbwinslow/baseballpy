## ADDED Requirements

### Requirement: Single Shared HTTP Client
Every network fetch MUST go through `baseballpy.core.http.HttpClient`, applying a per-host token bucket, a global bounded semaphore, HTTP/2 pooling and jittered exponential retry.

#### Scenario: Sync and async callers share limits
- **GIVEN** sync and async callers hitting `statsapi.mlb.com` concurrently at a configured 8 req/s
- **THEN** no more than 8 requests start in any one-second window across all callers.

#### Scenario: Retry policy
- **WHEN** the server returns 429 with `Retry-After: 2`
- **THEN** the client waits at least 2 seconds and retries up to `max_retries`
- **AND** a 404 is never retried.

#### Scenario: Conditional request
- **GIVEN** a stored ETag and a 304 response
- **THEN** `HttpResult.not_modified` is true and no body is parsed.
