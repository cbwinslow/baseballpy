# core-protocols Specification

## Purpose
Defines the decoupled `typing.Protocol` interfaces governing data extraction, schema normalization, and multi-format sink destinations in `baseballpy`.

## Requirements

### Requirement: Decoupled Protocol Hierarchy
The system MUST decouple network extraction, schema normalization, and storage ingestion via strict Python `typing.Protocol` classes, preventing direct dependencies between network I/O and storage engines.

#### Scenario: Custom Extractor with Standard Sink
- **GIVEN** an extractor implementing `ExtractorProtocol` and a sink implementing `SinkProtocol`
- **WHEN** data flows through `Pipeline.run(extractor, normalizer, sink)`
- **THEN** the sink consumes `pyarrow.RecordBatch` streams without knowing the network protocol, URL, or caching layer used by the extractor.

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
