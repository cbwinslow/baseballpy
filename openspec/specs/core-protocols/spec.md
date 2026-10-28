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

### Requirement: Zero-Copy Arrow Stream Protocol
Normalizers and Extractors MUST yield or emit data conforming to Apache Arrow PyCapsule protocol (`__arrow_c_stream__` or `pyarrow.RecordBatchReader`).

#### Scenario: Streaming high-volume pitch data
- **GIVEN** a multi-season Statcast query yielding 1,500,000 pitch records
- **WHEN** processed by the pipeline
- **THEN** data streams in bounded batches of 50,000 rows without accumulating full multi-gigabyte datasets in memory unless explicitly requested.
