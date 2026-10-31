## ADDED Requirements

### Requirement: Every MLB Stats API Download and Ingest Is Audit-Logged and Timed
Every MLB Stats API operation that lists, downloads, parses or stores data MUST write one structured audit event to `logs/audit.jsonl` with the operation name, the source `mlb_api`, the endpoint, the destination, the record count, the duration and whether the answer came from the lake. The operation names MUST be stable and documented: `mlb_api_fetch` and `mlb_api_cache_read` for the hand-written datasets, `mlb_<endpoint>` for a declarative endpoint (including the hydrate pool fallback, whose event records the refused pool URL, and a raw-only endpoint, whose event records the raw files kept), `mlb_snapshot`/`mlb_snapshot_bytes` for a projected read (destination = set name or `complete`) and `mlb_stream` for a live poll. A failed download MUST be logged with status `FAILURE` and the error text and MUST be re-raised.

#### Scenario: A declarative endpoint, cold and cached
- **WHEN** a declarative endpoint is ingested and then ingested again
- **THEN** two `mlb_<endpoint>` events exist, the first with `cache_hit` false and rows, the second with `cache_hit` true
- Verified by `tests/test_mlb_audit.py::test_a_declarative_endpoint_is_audited_cold_and_cached`.

#### Scenario: A raw-only endpoint
- **WHEN** an endpoint without a generated schema is ingested and then ingested again
- **THEN** two `mlb_<endpoint>` events exist, the first with the raw files stored and the second with `cache_hit` true
- Verified by `tests/test_mlb_audit.py::test_a_raw_only_endpoint_is_audited_cold_and_cached`.

#### Scenario: The hydrate pool fallback
- **WHEN** the pool route answers 406 and the people route serves the pool
- **THEN** the `mlb_<endpoint>` event records the stored rows and the refused pool URL as its endpoint
- Verified by `tests/test_mlb_audit.py::test_the_pool_fallback_records_its_rows_and_refused_url`.

#### Scenario: A projected snapshot
- **WHEN** `snapshot(fields="score")` and `snapshot_bytes()` run
- **THEN** `mlb_snapshot` and `mlb_snapshot_bytes` events exist with destinations `score` and `complete`
- Verified by `tests/test_mlb_audit.py::test_a_projected_snapshot_is_audited_with_its_set_name`.

#### Scenario: A refused download
- **WHEN** a request answers 406
- **THEN** the endpoint's audit event has status `FAILURE` and carries the HTTP error, and the error propagates
- Verified by `tests/test_mlb_audit.py::test_a_refused_request_is_logged_as_a_failure`.
