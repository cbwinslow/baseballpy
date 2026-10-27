## MODIFIED Requirements

### Requirement: Pitch Search Completeness
The pitch schema MUST be the union of all columns across eras (2008–present); era-specific columns are nullable; unknown columns are preserved. Windows hitting Savant's 25,000-row cap MUST be bisected automatically; a capped single day MUST raise and MUST NOT be cached.

#### Scenario: Truncation detection
- **GIVEN** a 5-day window returning exactly 25,000 rows
- **THEN** it is split into two windows that are fetched and concatenated
- **AND** the cached partition contains the union without duplicates.

### Requirement: Leaderboard Registry
Every leaderboard in `docs/ENDPOINT_CATALOG.md` §Savant MUST have an explicit schema, key columns and `min_year`, and MUST be ingestible for all years and type variants. Column types MUST NOT be inferred from column-name substrings.

#### Scenario: Typing regression
- **GIVEN** a leaderboard CSV with columns `bats`, `average_hit_speed`, `pa`, `hp_to_1b`
- **THEN** `bats` is string, `average_hit_speed` is float, `pa` is integer, `hp_to_1b` is float.

### Requirement: Season Ingest
`ingest_season(year)` and `ingest_all(start_year=2008)` MUST resume via the manifest and be idempotent on `(game_pk, at_bat_number, pitch_number)`.
