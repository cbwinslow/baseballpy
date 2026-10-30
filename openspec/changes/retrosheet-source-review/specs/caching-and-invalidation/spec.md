## ADDED Requirements

### Requirement: A Schema Change Invalidates Stored Chunks
Every processed chunk MUST record a digest of the dataset schema it was written under (`schema_sha256` in its manifest entry), and a chunk whose recorded digest differs from the dataset's current schema MUST NOT be served as current, so it is rebuilt on the next run without `--refresh`. A chunk written before the digest existed carries none and is trusted.

#### Scenario: A column is added
- **WHEN** a chunk was stored, the dataset's schema then gains a column, and the dataset is requested again
- **THEN** the chunk is treated as stale and rebuilt, and the new manifest entry carries the new digest
- Verified by `tests/test_lake.py::test_a_schema_change_makes_a_stored_chunk_stale_without_refresh and tests/test_retrosheet_currency.py::test_a_chunk_written_under_another_schema_is_rebuilt_without_refresh`.
