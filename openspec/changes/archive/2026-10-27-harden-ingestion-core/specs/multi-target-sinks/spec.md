## ADDED Requirements

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
