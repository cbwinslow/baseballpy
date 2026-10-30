## ADDED Requirements

### Requirement: List Columns Reach Both Databases
A dataset with a list column (for example `retrosheet.box_records.fields`) MUST export to DuckDB and to PostgreSQL and pass the read-back type check: DuckDB keeps a native array and PostgreSQL stores the list as JSON, loaded with dlt's `insert_values` loader because its CSV loader cannot write lists.

#### Scenario: A list column is exported and verified
- **WHEN** a dataset with a `list<string>` column is exported to DuckDB, and written through the database sink to DuckDB and PostgreSQL
- **THEN** the row count matches and the read-back reports no type mismatch
- Verified by `tests/test_export.py::test_a_list_column_exports_to_duckdb_and_verifies` and `tests/test_dlt_typed.py::test_a_list_column_loads_into_either_database_and_reads_back_without_mismatch`.
