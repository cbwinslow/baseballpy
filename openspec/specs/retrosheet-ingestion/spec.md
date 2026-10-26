# retrosheet-ingestion Specification

## Purpose
Defines the ingestion, schema parsing, and multi-sink export specifications for all Retrosheet baseball datasets (play-by-play events, 161-column game logs, and annual team rosters).

## Requirements

### Requirement: Two-Tier Storage Architecture (`raw/` and `processed/`)
The system MUST isolate downloaded Retrosheet archive text files from strongly-typed columnar outputs:
- `raw/{year}/`: Contains unmodified `.EVA`/`.EVN` event files, `TEAM{year}` manifests, and `{team}{year}.ROS` rosters retrieved from the Fastly-backed GitHub raw mirror (`chadwickbureau/retrosheet`).
- `processed/`: Contains Snappy-compressed PyArrow Parquet files (`events/season={year}/events.parquet`, `gamelogs/gl{year}.parquet`, `rosters/rosters_{year}.parquet`).

#### Scenario: Season download folder isolation
- **GIVEN** a request to extract Retrosheet data for season 2024
- **WHEN** downloaded and parsed
- **THEN** raw text files are placed in `raw/2024/` and parsed Parquet files in `processed/events/season=2024/`.

### Requirement: In-Memory Parsing via `chadwickpy`
The system MUST parse raw `.EVA` and `.EVN` event files using pure-Python `chadwickpy.tools.events.event_rows` and `chadwickpy.roster.League` directly in memory without writing intermediate files to disk or requiring a native C toolchain.

#### Scenario: Parsing single event file
- **GIVEN** an extracted `.EVA` event file
- **WHEN** parsed through `RetrosheetEventParser`
- **THEN** output conforms strictly to `RETROSHEET_EVENT_SCHEMA` (97 fields) with explicit numeric types (`INN_CT` as `int16`, `BAT_HOME_ID` as `int8`, `EVENT_CD` as `int16`).

### Requirement: Two-Phase Atomic Commit & Checkpointing
Downloads and Parquet conversions MUST write to `{filename}.part` and atomically rename to final destination only after verifying format integrity. Completion is checkpointed in `manifest.json`.

#### Scenario: Interrupted season extraction resumption
- **GIVEN** an extraction of season 2024 that was previously completed
- **WHEN** re-invoked without `refresh=True`
- **THEN** the system inspects `manifest.json`, sees `"events_2024": "COMPLETED"`, and returns the cached Parquet table with zero network calls.
