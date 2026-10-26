# statcast-ingestion Specification

## Purpose
Defines the extraction, chunking, schema enforcement, and caching specifications for Baseball Savant (Statcast) pitch-by-pitch tracking data and leaderboards.

## Requirements

### Requirement: Bounded Date-Range Chunking
Baseball Savant drops connections or truncates results when single queries exceed ~25,000 pitches. The system MUST automatically subdivide requested date ranges into bounded chunks (e.g. 5–7 day windows for regular season), executing requests concurrently under rate-limiting bounds.

#### Scenario: Full-season Statcast extraction
- **GIVEN** a request for `start_dt="2024-04-01"` and `end_dt="2024-10-01"`
- **WHEN** `extract_statcast()` is invoked
- **THEN** the extractor partitions the 6-month period into weekly chunks, schedules them across an async worker pool with token bucket rate limiting, and concats or streams batches.

### Requirement: Strongly-Typed Statcast Schema
Statcast CSV dumps provide all columns as plain text or scientific notation strings with varying null representations (`null`, `""`, `NA`, `None`). The system MUST coerce all 90+ attributes into canonical Arrow data types.

#### Scenario: Normalizing pitch and coordinate fields
- **GIVEN** raw Statcast CSV/JSON rows
- **WHEN** parsed through `StatcastNormalizer`
- **THEN**:
  - `game_date` is parsed as `pa.date32()`
  - `release_speed`, `effective_speed`, `release_spin_rate` are `pa.float32()`
  - `plate_x`, `plate_z`, `release_pos_x`, `release_pos_z` are `pa.float32()`
  - `balls`, `strikes`, `outs_when_up`, `inning` are `pa.int8()`
  - `pitcher`, `batter` are `pa.int32()`
  - `pitch_type`, `events`, `description` are dictionary-encoded `pa.dictionary(pa.int8(), pa.string())`.
