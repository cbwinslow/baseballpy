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
