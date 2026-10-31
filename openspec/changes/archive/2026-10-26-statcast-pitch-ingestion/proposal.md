# Change Proposal: Statcast Pitch-Level Ingestion Engine

## Why
Statcast (Baseball Savant) is the primary data source for modern pitch-by-pitch ball tracking, exit velocity, launch angles, spin metrics, and expected statistics (xBA, xwOBA, xSLG).
However, existing ingestion tools suffer from critical defects:
1. They crash or return truncated results on queries exceeding ~25,000 rows (Savant's server-side cap) or timeout with HTTP 504 on date ranges > 5–7 days.
2. They dump data into pandas DataFrames as untyped object strings with erratic null values (`"null"`, `""`, `"NA"`).
3. They drop or omit newly added Statcast fields (such as 2024 bat tracking `bat_speed` and `swing_length`).
4. They lack rate limiting, retry backoff, and direct zero-copy sinks to DuckDB and Parquet.

## What Changes
1. Implement `baseballpy.sources.statcast`:
   - `schema.py`: Exhaustive canonical PyArrow schema covering ALL Statcast columns across eras (90+ core columns, plus bat tracking and coordinate fields), strictly typed as `date32`, `float32`, `int16`, `int32`, `bool_`, and `dictionary`.
   - `extractor.py`: Conforming to `ExtractorProtocol`:
     - Automatic date chunking into bounded weekly windows (e.g. 5–7 days).
     - Token-bucket rate limiting (2.5 req/s via `aiolimiter`) tied to `baseballsavant.mlb.com`.
     - Bounded async concurrency via semaphore.
     - Jittered retry backoff via `tenacity`.
     - Local caching in `~/.baseballpy/cache/statcast/` partitioned by date range.
   - `normalizer.py`: Conforming to `NormalizerProtocol`:
     - Parses CSV bytes into PyArrow Table matching the canonical schema.
     - Coerces sentinel values (`"null"`, `""`, `"NA"`, `"None"`) to null.
     - Dictionary-encodes high-cardinality repeat strings (pitch types, events, descriptions).
     - Dynamic evolutionary schema detection preserving newly discovered columns (ADR 9 & ADR 15).
2. Implement Sinks in `baseballpy.sinks`:
   - `DuckDBSink`: Direct DuckDB table creation and appending without pandas conversion.
   - `ParquetSink`: Partitioned compressed columnar file writer.
3. Expose top-level API:
   - `baseballpy.statcast(start_dt, end_dt, ...)`
   - `baseballpy.to_duckdb(table, ...)`
   - `baseballpy.to_parquet(table, ...)`
4. Full telemetry integration recording duration, records count, throughput (rps), and cache hits in `~/.baseballpy/logs/audit.jsonl`.
5. Offline unit tests and mocked integration tests in `tests/test_statcast.py` and `tests/test_sinks.py`.
