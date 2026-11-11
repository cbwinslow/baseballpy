## ADDED Requirements

### Requirement: Shared Raw Blobs and Content-Addressed References
A `RawStore` MAY store shared raw payloads under `raw/_blobs/<prefix>/<sha256>.*` and record a `blob_ref` in dataset raw manifests. When resolving raw content for a chunk, the store MUST read from `raw/_blobs/` if `blob_ref` is present, and fall back to the dataset's legacy partition path if `blob_ref` is omitted.

#### Scenario: Multiple datasets share an upstream raw blob
- **WHEN** an upstream response provides records for multiple datasets
- **THEN** the raw payload is written once to `raw/_blobs/` and each dataset's manifest references the shared blob with the same sha256 checksum
- Verified by `tests/test_raw_shared.py::test_shared_raw_blob_deduplication`.

#### Scenario: Backward-compatible resolution for legacy raw chunks
- **WHEN** a raw manifest entry lacks `blob_ref`
- **THEN** `RawStore` resolves the raw payload from `raw/<source>/<dataset>/season=<season>/<chunk>.*`
- Verified by `tests/test_raw_shared.py::test_legacy_raw_chunk_resolution`.
