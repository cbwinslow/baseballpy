# Tasks

Rules for every task: write the named tests first (they fail), then the code. A task is done only when the four
gates (`uv run pytest`, `uvx ruff check .`, `uvx ruff format --check .`, `uv run mypy --strict src`), `uv run
baseballpy docs generate --check` and `openspec validate --specs` are green, the evidence is in `design.md` section
7, and one commit is made. Rollback point: git tag `pre-response-log`; the old layout stays readable until group 7.

## 1. Specs, decisions, backlog
- [x] 1.1 this change: proposal, design, spec deltas, ADRs 95-97, backlog rows; the drafts `shared-raw-bytes` and `batched-chunk-writes` point here; `openspec validate response-log-segments --strict` passes; `scripts/project_map.py` regenerated; gates green
- [x] 1.2 web search for prior art (WARC, DuckLake, how pybaseball/baseballr/sportsdataverse keep raw responses) and record it in design.md section 5
- [x] 1.3 find out why 177 of about 83,000 2024 feed files differ between the 4 datasets (which bytes differ, fetch times) and record it in design.md before group 5

## 2. Response log: journal and raw segment writer
- [x] 2.1 tests first: `tests/test_response_log.py::test_each_response_is_stored_once_with_the_sha256_of_its_original_bytes`, `::test_a_crash_replays_the_journal_and_refetches_no_finished_game`, `::test_a_torn_last_journal_record_is_dropped`, `::test_a_source_on_segments_writes_no_per_dataset_or_gzip_raw_file`
- [x] 2.2 journal writer and reader in `baseballpy/core/responselog.py` (the interface is fixed by the docstring of `tests/test_response_log.py`; remove the `xfail` marks of the tests it makes pass) (one zstd frame per record with `pyarrow.Codec`, length prefix, flushed per game)
- [x] 2.3 raw segment writer behind `SinkProtocol` (Parquet, zstd, large data pages)
- [x] 2.4 measure on 2024 samples: zstd level 9 against 19 and the page size (bytes and write seconds); replace the guessed numbers in design.md section 3

## 3. Processed segments and the commit protocol
- [x] 3.1 tests first: `tests/test_segments.py::test_a_segment_writes_one_file_per_dataset_in_bounded_row_groups`, `::test_every_processed_row_names_its_response`, `::test_a_game_counts_only_after_its_commit_line`, `::test_start_up_deletes_uncommitted_files_and_replays_the_journal`, `::test_a_torn_commit_line_is_ignored`, `::test_a_second_writer_on_the_same_season_is_refused`, `::test_a_refresh_replaces_a_segment_under_the_same_name`
- [x] 3.2 processed segment writer in `baseballpy/core/segments.py` (the interface is fixed by the docstring of `tests/test_segments.py`; remove the `xfail` marks of the tests it makes pass): `ParquetWriter`, row groups of about 50 games, `_raw_sha256`, `.part` names in `_open/`
- [x] 3.3 commit: renames with the existing retry, one line appended to `segments.json`, start-up clean-up and journal replay
- [x] 3.4 refresh of a committed segment (same name, open refresh run again on start)
- [x] 3.5 one writer per source and season through `core/hostlock.py`
- [x] 3.6 `baseballpy cache check` verifies segment files and response sha256s from `segments.json`; test `tests/test_segments.py::test_cache_check_finds_a_damaged_segment`
- [x] 3.7 add `_raw_sha256` without making old chunks stale (left out of the schema digest; old files read it as empty); ADR amendment if built another way

## 4. MLB per-game path on segments
- [x] 4.1 tests first: `tests/test_mlb_segments.py::test_each_game_url_is_fetched_and_parsed_once_for_all_its_datasets`, `::test_segment_rows_equal_the_old_per_game_rows`; `tests/test_segment_views.py::test_views_and_read_see_a_segment_as_soon_as_it_commits`, `::test_open_and_legacy_folders_are_never_read`, `tests/test_mlb_segments.py::test_an_empty_or_failed_response_never_marks_a_game_complete` (pybaseball's cache keeps empty results for future dates), `::test_old_part_files_and_segments_are_read_together`
- [x] 4.2 `baseballpy/sources/mlb_api/game_segments.py` (interface fixed by the docstring of `tests/test_mlb_segments.py`; remove its `xfail` marks): `game_url_groups()` from the endpoint registry (same path = same URL), `decode_body`, `ingest_game_segments`; the per-game path writes through the response log and segments (built; reached through `--option storage=segments` of the mlb_api games job, off by default until task 4.4 has measured a real season and the default is switched)
- [x] 4.3 views and `read` list `season=*/*.parquet` (segments beside `part-*` and `compact-*`, never `_open/` or `_legacy/`); a segment file is not reported as "differs from the registered schema" (the lineage column is expected); empty `_open/` folders are removed after a commit; remove the `xfail` marks of `tests/test_segment_views.py`
- [x] 4.4 run one real season: peak memory, seconds per game, files per dataset; adjust 250 games / 10 minutes / 50 per row group; record in design.md

## 5. Converter for the existing raw files
- [x] 5.1 tests first: `tests/test_raw_convert.py::test_the_dry_run_reports_and_changes_nothing`, `::test_every_sha256_is_checked_against_the_old_manifest`, `::test_distinct_bodies_are_all_kept`, `::test_copies_are_removed_only_after_the_whole_season_verifies`, `::test_a_rerun_changes_nothing`
- [x] 5.2 converter command with `--dry-run` (per season: files, copies, distinct bodies, bytes to save)
- [x] 5.3 real conversion: read back every row, then remove the old copies of that season
- [ ] 5.4 dry run on the real lake, then the real run season by season; disk before and after in design.md (replaces the guessed raw size)

## 6. Rebuild processed segments from raw
- [ ] 6.1 tests first: `tests/test_segment_rebuild.py::test_a_season_is_rebuilt_from_raw_with_the_same_rows`, `::test_a_schema_change_is_applied_by_rebuilding_from_raw`, `::test_old_files_are_hidden_before_segments_appear`, `::test_a_url_with_two_stored_versions_is_rebuilt_from_the_newest_for_every_dataset` (design 5b)
- [ ] 6.2 generic rebuild of a season's segments from its raw rows with the current normalizer (also the schema-change path, ADR 87)
- [ ] 6.3 per season: old files to `_legacy/`, segments in, row counts and keys compared with the old files; table in design.md
- [ ] 6.4 delete `_legacy/` of a season only after its comparison passed

## 7. Remove the old per-game path
- [ ] 7.1 tests first: `tests/test_mlb_segments.py::test_the_per_game_path_writes_no_part_files`, `tests/test_queue.py::test_the_queue_does_not_compact_sources_that_write_segments`
- [ ] 7.2 remove the per-game `part-*` writes and the queue's compaction step for sources that write segments; `compact` stays for part files
- [ ] 7.3 `catalog layout` treats segment files as normal (no TINY_FILES for them); docs (`docs/sources/mlb_api.md`, README, CLI docs) updated

## 8. Round-trip check and moving raw
- [ ] 8.1 tests first: `tests/test_raw_roundtrip.py::test_a_segment_passes_when_processed_rows_hold_every_value`, `::test_an_untyped_value_fails_the_check`, `::test_raw_is_moved_never_deleted_and_the_new_place_is_recorded`
- [ ] 8.2 round-trip check per segment (rebuild each response from processed rows, compare with the raw response)
- [ ] 8.3 optional move-raw command (only segments that passed; moved, never deleted; location in `segments.json`); not run on the real lake while the owner keeps all raw

## 9. The other sources
- [ ] 9.1 tests first: `tests/test_segment_sources.py::test_a_fake_source_uses_segments_through_the_registry_only`; `tests/test_architecture.py` still passes
- [ ] 9.2 one generic function plus the registry field (which datasets come from which response); no per-source special case
- [ ] 9.3 Statcast on segments
- [ ] 9.4 Retrosheet on segments
- [ ] 9.5 Lahman, Chadwick, Kalshi, Polymarket, FanGraphs, Baseball-Reference on segments, or a recorded reason per source

## 10. End to end and closing
- [ ] 10.1 tests first: `tests/test_segments_e2e.py::test_a_fake_download_is_readable_through_read_and_duckdb_at_once`
- [ ] 10.2 merge the spec deltas, archive this change (the two superseded drafts were archived by backlog-consolidation)
