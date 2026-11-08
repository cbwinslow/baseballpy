## MODIFIED Requirements

### Requirement: Raw Text Files Are Stored Gzipped With The Checksum Of The Original
For the sources in `raw_compress_sources` (default `mlb_api`, `statcast`) that do not write a response log, `RawStore.put` MUST store json, csv and other text raw files as `<name>.gz`, record the sha256 and byte count of the original bytes plus `stored: gzip`, never leave both forms of one file, and leave files whose name already ends in `.gz`, binary files and other sources unchanged. A source that writes a response log MUST store new raw bytes only in raw segments; its existing gzip files MUST stay readable until the converter has moved them. `exists`, `get`, `verify`, the cache check and the Statcast game feed MUST work with either form. `baseballpy compress-raw` MUST convert existing files only after the file matches its recorded checksum and its compressed copy reads back equal, leave any other file as it is and report it, and do nothing on a rerun.

#### Scenario: New files, conversion and checks
- **WHEN** raw files are written, refreshed, converted, damaged and checked
- **THEN** the checksum is the original's, readers get the original bytes, a damaged file is left alone and reported, the command and a rerun behave as stated, and a file the caller already gzipped is kept and verified as it came
- Verified by `tests/test_raw_compress.py::test_a_new_raw_file_is_gzipped_but_keeps_the_checksum_of_the_original`, `tests/test_raw_compress.py::test_other_sources_and_already_packed_files_are_stored_as_they_came`, `tests/test_raw_compress.py::test_a_refresh_never_leaves_both_forms_of_one_file`, `tests/test_raw_compress.py::test_conversion_keeps_every_byte_and_checksum_and_a_rerun_does_nothing`, `tests/test_raw_compress.py::test_a_file_that_does_not_match_its_checksum_is_left_alone`, `tests/test_raw_compress.py::test_the_compress_raw_command` and `tests/test_raw_compress.py::test_a_file_the_caller_already_gzipped_is_checked_and_read_as_it_came`.

#### Scenario: A source on segments writes no gzip file
- **WHEN** a source that writes a response log downloads a game
- **THEN** its raw bytes are in a raw segment and no new `.gz` raw file appears
- Verified by `tests/test_response_log.py::test_a_source_on_segments_writes_no_per_dataset_or_gzip_raw_file`.

## ADDED Requirements

### Requirement: Committed Segments Are Readable At Once
DuckDB views and `baseballpy.read` MUST read a dataset's `seg-*.parquet` files beside its `part-*` and `compact-*` files, MUST show a segment's rows as soon as its commit line exists without a compaction step (a view that already exists MUST NOT need a new `db sync` to show it), and MUST NOT read files in `_open/` or `_legacy/` folders or files ending in `.part`. For a season-split dataset they MUST read only the files directly inside each `season=YYYY/` folder.

#### Scenario: Visible at commit, hidden while open
- **WHEN** a segment is open, then committed, and a season also holds old part files and a `_legacy/` folder
- **THEN** the open rows are not visible, the committed rows are visible through `read` and a DuckDB view at once, old part rows and segment rows are read together, and `_legacy/` rows are not read
- Verified by `tests/test_segment_views.py::test_views_and_read_see_a_segment_as_soon_as_it_commits`, `tests/test_segment_views.py::test_open_and_legacy_folders_are_never_read` and `tests/test_segment_views.py::test_old_part_files_and_segments_are_read_together`.

#### Scenario: End to end
- **WHEN** a fake source downloads a few units through the response log
- **THEN** right after the run the rows are returned by `baseballpy.read` and by a DuckDB view with no compaction step, and a view that already existed shows a later segment without a new sync
- Verified by `tests/test_segments_e2e.py::test_a_fake_download_is_readable_through_read_and_duckdb_at_once`.

### Requirement: Sources That Write Segments Are Not Compacted By The Queue
The download queue MUST NOT run its compaction step for a source that writes segments, and that source's per-unit path MUST NOT write `part-*` files. `baseballpy compact` MUST still merge `part-*` files of the other sources.

#### Scenario: No part files, no compaction
- **WHEN** the per-game MLB path runs on segments and the queue finishes its stage
- **THEN** no `part-*` file is written and the queue starts no compaction for that source
- Verified by `tests/test_mlb_segments.py::test_the_per_game_path_writes_no_part_files` and `tests/test_queue.py::test_the_queue_does_not_compact_sources_that_write_segments`.
