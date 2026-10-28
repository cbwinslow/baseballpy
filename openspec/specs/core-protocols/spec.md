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

#### Scenario: Swapping Sinks without Re-Extracting
- **GIVEN** an extracted and normalized `pyarrow.Table`
- **WHEN** passed to `DuckDBSink`, `PolarsSink`, `ParquetSink`, or `DltSink`
- **THEN** each sink writes the data to its respective destination using native zero-copy Arrow memory buffers where supported.

### Requirement: Arrow Streaming
Normalizers MUST produce `pyarrow` tables or batches per source chunk (a Statcast window, a Retrosheet file, an MLB request); the stores MUST append each chunk to its Parquet part through one `ParquetWriter` instead of building a whole-dataset table, and sinks MUST accept a `pyarrow.RecordBatchReader` through `write_stream`. No batch size is fixed: it is the size of the source chunk.

#### Scenario: Streaming a multi-season query
- **GIVEN** a multi-season Statcast query
- **WHEN** it is ingested
- **THEN** each window is written to its own Parquet part as it arrives, so memory holds one window rather than the whole result.
