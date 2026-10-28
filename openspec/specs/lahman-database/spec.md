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

### Requirement: Permitted Sources Only
Lahman data MUST come only from the configured remote repo (default `cbwinslow/lahman-database-csv`, pinned ref) or from user-supplied data via `import_archive`. `chadwickbureau/baseballdatabank` MUST NOT be used, and there is no automatic fallback to any other repository. The manifest MUST record the source (`<repo>@<sha>` or `local-import`) per table.

#### Scenario: Remote unavailable
- **WHEN** the configured remote returns 404/5xx after retries
- **THEN** an error is raised that names `import_archive` as the alternative
- **AND** no other repository is contacted.

#### Scenario: Stale data warning
- **WHEN** the newest `yearID` in `Batting` is more than one season behind the last completed MLB season
- **THEN** a warning is logged and kept in the processed manifest.

### Requirement: Safe Archive Import
`import_archive` MUST reject zip members containing path traversal and members or archives beyond the size limits, and MUST write raw files atomically.

#### Scenario: Traversal and oversized members are rejected
- **WHEN** a zip holds a path-traversal member or a member over the size limit
- **THEN** `import_archive` rejects it and writes nothing
- Verified by `tests/test_lahman_coverage.py::test_import_archive_rejects_path_traversal and ::test_import_archive_rejects_oversized_members`.
