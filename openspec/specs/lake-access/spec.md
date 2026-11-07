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

### Requirement: Compaction Merges Chunks Without Losing Any Row Or Any Resume Point
`baseballpy compact` MUST merge the small chunk files of a dataset and season into a few big Parquet files (full row groups, zstd), read every new file back and compare it with its source chunks (category columns by value) before any small file is removed, and refuse and keep the small files on any difference. Chunks MUST stay in the manifest so ingests still treat them as downloaded; a compacted file MUST record where each chunk sits in its own footer; a chunk downloaded again MUST be taken out of its compacted file; a rerun MUST change nothing; leftovers of an interrupted run MUST be cleaned without duplicating rows. Zero-row part files of chunks recorded as downloaded and empty MUST be removed after their footers are checked, and such chunks MUST still count as downloaded.

#### Scenario: Merge, resume and rewrite
- **WHEN** chunks of a season are compacted, compacted again, one chunk is downloaded again, and a dry run, a corrupted copy and an interrupted run are tried
- **THEN** every row and chunk is still readable, a rerun changes nothing, the rewritten chunk replaces its rows without duplicates, a dry run and a refused copy leave the small files, and leftovers are cleaned
- Verified by `tests/test_compact.py::test_chunks_become_one_file_and_every_row_and_chunk_survives`, `tests/test_compact.py::test_a_rerun_changes_nothing_and_a_new_chunk_is_merged_in`, `tests/test_compact.py::test_a_chunk_downloaded_again_replaces_its_rows_and_never_duplicates`, `tests/test_compact.py::test_dry_run_changes_nothing`, `tests/test_compact.py::test_a_bad_copy_is_refused_and_the_small_files_stay` and `tests/test_compact.py::test_leftovers_of_an_interrupted_run_are_cleaned_without_duplicates`.

#### Scenario: Category columns, empty chunks, DuckDB and the command
- **WHEN** chunks with different category values, empty chunks, the DuckDB views and the command are used
- **THEN** values are compared by value, empty files go while the chunk still counts as downloaded, views see the compacted file, and the command reports what it merged
- Verified by `tests/test_compact.py::test_chunks_with_different_category_values_are_compacted_and_read_back_right`, `tests/test_compact.py::test_empty_chunk_files_are_removed_and_the_chunk_still_counts_as_downloaded`, `tests/test_compact.py::test_duckdb_views_and_the_footer_map_see_the_compacted_file` and `tests/test_compact.py::test_the_compact_command_reports_and_merges`.

### Requirement: Raw Text Files Are Stored Gzipped With The Checksum Of The Original
For the sources in `raw_compress_sources` (default `mlb_api`, `statcast`), `RawStore.put` MUST store json, csv and other text raw files as `<name>.gz`, record the sha256 and byte count of the original bytes plus `stored: gzip`, never leave both forms of one file, and leave files whose name already ends in `.gz`, binary files and other sources unchanged. `exists`, `get`, `verify`, the cache check and the Statcast game feed MUST work with either form. `baseballpy compress-raw` MUST convert existing files only after the file matches its recorded checksum and its compressed copy reads back equal, leave any other file as it is and report it, and do nothing on a rerun.

#### Scenario: New files, conversion and checks
- **WHEN** raw files are written, refreshed, converted, damaged and checked
- **THEN** the checksum is the original's, readers get the original bytes, a damaged file is left alone and reported, the command and a rerun behave as stated, and a file the caller already gzipped is kept and verified as it came
- Verified by `tests/test_raw_compress.py::test_a_new_raw_file_is_gzipped_but_keeps_the_checksum_of_the_original`, `tests/test_raw_compress.py::test_other_sources_and_already_packed_files_are_stored_as_they_came`, `tests/test_raw_compress.py::test_a_refresh_never_leaves_both_forms_of_one_file`, `tests/test_raw_compress.py::test_conversion_keeps_every_byte_and_checksum_and_a_rerun_does_nothing`, `tests/test_raw_compress.py::test_a_file_that_does_not_match_its_checksum_is_left_alone`, `tests/test_raw_compress.py::test_the_compress_raw_command` and `tests/test_raw_compress.py::test_a_file_the_caller_already_gzipped_is_checked_and_read_as_it_came`.

### Requirement: Offline Layout Check
`baseballpy catalog layout` MUST inspect `processed/` and `raw/` without network access or changes and report: more than ten part files in one dataset folder (TINY_FILES), zero-row part files (EMPTY_FILES), files whose columns or types differ from the registered schema (MIXED_SCHEMA), multi-group files averaging under 5,000 rows per row group (SMALL_ROW_GROUPS), compacted files no download record points at or that lack chunks their records name (ORPHAN_COMPACT), and raw text files of the configured sources that are not gzipped (RAW_PLAIN). MIXED_SCHEMA and ORPHAN_COMPACT MUST give exit code 1; the others advise and name the command that fixes them.

#### Scenario: Each finding appears, and a clean or compacted lake has none
- **WHEN** a lake is clean, has many small and empty files, a part with other columns, an unreferenced compacted file, tiny row groups or plain raw files, and the command runs
- **THEN** only the matching findings appear, compaction clears the small-file findings, and the exit code is 1 only for the two failing kinds
- Verified by `tests/test_layout_audit.py::test_a_clean_lake_has_no_findings`, `tests/test_layout_audit.py::test_many_small_files_and_empty_files_are_advised_and_compaction_clears_them`, `tests/test_layout_audit.py::test_a_part_with_other_columns_fails_the_check`, `tests/test_layout_audit.py::test_a_compacted_file_nobody_points_at_fails_the_check`, `tests/test_layout_audit.py::test_tiny_row_groups_are_advised`, `tests/test_layout_audit.py::test_plain_raw_text_files_are_advised` and `tests/test_layout_audit.py::test_the_layout_command_prints_json_and_sets_the_exit_code`.

### Requirement: A Fresh Install Works With Any Supported DuckDB
When the catalog database in the lake was written by a newer DuckDB than the installed one, a read-write open MUST move it aside (`<name>.newer-duckdb`) and rebuild the views, a read-only query MUST raise an error that names `baseballpy db sync`, and a database file at a path chosen by the caller MUST NOT be moved. The backend name `arrow` MUST mean `pyarrow`, and a DataFrame library that is not installed MUST be named with its install command.

#### Scenario: Newer catalog, arrow, missing pandas
- **WHEN** the first open of the lake catalog fails as a newer-version file, a read-only query meets the same file, `arrow` is requested, and pandas is missing
- **THEN** the old file is kept aside and the views are rebuilt, the query error names `db sync`, `arrow` returns an Arrow table, and the error for pandas says `pip install pandas`
- Verified by `tests/test_workflows.py::test_a_catalog_from_a_newer_duckdb_is_moved_aside_and_rebuilt`, `tests/test_workflows.py::test_a_read_only_query_of_a_newer_catalog_says_what_to_do`, `tests/test_workflows.py::test_arrow_is_another_name_for_pyarrow` and `tests/test_workflows.py::test_a_missing_optional_dataframe_library_says_what_to_install`.
