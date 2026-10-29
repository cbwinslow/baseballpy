# data-export Specification

## Purpose
Sends the cached, typed datasets of any source to Parquet, CSV, DuckDB or PostgreSQL through one registry-driven path, verified and audited.

## Requirements

### Requirement: Registry-Driven Verified Export
`baseballpy export <source>[:<dataset>] --to parquet|csv|duckdb|postgres` MUST read only the cached typed Parquet, take names, schema, key and season layout from the dataset registry (no per-source code), write files to `exports/<source>/<dataset>/[season=YYYY/]<dataset>.<ext>` (overridable), name database tables after the registry `view` name (PostgreSQL schema `baseballpy` by default), read every export back and compare rows and types, record an `export` audit event, and fail with an instruction when nothing is cached.

#### Scenario: Files land in the registry layout and read back equal
- **WHEN** a dataset is exported to Parquet or CSV, with and without `--out`, season-partitioned or not
- **THEN** the files are at `<root>/<source>/<dataset>/[season=YYYY/]<dataset>.<ext>`, a CSV has its `.schema.json`, and reading them back equals the cached table
- Verified by `tests/test_export.py::test_files_land_in_the_exports_folder_with_the_registry_layout`, `tests/test_export.py::test_out_overrides_the_folder_and_seasons_get_season_folders` and `tests/test_export.py::test_the_exports_folder_can_be_moved_by_environment`.

#### Scenario: Databases keep the types and honour the modes
- **WHEN** a dataset is exported to DuckDB or PostgreSQL with replace, append and merge
- **THEN** replace never grows the table, append adds the rows, merge updates rows with the same registry key without duplicating, and the column types match the schema
- Verified by `tests/test_export.py::test_duckdb_modes_with_seasons`, `tests/test_export.py::test_postgres_replace_append_merge_with_registry_names` and `tests/test_dlt_typed.py::test_merge_updates_matching_keys_and_never_duplicates`.

#### Scenario: Problems are reported, not hidden
- **WHEN** a dataset has nothing cached, a mode or target is unknown, a file target is asked to merge, the PostgreSQL URL is missing, a merge key has empty values, or the read-back differs
- **THEN** the export fails with a message saying what to do, and a failed read-back is reported as an error (the files already written stay on disk for inspection)
- Verified by `tests/test_export.py::test_missing_data_modes_targets_and_seasons_are_refused_clearly`, `tests/test_export.py::test_postgres_url_comes_from_the_environment_or_an_error_says_how`, `tests/test_export.py::test_merge_is_refused_when_a_key_column_has_empty_values` and `tests/test_export.py::test_a_difference_found_on_read_back_fails_the_export`.

#### Scenario: The command and the audit log
- **WHEN** `baseballpy export` runs for a source, for named datasets, and for a missing dataset
- **THEN** uncached datasets of a source-wide export are skipped, a named uncached dataset exits 1, and every export writes an `export` audit event
- Verified by `tests/test_export.py::test_command_exports_named_datasets_and_skips_uncached_ones_of_a_source`, `tests/test_export.py::test_command_fails_for_an_explicit_dataset_with_nothing_cached_and_for_bad_input`, `tests/test_export.py::test_command_reaches_postgres_through_the_environment` and `tests/test_export.py::test_every_export_is_written_to_the_audit_log`.

### Requirement: Typed CSV With a Schema Sidecar
The CSV sink MUST write UTF-8 CSV atomically with a `<name>.schema.json` sidecar holding every column's Arrow type and nullability and the exact Arrow schema, MUST read it back to an identical table, MUST treat an empty cell as NULL, and MUST refuse nested columns.

#### Scenario: Every registry column type round trips
- **WHEN** a table with string, int8/16/32/64, float, double, bool, date, UTC timestamp and dictionary columns is written to CSV and read back
- **THEN** the table is equal, including NULLs, quotes, commas, newlines and unicode; an empty table keeps its header and schema; a nested column is refused before anything is written
- Verified by `tests/test_csv_sink.py::test_every_registry_column_type_round_trips_exactly`, `tests/test_csv_sink.py::test_an_empty_table_still_writes_header_and_schema` and `tests/test_csv_sink.py::test_nested_columns_are_refused_with_a_clear_message`.

### Requirement: Typed dlt Database Sink
The `dlt` sink MUST declare key columns not-null, support append, replace and merge on a primary key, and report the row count and column types the database holds so they can be compared with the Arrow schema (a `float` becomes `double` and `int8` a `tinyint` or `smallint`; any other difference is reported).

#### Scenario: Types survive and differences are reported
- **WHEN** an Arrow table with all registry types is loaded into DuckDB and PostgreSQL and the database types are compared
- **THEN** there is no mismatch, and a changed column type or column list is reported
- Verified by `tests/test_dlt_typed.py::test_types_survive_the_load_and_the_read_back_reports_no_mismatch` and `tests/test_dlt_typed.py::test_sql_type_table_and_mismatch_report`.

### Requirement: Identifier Names Are Preserved
Exports to server databases MUST keep every column name exactly as the Arrow schema spells it (mixed case and names starting with a digit included), so the read-back check compares the same names.

#### Scenario: Mixed-case and digit-leading names in DuckDB and PostgreSQL
- **WHEN** a table with columns `playerID`, `yearID`, `2B` and `HR` is loaded and merged on its original-case key
- **THEN** the database holds the same column names and the merge does not duplicate rows
- Verified by `tests/test_dlt_typed.py::test_mixed_case_and_digit_leading_names_survive_unchanged`.
