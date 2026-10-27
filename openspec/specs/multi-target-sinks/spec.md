# Multi-Target Sinks Specification

## 1. Overview
`baseballpy` provides decoupled, pluggable storage sinks adhering to `SinkProtocol`:
- `DuckDBSink`: Direct zero-copy table creation and view registration into embedded or persistent DuckDB databases (`append` and `replace` modes).
- `ParquetSink`: Partitioned, compressed Parquet writer using Snappy/ZSTD compression.
- `PolarsSink`: Zero-copy handoff into eager `pl.DataFrame` and lazy `pl.LazyFrame`.
- `DltSink`: Native bridge streaming PyArrow tables into relational and cloud data warehouses (PostgreSQL, Snowflake, BigQuery, MotherDuck) via `dlt` pipelines with schema auto-evolution.

---

## 2. Invariants
- Sinks must never initiate outbound network requests.
- Sinks consume standardized `pyarrow.Table` or `pyarrow.RecordBatchReader`.
- No forced pandas conversions or string truncations during sink emission.

### Requirement: Safe, Idempotent DuckDB Writes
`DuckDBSink` MUST validate identifiers, support `append`, `replace` and keyed `upsert`, write by column name, and stream over one connection.

#### Scenario: Injection attempt
- **WHEN** `table_name="x; DROP TABLE y"`
- **THEN** `ValueError` is raised and nothing executes.

#### Scenario: Idempotent re-ingest
- **GIVEN** pitches keyed `(game_pk, at_bat_number, pitch_number)`
- **WHEN** the same table is upserted twice
- **THEN** the row count is unchanged.

### Requirement: Protocol Conformance
All sinks MUST implement `write(table, destination, **kw) -> int` and `write_stream(reader, destination, **kw) -> int`.

### Requirement: Atomic Parquet
`ParquetSink` MUST write via `.part` + atomic replace and support `partition_by`.
