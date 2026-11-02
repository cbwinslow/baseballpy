## ADDED Requirements

### Requirement: Bounded Hydrate Batch Concurrency
When a high-volume request requires player hydration batches (such as split stat pools under HTTP 406 fallback), the extractor MUST execute batch downloads concurrently using bounded concurrency up to `max_concurrency` while strictly routing through the host rate limiter.

#### Scenario: Hydrate batches execute concurrently within rate limit
- **GIVEN** an MLB endpoint requiring 10 hydrate batches of player IDs
- **WHEN** the fallback extraction is executed
- **THEN** batches are downloaded concurrently across worker tasks and bounded by the host rate limiter (8 req/s) with zero 429 errors.
- Verified by `tests/test_concurrency.py::test_hydrate_batches_execute_concurrently`.
