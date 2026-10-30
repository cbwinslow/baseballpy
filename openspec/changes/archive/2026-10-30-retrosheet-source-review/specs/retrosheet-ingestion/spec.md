## ADDED Requirements

### Requirement: Lake Layout
Raw files MUST be stored under `raw/retrosheet/<raw dataset>/[season=YYYY/]` (`event_files`, `box_files`, `rosters`, `gamelogs`, `gamelogs_postseason`, `schedule`, `schedule_original`, `umpires`, `discrepancies`, `reference_<name>`, `documents`) and parsed output under `processed/retrosheet/<dataset>/[season=YYYY/]part-<chunk>.parquet`.

#### Scenario: Every file kind lands in its raw directory
- **WHEN** a full season is downloaded
- **THEN** each file kind is stored in its raw directory with its sha256 and pinned ref recorded
- Verified by `tests/test_retrosheet_coverage.py::test_download_season_fetches_all_kinds_records_sha256_and_resumes`.

### Requirement: Typed Columns, Quarantine and No Silent Loss
Counts MUST be integers, flags booleans and dates `date32` (partial dates stay text). A value or row that cannot be read MUST be quarantined with its raw text and counted in the report, never dropped silently; fields beyond the schema MUST be kept in `_extras`.

#### Scenario: Bad values are quarantined, drift goes to extras
- **WHEN** a file holds an uncastable integer, an unparseable date or an unknown column
- **THEN** the value is quarantined and the unknown column is kept in `_extras`
- Verified by `tests/test_sources_hardening.py::test_retrosheet_parser_quarantines_uncoercible_ints, tests/test_retrosheet_coverage.py::test_unparseable_dates_are_quarantined_not_silently_dropped and ::test_reference_header_drift_goes_to_extras_and_dates_are_typed`.

#### Scenario: Short and long flat-file rows
- **WHEN** a game-log row has too few fields, a game-log row has more than 161 fields, or a roster row has more than 7 fields
- **THEN** the short row is quarantined and counted, and the extra fields are kept in `_extras`
- Verified by `tests/test_retrosheet_rows.py::test_short_gamelog_rows_are_quarantined_and_extra_fields_kept` (written by task 5.8).

### Requirement: Pin Moves Invalidate Season Chunks
A season chunk recorded at a different pinned ref MUST NOT be served as complete; entries without a ref are trusted.

#### Scenario: Ref change
- **WHEN** the pinned ref changes
- **THEN** the season chunk is checked again
- Verified by `tests/test_sources_lock.py::test_retrosheet_season_chunk_invalidated_by_ref_change_but_legacy_entry_trusted`.

### Requirement: Absent Files Are Recorded, Not Hidden
A tree-listed file answering 404 MUST be recorded `ABSENT` and retried on the next run; a download restricted to some kinds MUST NOT mark the season complete; a missing game log MUST raise.

#### Scenario: Missing and partial downloads
- **WHEN** a file answers 404, only some kinds are downloaded, or a game log is missing
- **THEN** the season is not COMPLETED and the missing log raises
- Verified by `tests/test_retrosheet_coverage.py::test_listed_but_missing_file_is_absent_never_completed_and_retried, ::test_kind_restricted_download_never_marks_the_season_complete, ::test_season_missing_from_the_tree_is_recorded_absent and ::test_missing_gamelog_raises_instead_of_returning_empty`.

### Requirement: Derived Box Scores Include Every Appearance
`boxscores_batting` and `boxscores_pitching` MUST hold one row per appearance, including substitutes and relievers.

#### Scenario: Substitutes are kept
- **WHEN** a game has substitutes and relievers
- **THEN** each has its own row
- Verified by `tests/test_retrosheet.py::test_boxscores_include_substitutes_and_relievers_not_just_starters`.

### Requirement: Upstream Currency
A raw file MUST be served only when its stored git blob SHA equals the one the pinned tree lists; a processed chunk MUST be served only when it records a fingerprint of the raw files it was built from (ADR 43, ADR 48). A pin move therefore refetches only changed files and rebuilds only their chunks.

#### Scenario: Unchanged blobs are kept, changed blobs rebuild
- **WHEN** the pin moves and one file's blob changes
- **THEN** only that file is fetched and only the chunks built from it are rebuilt
- Verified by `tests/test_retrosheet_currency.py::test_pin_move_refetches_only_changed_blobs_and_rebuilds_their_chunks` (written by tasks 5.1 and 5.2).

### Requirement: Provider Documents Kept
Repository files outside the data folders (README with the Retrosheet notice, `.gitattributes`) MUST be kept raw under `raw/retrosheet/documents/` with sha256 and fingerprint through `core/documents.py`, and files no dataset pattern covers MUST be kept raw and reported.

#### Scenario: README kept
- **WHEN** the tree lists `README.md`
- **THEN** it is stored in `raw/retrosheet/documents/`
- Verified by `tests/test_retrosheet_currency.py::test_root_documents_are_kept` (written by task 5.3).

### Requirement: Registry-Driven Selection and Access
Every registered Retrosheet dataset MUST be accepted by `--datasets` and readable through one generic `table(name, season)`. Selecting a season dataset without seasons MUST fail with an instruction. Each ingest MUST download a needed file once.

#### Scenario: Every registry name works
- **WHEN** each registered name is passed to `--datasets` and to `table()`
- **THEN** a job is planned and a typed table is returned
- Verified by `tests/test_retrosheet_selection.py::test_every_registry_dataset_is_selectable_and_readable` (written by tasks 5.5 and 5.7).

### Requirement: Full Event Fields and Unique Keys
Every field `chadwickpy` emits for an event MUST be stored as a typed column (unknown future fields in `_extras`), and every registry key MUST be unique and non-null; events, postseason events and deduced events are keyed `(GAME_ID, EVENT_ID)`.

#### Scenario: Multi-play games
- **WHEN** a game with several plays is parsed
- **THEN** every chadwickpy field is a column and no key repeats
- Verified by `tests/test_retrosheet_events.py::test_event_fields_match_chadwickpy_and_keys_are_unique` (written by task 5.6).

### Requirement: Bounded Memory
Ingest and export MUST NOT hold more than one season in memory; row counts come from the writer, not from re-reading the output.

#### Scenario: Export one season at a time
- **WHEN** a many-season dataset is exported
- **THEN** peak memory does not grow with the number of seasons
- Verified by `tests/test_export.py::test_export_holds_one_season_at_a_time` (written by task 5.11).

### Requirement: Cross-Dataset Quality Checks
Ingest MUST check key uniqueness, player ids against the Chadwick register and `box_games.game_id` against `gamelogs`, independent of load order, and report findings through `catalog status`.

#### Scenario: Orphan ids are reported
- **WHEN** a dataset holds an id that its reference dataset lacks
- **THEN** the finding is reported with a count and examples
- Verified by `tests/test_retrosheet_quality.py::test_orphan_player_ids_are_reported` (written by task 5.13).

### Requirement: Every Operation Is Audit-Logged and Timed
Every Retrosheet operation that lists the upstream tree, downloads a file, keeps provider documents, builds a dataset unit, checks data quality or ingests a season or the reference tables MUST write one structured event (operation, endpoint, destination, record count, duration, cache hit, status) to `logs/audit.jsonl`; a failure MUST be logged with status FAILURE and re-raised.

#### Scenario: A season and the reference ingest leave a trail
- **WHEN** a season and the reference tables are ingested, and the season is ingested again
- **THEN** the log holds one event per operation, and the second run's build events are cache hits with zero records
- Verified by `tests/test_retrosheet_audit.py::test_a_season_and_the_reference_ingest_leave_an_audit_trail`.

### Requirement: Missing Event Text Is NULL
A text field that cwevent reports as empty MUST be stored as NULL, like every other Retrosheet dataset, so that a CSV round trip of `events`, `events_postseason` and `events_deduced` is exact.

#### Scenario: Events survive a CSV round trip
- **WHEN** parsed events are written to CSV and read back
- **THEN** the table is equal and no text column holds an empty string
- Verified by `tests/test_retrosheet_events.py::test_missing_text_fields_are_null_not_empty_strings_and_survive_a_csv_round_trip`.

## MODIFIED Requirements

### Requirement: Box-Score Game Accounts (interim)
Every `.EB*` file MUST be parsed: `id`/`version`/`info` into `box_games` (typed, `unknown` as NULL, unknown keys in `_extras`), `start` into `box_starters`, `stat,bline` into `box_batting_lines`, and every other record (including unknown kinds and repeated `info` keys) losslessly into `box_records` with its raw line; an unexpected field count for a typed kind MUST raise `BoxParseError`. Typed datasets for the remaining kinds follow once the official layout document is available.

#### Scenario: Every line accounted for, unknown kinds kept, bad layouts raise
- **WHEN** real box accounts are parsed
- **THEN** every line is accounted for, unknown record kinds and repeated keys are preserved with their raw line, and an unexpected field count raises
- Verified by `tests/test_retrosheet_box.py::test_every_line_of_real_games_is_accounted_for, ::test_unknown_record_kind_is_preserved_not_dropped, ::test_unexpected_layouts_raise_instead_of_guessing and ::test_repeated_info_keys_are_kept`.
