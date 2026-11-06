# lake-access Specification

## Purpose
Two documented doors from the lake to a DataFrame: `baseballpy.read` for bulk rows and `baseballpy.sql` for DuckDB analysis, over the same Parquet files.

## Requirements

### Requirement: Read Rows Straight From Parquet
`baseballpy.read(dataset, seasons=None, columns=None, backend="polars", lazy=False)` MUST load a registered dataset (named `source.name`, by view name or by a unique bare name) directly from `processed/` Parquet, open only the season folders asked for, return only the columns asked for, and offer Polars, pandas and Arrow results and a lazy Polars frame. Unknown or ambiguous names, seasons on a dataset that is not split by season, and a dataset with no data MUST fail with a message that says what to do.

#### Scenario: Seasons, columns, backends and names
- **WHEN** a dataset is read for all seasons, one season, a range, some columns, as Arrow and lazily, and by view name
- **THEN** the rows and a `season` column are right, only the asked seasons and columns come back, and bad input is refused clearly
- Verified by `tests/test_access.py::test_read_all_seasons_has_every_row_and_a_season_column`, `tests/test_access.py::test_read_seasons_and_columns_open_only_what_is_asked`, `tests/test_access.py::test_read_backends_and_lazy` and `tests/test_access.py::test_read_resolves_view_and_bare_names_and_rejects_bad_input`.

### Requirement: SQL Over The Same Views, Read-Only
`baseballpy.sql(query, backend="polars")` MUST run a DuckDB query over the lake views on a read-only connection and return a DataFrame; it MUST give the same answers as `read`, support joins across sources, and refuse statements that change data or a missing database.

#### Scenario: Same answers, joins, no writes
- **WHEN** a group-by and a cross-source join are run with `sql` and compared with `read`, and a `DROP VIEW` is attempted
- **THEN** counts and sums agree, the join is right, and the change is refused
- Verified by `tests/test_access.py::test_sql_gives_the_same_rows_as_read_and_can_join` and `tests/test_access.py::test_sql_refuses_to_change_data_and_needs_a_database`.

### Requirement: Strict Views Skip The Schema Merge
Views of registered datasets MUST NOT use `union_by_name` (every part has the dataset's one strict schema); views of unregistered datasets keep it. The parts of a dataset MUST share one schema.

#### Scenario: View options and part schemas
- **WHEN** view SQL is built for a registered and an unregistered dataset and a dataset with several chunks is written
- **THEN** only the unregistered view merges schemas, and all parts have equal schemas
- Verified by `tests/test_access.py::test_registered_views_skip_the_schema_merge_and_parts_share_one_schema`.
