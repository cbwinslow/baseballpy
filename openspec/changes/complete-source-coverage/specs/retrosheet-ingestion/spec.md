## MODIFIED Requirements

### Requirement: Tree-Driven Discovery
Available seasons and files MUST be discovered from the upstream repository tree at the pinned ref, not hard-coded.

### Requirement: Complete Dataset Set
The system MUST ingest event files (regular and postseason/all-star), box-score files, schedules, rosters, regular and postseason game logs, every CSV under `reference/`, and the parsed events, boxscores, daily splits and substitutions tables.

### Requirement: Honest Completion
A season MUST be marked COMPLETED only if every file the tree lists for it is present and valid; missing upstream files are recorded `ABSENT`; a 404 is never success.

#### Scenario: Interrupted ingest
- **GIVEN** an `ingest_all(2000, 2005)` killed during 2003
- **WHEN** re-run
- **THEN** 2000–2002 are skipped, 2003's `.part` files are discarded, and 2003–2005 complete.

### Requirement: Streaming Parse
Parsing MUST stream into Parquet row-group batches without accumulating whole-season Python lists.
