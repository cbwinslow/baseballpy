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

### Requirement: Names Follow One Rule And Unknown Folders Fail
Sources and datasets MUST be `lower_snake_case`; a dataset's view MUST be `<source>_<dataset>` (with the prefix `mlb` for the `mlb_api` source) and unique; every source MUST have a `docs/sources/<source>.md` and every such file a source; and `baseballpy catalog layout` MUST fail on any folder under `processed/` (a source or a dataset) that no registered dataset owns.

#### Scenario: Rules and a stray folder
- **WHEN** the registry is checked and a lake holds a misspelled dataset folder and an unknown source folder
- **THEN** names, views and doc files satisfy the rules, and the layout check reports both folders as failing UNKNOWN_FOLDER findings while a registered folder is not reported
- Verified by `tests/test_naming_rules.py::test_sources_and_datasets_are_lower_snake_case`, `tests/test_naming_rules.py::test_views_follow_source_underscore_dataset_with_one_declared_exception`, `tests/test_naming_rules.py::test_every_source_has_a_doc_file_and_every_doc_file_has_a_source`, `tests/test_naming_rules.py::test_a_processed_folder_no_dataset_owns_fails_the_layout_check` and `tests/test_naming_rules.py::test_registered_folders_are_not_unknown`.

### Requirement: A Schema That Gains Columns Does Not Stop Compacted Files From Being Rewritten
Writing a compacted file MUST line each chunk up with the registered schema by column name: a column the chunk lacks is filled with empty cells, and a column the schema lacks MUST raise an error instead of being dropped.

#### Scenario: Old and new chunks share one file
- **WHEN** a chunk written before a schema gained `name_slug` and a chunk written after are compacted together, and a chunk with an unknown column is offered
- **THEN** the file holds all rows with `name_slug` empty for the old ones, and the unknown column is refused
- Verified by `tests/test_compacted_schema.py::test_old_rows_get_empty_new_columns`, `tests/test_compacted_schema.py::test_a_column_the_schema_lacks_is_refused_not_dropped` and `tests/test_compacted_schema.py::test_old_and_new_chunks_are_written_into_one_file`.

### Requirement: The Season Catalog Is The Lake Inventory
`baseballpy db sync` MUST build the view `v_season_catalog` with one row per source, dataset and season
(season NULL for unpartitioned datasets) and the columns `source`, `dataset`, `season`, `row_count`,
`files`, `view_name`, `bytes` and `last_written_at`. `view_name` MUST be the DuckDB view that serves the
dataset (the registry view name, or `<source>_<dataset>` for an unregistered folder), `bytes` MUST be the
total size of the visible Parquet files and `last_written_at` the newest modification time of those files.

#### Scenario: A person asks what the lake holds
- **WHEN** the database is synced and `v_season_catalog` is queried for a source
- **THEN** each held season of each dataset has its row count, file count, byte size, last write time and
  the view name to query, and an older query that selects only the first five columns still works
- Verified by `tests/test_database.py::test_season_catalog_is_the_lake_inventory`.

### Requirement: One Compaction Per Dataset At A Time
`compact_dataset` (and so `baseballpy compact` and the download queue's stage compaction) MUST take an
operating-system lock named for the dataset (`compact-<source>-<dataset>` in the lake's locks folder)
before it changes any file, and MUST give it back when it ends. A second compaction of the same dataset
MUST be refused with a clear message and MUST change no file and no record; compaction of other datasets
MUST NOT be blocked. A dry run MUST NOT need the lock. `baseballpy compact` MUST report a refused dataset
as skipped and exit non-zero after the other datasets are done.

#### Scenario: A second compaction of the same dataset is refused
- **WHEN** another process holds the compaction lock of a dataset and `compact_dataset` runs for it
- **THEN** it raises `HostBusyError`, no file or record changes, and after the holder ends (even by a
  crash) the dataset compacts normally
- Verified by `tests/test_compact_lock.py::test_a_second_compaction_of_one_dataset_is_refused_and_changes_nothing`.

#### Scenario: The command skips a busy dataset
- **WHEN** `baseballpy compact` is run for a dataset another process is compacting
- **THEN** it prints that the dataset was skipped because it is busy and exits with a non-zero code
- Verified by `tests/test_compact_lock.py::test_the_compact_command_skips_a_busy_dataset_and_fails`.

### Requirement: Compaction Is Deterministic
Compacting the same chunks in one run MUST produce byte-identical compacted files whatever order the chunks
were downloaded in; a rerun MUST rewrite nothing; and compacting at different times MUST leave the same
rows (the grouping into files may differ, and a reader must not depend on row order).

#### Scenario: Another download order gives the same files
- **WHEN** the same four chunks are stored in two lakes in opposite order and each is compacted
- **THEN** the compacted files have the same names and the same sha256
- Verified by `tests/test_compact_deterministic.py::test_the_same_chunks_give_byte_identical_files_whatever_the_download_order`.

#### Scenario: A rerun and a staged run
- **WHEN** a compacted dataset is compacted again, and another lake is compacted in two stages
- **THEN** the rerun rewrites nothing and both lakes hold the same rows
- Verified by `tests/test_compact_deterministic.py::test_a_rerun_rewrites_nothing` and `tests/test_compact_deterministic.py::test_compacting_at_different_times_gives_the_same_rows`.

### Requirement: A Fresh Download Has The Lake Shape
After a download into an empty home, every source MUST leave `processed/<source>/<dataset>/[season=YYYY/]`
with only `part-*`, `compact-NNNN` or `seg-NNNN` Parquet files (in a season folder exactly when the dataset
is split by season), every file with the registered column names, order and types, no folder for an
unregistered dataset, no half-written file, raw files that match their recorded sha256, and after
`baseballpy db sync` one view per dataset with data whose row count equals the rows in the files. The same
MUST hold after compaction, and a second run MUST NOT download again.

#### Scenario: Every source's download matches the shape
- **WHEN** a Statcast season, a Retrosheet season, the Chadwick register, the Lahman tables and the MLB game datasets (and every supported MLB endpoint that has a recorded answer) are downloaded from the recorded fixtures into empty homes
- **THEN** the contract holds, holds again after compaction, and a second run makes no request
- Verified by `tests/test_download_contract.py::test_a_fresh_statcast_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_retrosheet_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_chadwick_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_lahman_download_has_the_lake_shape`, `tests/test_download_contract.py::test_a_fresh_mlb_game_download_has_the_lake_shape` and `tests/test_download_contract.py::test_every_mlb_endpoint_download_has_the_lake_shape`.

#### Scenario: A dataset whose chunks are all empty keeps its view through compaction
- **WHEN** every chunk of a dataset is empty and the dataset is compacted
- **THEN** one empty file stays (the first chunk's), the chunks still count as downloaded, and the dataset's view still exists and counts zero rows
- Verified by `tests/test_compact.py::test_a_dataset_whose_chunks_are_all_empty_keeps_one_empty_file_and_its_view`.

#### Scenario: A broken lake is caught
- **WHEN** a stray file name, a wrong column type or an unregistered folder is added to a downloaded lake
- **THEN** the contract check fails
- Verified by `tests/test_download_contract.py::test_the_contract_catches_a_stray_file_a_wrong_type_and_an_unknown_folder`.

### Requirement: Savant Leaderboards And Retrosheet Reference Files Match The Shape
Every supported Savant leaderboard downloaded for a season, and Retrosheet's reference ingest, MUST satisfy the
same lake-shape contract as the other sources, before and after compaction.

#### Scenario: Leaderboards and reference files
- **WHEN** every supported leaderboard is downloaded for one season from its recorded page, and a Retrosheet season and its reference files are downloaded
- **THEN** the lake-shape contract holds, and holds again after compaction
- Verified by `tests/test_download_contract.py::test_every_statcast_leaderboard_download_has_the_lake_shape` and `tests/test_download_contract.py::test_a_fresh_retrosheet_download_has_the_lake_shape`.

#### Scenario: A segment download matches the same shape
- **WHEN** MLB games are downloaded as segments (ADR 95) into an empty home
- **THEN** every processed file is a `seg-NNNN.parquet` with the registered columns plus the lineage column, the layout check reports no mixed schema, the raw segments and processed segment files match their commit-line checksums, each dataset has its view with the right count, and a second run fetches nothing
- Verified by `tests/test_download_contract.py::test_a_fresh_mlb_game_download_as_segments_has_the_lake_shape` and `tests/test_layout_audit.py::test_a_segment_file_with_the_lineage_column_is_not_a_mixed_schema`.

### Requirement: The Inventory Reads A Parquet Footer Only For A New Or Changed File
The DuckDB inventory (`v_season_catalog`) MUST count rows from a cache of Parquet footers keyed by file path, size
and modification time, MUST open a footer only for a file that is new or changed, and MUST give the same rows with or
without the cache.

#### Scenario: A second refresh opens no footer
- **WHEN** the inventory rows are built twice and then one file is rewritten
- **THEN** the second build opens no footer and returns the same rows, and the third reads only the rewritten file and counts its new rows
- Verified by `tests/test_database.py::test_the_inventory_reads_a_file_footer_only_when_the_file_is_new_or_changed`.
