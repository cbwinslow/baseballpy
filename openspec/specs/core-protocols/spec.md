# core-protocols Specification

## Purpose
Defines the decoupled `typing.Protocol` interfaces governing data extraction, schema normalization, and multi-format sink destinations in `baseballpy`.

## Requirements

### Requirement: Decoupled Protocol Hierarchy
The contracts that other code consumes MUST be enforced by tests: sinks satisfy `SinkProtocol`, the live streamer satisfies `StreamExtractorProtocol`, and every source registered in the dataset registry has an `IngestAdapter` (`source`, `all_seasons`, `plan`, `run`) registered in `baseballpy.ingest`; the ingest runner and the CLI MUST NOT import a concrete source. `ExtractorProtocol` and `NormalizerProtocol` are optional shape guides for single-dataset sources and are not enforced (ADR 39).

#### Scenario: Every registered source has an adapter
- **GIVEN** the dataset registry and the registered adapters
- **WHEN** the contract test runs
- **THEN** each source that owns datasets has an adapter satisfying `IngestAdapter` whose planned jobs carry that source name.
- Verified by `tests/test_ingest_contract.py::test_every_source_with_datasets_has_a_registered_adapter and ::test_every_adapter_satisfies_the_protocol_and_plans_its_own_jobs`.

#### Scenario: Swapping Sinks without Re-Extracting
- **GIVEN** an extracted and normalized `pyarrow.Table`
- **WHEN** passed to `DuckDBSink`, `PolarsSink`, `ParquetSink`, or `DltSink`
- **THEN** each sink writes the data to its respective destination using native zero-copy Arrow memory buffers where supported.
- Verified by `tests/test_sinks.py::test_duckdb_sink_append_and_replace and ::test_parquet_sink and ::test_polars_sink and ::test_dlt_sink` and `tests/test_hardening.py::test_all_sinks_conform_to_protocol_signatures`.

### Requirement: Arrow Streaming
Normalizers MUST produce `pyarrow` tables or batches per source chunk (a Statcast window, a Retrosheet file, an MLB request); the stores MUST append each chunk to its Parquet part through one `ParquetWriter` instead of building a whole-dataset table, and sinks MUST accept a `pyarrow.RecordBatchReader` through `write_stream`. No batch size is fixed: it is the size of the source chunk.

#### Scenario: Streaming a multi-season query
- **GIVEN** a multi-season Statcast query
- **WHEN** it is ingested
- **THEN** each window is written to its own Parquet part as it arrives, so memory holds one window rather than the whole result.
- Verified by `tests/test_smoke.py::test_smoke_statcast_multi_chunk_idempotency_and_manifest` and `tests/test_lake.py::test_put_stream_writes_row_groups_atomically_and_skips_empty_streams`.
