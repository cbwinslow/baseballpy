# multi-target-sinks Specification

## Purpose
Defines the specifications for output sinks into DuckDB, Apache Parquet, Polars, and `dlt` (PostgreSQL, BigQuery, Snowflake, MotherDuck).

## Requirements

### Requirement: Native DuckDB Sink
The system MUST provide a `DuckDBSink` that accepts Arrow Table or RecordBatchReader streams and writes them into an embedded DuckDB database file or in-memory connection without converting through pandas.

#### Scenario: Ingesting Statcast season to DuckDB
- **GIVEN** a stream of 700,000 normalized Statcast pitch records
- **WHEN** passed to `DuckDBSink(db_path="baseball.duckdb", table="statcast_pitches")`
- **THEN** creates or appends to `statcast_pitches` table using DuckDB's zero-copy Arrow appender.

### Requirement: Partitioned Parquet Sink
The system MUST provide a `ParquetSink` capable of writing Hive-partitioned datasets (e.g. `season={YYYY}/month={MM}/`).

#### Scenario: Exporting play-by-play to disk
- **GIVEN** multi-year event data
- **WHEN** exported via `ParquetSink(base_path="data/events", partition_cols=["year"])`
- **THEN** files are written partitioned by year with Snappy compression and standard PyArrow metadata.

### Requirement: Dlt Pipeline Sink
The system MUST provide a `DltSink` generator adapter wrapping any `baseballpy` source into a `dlt.resource`, allowing direct loading into PostgreSQL, BigQuery, Snowflake, and ClickHouse.

#### Scenario: Ingesting to PostgreSQL with dlt
- **GIVEN** `baseballpy.sources.mlb_api.games_resource(season=2024)`
- **WHEN** piped into `dlt.pipeline(destination="postgres")`
- **THEN** tables and schema migrations are automatically executed in PostgreSQL.
