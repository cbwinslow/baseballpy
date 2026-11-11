## ADDED Requirements

### Requirement: Batched Chunk Writes
A `ProcessedStore` MAY accept a batch of partitioned records and commit them as a consolidated chunk file `part-batch-*.parquet`. Manifests MUST record all chunk identifiers contained in the batch in a single atomic checkpoint.

#### Scenario: Multi-game batch write
- **WHEN** multiple games are processed in a batch
- **THEN** a single Parquet file is committed per dataset and the manifest records all included game chunks atomically
- Verified by `tests/test_batched_chunks.py::test_batched_chunk_write_and_read`.

#### Scenario: Mid-batch interruption rollback
- **WHEN** extraction terminates before a batch completes
- **THEN** uncommitted `.part` files are discarded and resuming re-fetches from the first uncommitted game without duplicate rows
- Verified by `tests/test_batched_chunks.py::test_interrupted_batch_resumes_cleanly`.
