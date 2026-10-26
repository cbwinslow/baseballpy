# lahman-database Specification

## Purpose
Defines the ingestion, schema coercion, dual-mode acquisition, and local storage specifications for the SABR Sean Lahman Baseball Database (1871–2025).

## Requirements

### Requirement: Dual-Mode Ingestion (Automated Mirror + Manual SABR Box Import)
The system MUST support two complementary paths to acquire the complete 27-table Lahman database:
1. **Mode A (Automated Extraction):** Direct download from the up-to-date public GitHub mirror `cbwinslow/lahman-database-csv/main/data/` with two-phase atomic write gates (`.part`), token-bucket rate limiting, and manifest tracking.
2. **Mode B (Manual Local Import):** User provides local path to official `.zip` or unzipped folder downloaded from SABR Box via `lahman.import_archive(path)`. The system validates CSV headers, copies to `cache/lahman/raw/`, and compiles to Parquet in `cache/lahman/processed/`.

### Requirement: Strongly-Typed Parquet Compilation
All 27 tables MUST be parsed and saved as strongly-typed Parquet partitions in `cache/lahman/processed/{table}.parquet`.
Specific canonical schemas MUST be enforced for:
- `People`: `birthYear`, `birthMonth`, `birthDay`, `debut` (as `date32`), `finalGame` (as `date32`), `retroID`, `bbrefID`.
- `Batting`: `playerID`, `yearID`, `stint`, `teamID`, `lgID`, `G`, `AB`, `R`, `H`, `2B`, `3B`, `HR`, `RBI`, `SB`, `CS`, `BB`, `SO`.
- `Pitching`: `playerID`, `yearID`, `W`, `L`, `ERA`, `IPouts`, `SO`, `BB`, `CG`, `SHO`, `SV`.
- `Teams`: `yearID`, `teamID`, `franchID`, `divID`, `Rank`, `W`, `L`, `R`, `RA`, `ERA`, `FP`, `attendance`, `BPF`, `PPF`.
- `Fielding`: `playerID`, `yearID`, `POS`, `G`, `GS`, `InnOuts`, `PO`, `A`, `E`, `DP`, `PB`, `ZR`.
- `Salaries`: `yearID`, `teamID`, `lgID`, `playerID`, `salary`.
- `HallOfFame`: `playerID`, `yearid`, `votedBy`, `ballots`, `needed`, `votes`, `inducted`.
- `AllstarFull`: `playerID`, `yearID`, `gameID`, `teamID`, `GP`, `startingPos`.

### Requirement: Type-Safe Enums
The system MUST provide a `LahmanTable` StrEnum cataloging all 27 tables.
