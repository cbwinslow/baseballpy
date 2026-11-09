## MODIFIED Requirements

### Requirement: Four-Tier Local Layout
All persisted data MUST live under `$BASEBALLPY_HOME` (default `.baseballpy/` in the nearest project folder, else `~/.baseballpy/`; ADR 62) in `raw/`, `processed/`, `quarantine/`, `cache/http/`, `databases/` and `logs/`, with a `VERSION` file holding the layout version (2). Datasets MUST live only in `raw/` and `processed/`: `raw/<source>/<dataset>/[season=YYYY/]` holds immutable upstream bytes and `processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet` holds typed Parquet, one dataset per directory. A source that writes a response log (ADR 95) MUST instead keep its raw bytes once per response in `raw/<source>/[season=YYYY/]seg-<NNNN>.parquet` with that folder's `segments.json`, and its typed rows in `processed/<source>/<dataset>/[season=YYYY/]seg-<NNNN>.parquet`; files being written MUST stay in an `_open/` folder with names ending in `.part`. Path helpers MUST NOT create directories; writers create them on write. Locations are configurable with `BASEBALLPY_HOME` and the per-tier `BASEBALLPY_*_OVERRIDE` settings of `LakeConfig`.

#### Scenario: The default data folder lives in the project
- **GIVEN** `BASEBALLPY_HOME` is not set and the working directory is inside a folder with `pyproject.toml` or `.git`
- **THEN** the data folder is `.baseballpy/` in the nearest such folder, and outside any project it is `~/.baseballpy/`
- **AND** `BASEBALLPY_HOME` still wins when set.
- Verified by `tests/test_default_home.py::test_default_is_dot_baseballpy_in_the_nearest_project_folder`, `tests/test_default_home.py::test_outside_any_project_the_home_folder_is_used` and `tests/test_default_home.py::test_environment_variables_still_win`.

#### Scenario: Cache deletion is safe
- **GIVEN** a populated lake
- **WHEN** `cache/` is deleted
- **THEN** no dataset is lost and all DuckDB views still resolve.
- Verified by `tests/test_database.py::test_deleting_the_cache_loses_no_dataset_and_every_view_still_resolves`.

#### Scenario: Datasets do not share partitions
- **GIVEN** Retrosheet regular-season and postseason events for 2023
- **THEN** they are stored in `processed/retrosheet/events/season=2023/` and `processed/retrosheet/events_postseason/season=2023/` respectively
- **AND** `SELECT count(*) FROM retrosheet_events` equals the regular-season row count only.
- Verified by `tests/test_database.py::test_events_and_postseason_are_separate_views` and `tests/test_lake.py::test_regular_and_postseason_events_are_distinct_datasets`.

#### Scenario: Path helpers are read-only
- **WHEN** `LakeConfig.raw_dir(...)`/`processed_dir(...)` are evaluated on an empty home
- **THEN** no directory is created.
- Verified by `tests/test_config.py::test_lake_config_never_creates_directories_on_read`.

#### Scenario: A segment writes one file per dataset
- **WHEN** a segment of several games that feed several datasets is committed
- **THEN** there is one raw `seg-<NNNN>.parquet` for the source and season and one `seg-<NNNN>.parquet` per dataset that has rows, and no `.part` file is left outside `_open/`
- Verified by `tests/test_segments.py::test_a_segment_writes_one_file_per_dataset_in_bounded_row_groups`.

## ADDED Requirements

### Requirement: Each Response Is Stored Once
A source that writes a response log MUST fetch and parse each URL of a unit of work (for example a game) once and feed every dataset the registry says comes from it. The response MUST be stored once, as one raw-segment row (`url`, `fetched_at`, `status`, `etag`, sha256 of the original bytes, zstd body), and the source MUST NOT write per-dataset raw copies or new gzip raw files.

#### Scenario: One response, many datasets
- **WHEN** a game whose live feed feeds four datasets and whose boxscore feeds six is downloaded
- **THEN** each URL is requested once and parsed once, each response is one raw row whose sha256 is that of the original bytes, reading the row gives back the original bytes, and no per-dataset or gzip raw file is written
- Verified by `tests/test_response_log.py::test_each_response_is_stored_once_with_the_sha256_of_its_original_bytes`, `tests/test_response_log.py::test_a_source_on_segments_writes_no_per_dataset_or_gzip_raw_file` and `tests/test_mlb_segments.py::test_each_game_url_is_fetched_and_parsed_once_for_all_its_datasets`.

#### Scenario: Same rows as before
- **WHEN** the same fixture games are stored through segments and through the old per-game path
- **THEN** every dataset has the same rows
- Verified by `tests/test_mlb_segments.py::test_segment_rows_equal_the_old_per_game_rows`.

### Requirement: A Crash Journal Keeps Finished Responses
Every stored response MUST first be appended to `raw/<source>/[season=YYYY/]_open/journal.zst` as one compressed, length-prefixed record, flushed after each unit of work. After a crash or restart the journal MUST be replayed so no finished unit is fetched again, a torn last record MUST be dropped (its unit is fetched again), and the journal MUST be deleted only after the segment that holds its responses is committed.

#### Scenario: Restart after a crash
- **WHEN** a run is killed after some games of an open segment, and started again
- **THEN** the finished games are not requested again and the committed segment holds every game once
- Verified by `tests/test_response_log.py::test_a_crash_replays_the_journal_and_refetches_no_finished_game`.

#### Scenario: Torn journal record
- **WHEN** the last journal record is cut short
- **THEN** replay keeps every whole record, drops the torn one and fetches that game again
- Verified by `tests/test_response_log.py::test_a_torn_last_journal_record_is_dropped`.

### Requirement: Segments Are Written In Bounded Row Groups And Name Their Response
An open segment MUST close after a configured number of units or a configured time (defaults 250 games and 10 minutes, to be measured). Each processed segment file MUST be written one row group at a time (default about 50 games per row group) so that no more than one row group of rows per dataset is held in memory, and every processed row MUST carry `_raw_sha256`, the sha256 of the response it was made from. Adding `_raw_sha256` MUST NOT make chunks stored before it existed stale.

#### Scenario: Row groups and lineage
- **WHEN** a segment of 120 games is written with 50 games per row group
- **THEN** each dataset file has three row groups, and every row's `_raw_sha256` names a row of the raw segment
- Verified by `tests/test_segments.py::test_a_segment_writes_one_file_per_dataset_in_bounded_row_groups` and `tests/test_segments.py::test_every_processed_row_names_its_response`.

### Requirement: A Segment Counts Only When Its Commit Line Exists
A segment MUST be committed by renaming its files from `_open/` into place (with the existing Windows retry) and then appending one JSON line to the season's `segments.json` (segment id, unit ids, sha256 and row count per file, schema fingerprint per dataset). A unit MUST count as stored only when a line names it; a torn last line MUST be ignored. On start, files no line names MUST be deleted and the journal replayed.

#### Scenario: Commit, crash before the line, torn line
- **WHEN** a segment's files are renamed but the run stops before its line is written, and another run finds a torn last line
- **THEN** the games of that segment are not counted, the start-up deletes the unnamed files and replays the journal, and the torn line is ignored
- Verified by `tests/test_segments.py::test_a_game_counts_only_after_its_commit_line`, `tests/test_segments.py::test_start_up_deletes_uncommitted_files_and_replays_the_journal` and `tests/test_segments.py::test_a_torn_commit_line_is_ignored`.

### Requirement: One Writer Per Source And Season
Only one process MUST write the segments of one source and season at a time; downloads, the converter, the rebuild and the round-trip check MUST take the existing host lock, and a second writer MUST be refused with a message that names the source and season being written (the lock file does not record the process that holds it).

#### Scenario: Second writer
- **WHEN** a second writer starts on a season that is being written
- **THEN** it is refused and the first writer's files are untouched
- Verified by `tests/test_segments.py::test_a_second_writer_on_the_same_season_is_refused`.

### Requirement: A Refreshed Segment Replaces Its File Under The Same Name
Rewriting a committed segment MUST write the new files in `_open/` and rename each over the old file of the same name, so a reader sees the old rows or the new rows of that segment and never both; its journal MUST stay until the new commit line is written, and an unfinished refresh MUST be run again on start.

#### Scenario: Refresh and crash during refresh
- **WHEN** a committed segment is refreshed, and a second refresh is stopped after one of its renames
- **THEN** each dataset has one file for the segment, row counts never include both versions, and the next start finishes the stopped refresh
- Verified by `tests/test_segments.py::test_a_refresh_replaces_a_segment_under_the_same_name`.

### Requirement: Cache Check Verifies Segments
`baseballpy cache check` MUST verify every committed segment file against the sha256 in its commit line and every raw row's body against its own sha256, and report a missing or damaged one with exit code 1.

#### Scenario: Damaged segment
- **WHEN** a raw segment file is changed on disk after its commit
- **THEN** the check names the file and exits 1, and a clean lake exits 0
- Verified by `tests/test_segments.py::test_cache_check_finds_a_damaged_segment`.

### Requirement: Old Raw Files Are Converted Without Losing A Byte
A converter MUST turn a source's existing raw files into raw segments: check each file against its old manifest sha256, keep every distinct body as one row with its old path, read every row back, and remove a season's old files only after the whole season verified. A file that does not match MUST stay and be reported. `--dry-run` MUST change nothing and report files, copies, distinct bodies and bytes saved per season; a rerun MUST change nothing.

#### Scenario: Dry run, distinct bodies, verify first, rerun
- **WHEN** a season with four copies of most feeds, two different bodies for one feed and one damaged file is converted, first as a dry run and then for real, twice
- **THEN** the dry run changes nothing, both different bodies are kept, the damaged file stays and is reported, old copies go only after the season verified, and the rerun changes nothing
- Verified by `tests/test_raw_convert.py::test_the_dry_run_reports_and_changes_nothing`, `tests/test_raw_convert.py::test_every_sha256_is_checked_against_the_old_manifest`, `tests/test_raw_convert.py::test_distinct_bodies_are_all_kept`, `tests/test_raw_convert.py::test_copies_are_removed_only_after_the_whole_season_verifies` and `tests/test_raw_convert.py::test_a_rerun_changes_nothing`.

### Requirement: Processed Segments Are Rebuilt From Raw
A rebuild MUST make the processed segments of a season from its raw segments with the current normalizer, without network access; a segment whose recorded schema fingerprint differs from the dataset's current schema MUST be rebuilt this way. When a season's old `part-*`/`compact-*` files are replaced, they MUST first be moved to `_legacy/` and deleted only after the row counts and keys of the new segments equal theirs.

#### Scenario: Rebuild, schema change and replacing old files
- **WHEN** a season is rebuilt from raw, a schema gains a column and the season is rebuilt again, and a season with old files is migrated
- **THEN** the rows equal the old rows, the new column is filled from raw, and at no time does a reader see a row twice
- Verified by `tests/test_segment_rebuild.py::test_a_season_is_rebuilt_from_raw_with_the_same_rows`, `tests/test_segment_rebuild.py::test_a_schema_change_is_applied_by_rebuilding_from_raw` and `tests/test_segment_rebuild.py::test_old_files_are_hidden_before_segments_appear`.

### Requirement: Raw Leaves The Laptop Only After A Round-Trip Check
A round-trip check MUST rebuild each response of a segment from its processed rows and compare it with the raw response, and fail when any raw value is not found in the processed rows. Raw segments MAY be moved to another place only after their check passed; they MUST be moved, never deleted, and the commit line MUST record the new location so readers and the cache check find them.

#### Scenario: Check and move
- **WHEN** a segment whose processed rows hold every value is checked, a segment with an untyped value is checked, and the first is moved
- **THEN** the first passes, the second fails and cannot be moved, and after the move the raw rows are found at the recorded place and nothing was deleted
- Verified by `tests/test_raw_roundtrip.py::test_a_segment_passes_when_processed_rows_hold_every_value`, `tests/test_raw_roundtrip.py::test_an_untyped_value_fails_the_check` and `tests/test_raw_roundtrip.py::test_raw_is_moved_never_deleted_and_the_new_place_is_recorded`.

### Requirement: Every Source Uses Segments Through The Registry
The response log and segment writer MUST be one generic mechanism behind `SinkProtocol` that any `IngestAdapter` uses by declaring, in the registry, which datasets come from which response; the mechanism MUST NOT contain source-specific code, and the import boundaries of `tests/test_architecture.py` MUST hold.

#### Scenario: A fake source
- **WHEN** a fake source declares its responses and datasets in the registry and runs
- **THEN** it writes raw and processed segments with no code of its own in the mechanism, and the architecture test passes
- Verified by `tests/test_segment_sources.py::test_a_fake_source_uses_segments_through_the_registry_only`.
