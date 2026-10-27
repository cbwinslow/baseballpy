## MODIFIED Requirements

### Requirement: Strict Schemas for All 27 Tables
Every Lahman table MUST have an explicit PyArrow schema generated from the real upstream header, documented primary key, and `_extras` preservation of unknown columns.

#### Scenario: New upstream column
- **WHEN** a release adds a column `foo` to `Batting.csv`
- **THEN** ingestion succeeds, `foo` is stored in `_extras`, and a drift warning is logged.

### Requirement: Permitted Sources Only
Lahman data MUST come only from the configured remote repo (default `cbwinslow/lahman-database-csv`, pinned ref) or from user-supplied data via `import_archive`. `chadwickbureau/baseballdatabank` MUST NOT be used, and there is no automatic fallback to any other repository. The manifest MUST record the source (`remote@sha` or `local-import`) per table.

#### Scenario: Remote unavailable
- **WHEN** the configured remote returns 404/5xx after retries
- **THEN** an error is raised that names `import_archive` as the alternative
- **AND** no other repository is contacted.

#### Scenario: Stale data warning
- **WHEN** the newest `yearID` in `Batting` is more than one season behind the last completed MLB season
- **THEN** a warning is logged and surfaced by `baseballpy catalog status`.
