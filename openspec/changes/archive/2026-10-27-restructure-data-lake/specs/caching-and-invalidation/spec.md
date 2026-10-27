## ADDED Requirements

### Requirement: Four-Tier Local Layout
All persisted data MUST live under `$BASEBALLPY_HOME` in `raw/`, `processed/`, `quarantine/`, `cache/http/`, `databases/` and `logs/`. Datasets MUST live only in `raw/` and `processed/`.

#### Scenario: Cache deletion is safe
- **GIVEN** a populated lake
- **WHEN** `cache/` is deleted
- **THEN** no dataset is lost and all DuckDB views still resolve.

#### Scenario: Datasets do not share partitions
- **GIVEN** Retrosheet regular-season and postseason events for 2023
- **THEN** they are stored in `processed/retrosheet/events/season=2023/` and `processed/retrosheet/events_postseason/season=2023/` respectively
- **AND** `SELECT count(*) FROM retrosheet_events` equals the regular-season row count only.

### Requirement: Layout Migration
`baseballpy migrate-layout` MUST convert a v1 tree to v2 idempotently, verify row counts, and never delete v1 data unless `--delete-old` is passed.

### Requirement: Reproducible Source Refs
GitHub-hosted sources MUST be fetched at a pinned commit SHA recorded in `core/sources_lock.py` and in each manifest entry's `source_ref`.
