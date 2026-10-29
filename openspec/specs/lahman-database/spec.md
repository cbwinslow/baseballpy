# lahman-database Specification

## Purpose
Defines the ingestion, schema coercion, dual-mode acquisition, and local storage specifications for the SABR Sean Lahman Baseball Database (1871–2025).

## Requirements

### Requirement: Dual-Mode Ingestion (Automated Mirror + Manual SABR Box Import)
The system MUST support two complementary paths to acquire the complete 27-table Lahman database:
1. **Mode A (Automated Extraction):** Direct download from the up-to-date public GitHub mirror `cbwinslow/lahman-database-csv/main/data/` with two-phase atomic write gates (`.part`), token-bucket rate limiting, and manifest tracking.
2. **Mode B (Manual Local Import):** User provides local path to official `.zip` or unzipped folder downloaded from SABR Box via `lahman.import_archive(path)`. The system validates CSV headers, copies to `raw/lahman/<Table>/<Table>.csv`, and compiles to Parquet at `processed/lahman/<Table>/part-data.parquet`.

#### Scenario: Remote download and local import
- **WHEN** a table is fetched from the remote mirror, or `import_archive` is given a local zip
- **THEN** the raw CSV, the processed `part-data.parquet` and a completed manifest entry exist; the archive import records all 27 tables as `local-import` and contacts no network
- Verified by `tests/test_lahman.py::test_lahman_extractor_and_caching and tests/test_lahman_coverage.py::test_import_archive_imports_all_27_as_local_import_and_never_hits_the_network`.

### Requirement: Strongly-Typed Parquet Compilation
All 27 tables MUST be parsed and saved as strongly-typed Parquet at `processed/lahman/<Table>/part-data.parquet` (raw CSVs at `raw/lahman/<Table>/<Table>.csv`); each table is a separate dataset with view `lahman_<table_lower>`.
Specific canonical schemas MUST be enforced for:
- `People`: `birthYear`, `birthMonth`, `birthDay`, `debut` (as `date32`), `finalGame` (as `date32`), `retroID`, `bbrefID`.
- `Batting`: `playerID`, `yearID`, `stint`, `teamID`, `lgID`, `G`, `AB`, `R`, `H`, `2B`, `3B`, `HR`, `RBI`, `SB`, `CS`, `BB`, `SO`.
- `Pitching`: `playerID`, `yearID`, `W`, `L`, `ERA`, `IPouts`, `SO`, `BB`, `CG`, `SHO`, `SV`.
- `Teams`: `yearID`, `teamID`, `franchID`, `divID`, `Rank`, `W`, `L`, `R`, `RA`, `ERA`, `FP`, `attendance`, `BPF`, `PPF`.
- `Fielding`: `playerID`, `yearID`, `POS`, `G`, `GS`, `InnOuts`, `PO`, `A`, `E`, `DP`, `PB`, `ZR`.
- `Salaries`: `yearID`, `teamID`, `lgID`, `playerID`, `salary`.
- `HallOfFame`: `playerID`, `yearid`, `votedBy`, `ballots`, `needed`, `votes`, `inducted`.
- `AllstarFull`: `playerID`, `yearID`, `gameID`, `teamID`, `GP`, `startingPos`.

#### Scenario: Every table has a strict schema and key
- **WHEN** the 27 tables are compiled
- **THEN** each has an explicit schema and a primary key verified unique, and a fixture normalizes to the exact schema without loss
- Verified by `tests/test_lahman_coverage.py::test_every_one_of_the_27_tables_has_a_strict_schema_and_key and ::test_fixture_normalizes_to_the_exact_schema_without_loss`.

### Requirement: Type-Safe Enums
The system MUST provide a `LahmanTable` StrEnum cataloging all 27 tables.

#### Scenario: LahmanTable lists the tables
- **WHEN** `LahmanTable` is inspected
- **THEN** it is a `StrEnum` with one member per Lahman table
- Verified by `tests/test_enums.py::test_lahman_table_enum`.

### Requirement: Strict Schemas for All 27 Tables
Every Lahman table MUST have an explicit PyArrow schema generated from the real upstream header (`scripts/gen_schemas.py lahman`), a documented primary key verified unique on the full data, name-based column mapping, and `_extras` preservation of unknown columns.

#### Scenario: New upstream column
- **WHEN** a release adds a column `foo` to `Batting.csv`
- **THEN** ingestion succeeds, `foo` is stored in `_extras`, and a drift warning is logged.
- Verified by `tests/test_lahman_coverage.py::test_extra_and_missing_columns_never_drop_data` and `tests/test_sources_hardening.py::test_lahman_normalizer_preserves_unknown_columns_and_quarantines_bad_cells`.

### Requirement: Permitted Sources Only
Lahman data MUST come only from the configured remote repo (default `cbwinslow/lahman-database-csv`, pinned ref) or from user-supplied data via `import_archive`. `chadwickbureau/baseballdatabank` MUST NOT be used, and there is no automatic fallback to any other repository. The manifest MUST record the source (`<repo>@<sha>` or `local-import`) per table.

#### Scenario: Remote unavailable
- **WHEN** the configured remote returns 404/5xx after retries
- **THEN** an error is raised that names `import_archive` as the alternative
- **AND** no other repository is contacted.
- Verified by `tests/test_lahman_coverage.py::test_remote_failure_names_import_archive_and_contacts_no_other_repo`.

#### Scenario: Stale data warning
- **WHEN** the newest `yearID` in `Batting` is more than one season behind the last completed MLB season
- **THEN** a warning is logged and kept in the processed manifest.
- Verified by `tests/test_lahman_coverage.py::test_import_flags_stale_data_in_the_manifest and ::test_quality_checks_report_duplicates_orphans_and_stale_data`.

### Requirement: Safe Archive Import
`import_archive` MUST reject zip members containing path traversal and members or archives beyond the size limits, and MUST write raw files atomically.

#### Scenario: Traversal and oversized members are rejected
- **WHEN** a zip holds a path-traversal member or a member over the size limit
- **THEN** `import_archive` rejects it and writes nothing
- Verified by `tests/test_lahman_coverage.py::test_import_archive_rejects_path_traversal and ::test_import_archive_rejects_oversized_members`.

### Requirement: Currency and Fingerprints at Both Cache Tiers
Every raw Lahman file MUST have exactly one manifest entry holding its sha256, size, data-row count, origin, the commit it came from and the provider's git blob fingerprint, and whether a cached copy can be served MUST be decided by the shared `is_current()` at the raw tier (stored fingerprint against the blob the pinned tree lists, the pinned commit when no tree is available) and at the processed tier (the Parquet is current only when it was built from the raw file held), so moving the pin refetches and rebuilds exactly the files whose blob changed.

#### Scenario: One entry per file with a git fingerprint, remembered by the Parquet
- **WHEN** a table is fetched from the mirror
- **THEN** `raw/lahman/<Table>/manifest.json` has only the `<Table>.csv` entry with `upstream` kind `git_blob`, the exact data-row count and `source_ref`, and the processed manifest holds the same fingerprint
- Verified by `tests/test_lahman_workflow.py::test_fingerprints_one_entry_per_file_and_documents_are_kept`.

#### Scenario: A pinned lake needs no request, even offline
- **WHEN** a fresh process asks for a cached table, with the tree listing saved or deleted and the network failing
- **THEN** both tiers are served without a request for the file, with a warning when the tree could not be listed
- Verified by `tests/test_lahman_workflow.py::test_a_second_process_serves_both_tiers_without_any_request` and `tests/test_lahman_workflow.py::test_offline_without_a_cached_listing_the_pinned_commit_decides`.

#### Scenario: Moving the pin
- **WHEN** the pinned ref changes to a commit where a table's blob differs, and to one where it is unchanged
- **THEN** the changed table is downloaded again and its Parquet rebuilt; the unchanged table is not downloaded
- Verified by `tests/test_lahman_workflow.py::test_moving_the_pin_refetches_the_raw_file_and_rebuilds_the_parquet` and `tests/test_lahman_workflow.py::test_an_unchanged_blob_under_a_new_pin_is_not_downloaded_again`.

#### Scenario: Cache hits are reported
- **WHEN** an ingest job is served from the cache
- **THEN** the job result and the audit event say `cache_hit`
- Verified by `tests/test_lahman_workflow.py::test_ingest_jobs_report_cache_hits`.

### Requirement: Provider Documentation Is Kept
The mirror's `README.md`, `LICENSE` and data dictionary (`data/readme*.txt`) MUST be kept in `raw/lahman/documents/` with their hashes and git fingerprints, a cached run MUST NOT download them again, and `docs/DATA_LICENSES.md` MUST name the licence (CC BY-SA 3.0), the attribution and the ShareAlike consequence.

#### Scenario: Documents kept and licence stated
- **WHEN** a table is fetched, and the licence documentation is read
- **THEN** the three files are in `raw/lahman/documents/` verifiable by sha256, and the licence page names CC BY-SA 3.0 and the same-licence term
- Verified by `tests/test_lahman_workflow.py::test_fingerprints_one_entry_per_file_and_documents_are_kept` and `tests/test_lahman_workflow.py::test_the_licence_documentation_names_cc_by_sa_and_the_share_alike_term`.

### Requirement: Supplied Releases Are Kept Whole and Never Mixed Silently
`import_archive` MUST keep the release's README, licence and data dictionary in `raw/lahman/documents/`, keep a CSV that is not one of the 27 tables as raw bytes only with a warning (never as an unregistered table), ignore other file types, give supplied files a content fingerprint and treat them as authoritative until refreshed, and MUST warn once when a table is fetched from the mirror while other tables came from a supplied archive.

#### Scenario: Import contents
- **WHEN** an archive with tables, a data dictionary, a licence, an unknown CSV and other files is imported
- **THEN** the tables are typed, the documents kept, the unknown CSV kept raw only with a warning, and the tables are served without network
- Verified by `tests/test_lahman_workflow.py::test_import_keeps_documents_and_unknown_csvs_raw_only_and_ignores_the_rest`.

#### Scenario: Mixed release warning
- **WHEN** a partial supplied release is completed from the mirror
- **THEN** one warning names the supplied tables
- Verified by `tests/test_lahman_workflow.py::test_mixing_a_supplied_table_with_a_mirror_table_warns_once`.

### Requirement: Complete Python Access
Every one of the 27 tables MUST be readable with `lahman.table(name)`, names MUST ignore letter case, the registry, the `LahmanTable` enum and the generated tables MUST name the same 27 tables, and a table MUST be read once per process and reused until its Parquet changes.

#### Scenario: One call, any case, one list of names
- **WHEN** tables are requested by name in different letter cases and the name lists are compared
- **THEN** each resolves to the canonical table, an unknown name lists the 27 known ones, and the three lists are equal
- Verified by `tests/test_lahman_workflow.py::test_table_names_ignore_letter_case_and_unknown_names_list_the_27`, `tests/test_lahman_workflow.py::test_enum_registry_and_generated_tables_name_the_same_27_tables` and `tests/test_lahman_workflow.py::test_generic_top_level_accessor_serves_every_table`.

#### Scenario: Repeated reads are free
- **WHEN** the same table is read repeatedly, then its Parquet is rewritten
- **THEN** the same object is returned until the rewrite, after which it is read again
- Verified by `tests/test_lahman_workflow.py::test_tables_are_remembered_in_process_and_noticed_when_the_parquet_changes`.

### Requirement: Data Quality Across Tables Independent of Load Order
The relationships between tables (`playerID` in `People`, `yearID`+`teamID` in `Teams`, `Teams.franchID` in `TeamsFranchises`, `HomeGames.parkkey` in `Parks`, `CollegePlaying.schoolID` in `Schools`) MUST be checked by one generic function whenever a table is stored and again for its children when a parent is stored later, rows with an empty id MUST NOT count as orphans, and the findings MUST be kept in the processed manifest and printed by `baseballpy catalog status`.

#### Scenario: Order does not matter
- **WHEN** `Batting` is stored before `People` and `Teams`, then the parents arrive, grow, and complete
- **THEN** the findings appear when the parent arrives and disappear when the parent covers the rows
- Verified by `tests/test_lahman_workflow.py::test_findings_do_not_depend_on_the_order_tables_are_stored_in`.

#### Scenario: Findings are visible and exact
- **WHEN** a child table has an empty id, an unknown id, a duplicate key and stale data
- **THEN** only the unknown id counts as an orphan, the other findings are reported, and `catalog status` prints them
- Verified by `tests/test_lahman_workflow.py::test_empty_ids_are_not_orphans_and_other_relationships_are_checked`, `tests/test_lahman_coverage.py::test_quality_checks_report_duplicates_orphans_and_stale_data` and `tests/test_lahman_workflow.py::test_catalog_status_shows_the_findings`.
