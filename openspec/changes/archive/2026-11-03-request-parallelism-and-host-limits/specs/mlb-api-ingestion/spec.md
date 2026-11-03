## ADDED Requirements

### Requirement: Request-Level Parallelism
The requests of one MLB endpoint (team, player, game or season fan-out) MUST run on a bounded pool of at most `max_concurrency` workers, gated only by the shared host token bucket and in-flight limit. Without `keep_going` the first failure MUST stop the queued requests and raise; with it, refused requests MUST be listed in the report and the others ingested. The report's 404 count MUST include every worker's.

#### Scenario: One endpoint's requests overlap
- **GIVEN** an endpoint with 12 requests of 30 ms each and `max_concurrency=4`
- **WHEN** it is ingested
- **THEN** the peak number of requests in flight is between 2 and 4 and every request is stored.
- Verified by `tests/test_request_parallelism.py::test_one_endpoints_requests_overlap_within_the_bound`.

#### Scenario: Fail-fast is kept
- **GIVEN** an endpoint whose second request answers HTTP 500 and `keep_going` is false
- **WHEN** it is ingested
- **THEN** the error is raised and the remaining queued requests are not fetched.
- Verified by `tests/test_request_parallelism.py::test_fail_fast_stops_queued_requests`.

#### Scenario: Missing records are counted across workers
- **GIVEN** an endpoint where three requests answer HTTP 404 and `tolerate_missing` applies
- **WHEN** it is ingested in parallel
- **THEN** the report's `missing` is 3.
- Verified by `tests/test_request_parallelism.py::test_missing_count_is_summed_across_workers`.
