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
The system MUST automatically retry failed requests on HTTP 429, 500, 502, 503, 504, and connect timeout errors using exponential backoff with randomized jitter up to `max_retries` (default 5).
