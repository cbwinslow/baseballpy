# mlb-api-ingestion Specification

## Purpose
Defines the extraction and normalization specifications for the official MLB Stats API (`statsapi.mlb.com`), encompassing schedule, live Gameday feeds, boxscores, and roster transactions.

## Requirements

### Requirement: Schedule and Game Index Extraction
The system MUST query `statsapi.mlb.com/api/v1/schedule` with date windows and sport codes (default 1 for MLB), parsing game statuses, doubleheaders, venue IDs, and `game_pk` identifiers.

#### Scenario: Querying daily schedule
- **GIVEN** a date range `2024-06-01` to `2024-06-07`
- **WHEN** `mlb_schedule(start_date, end_date)` is called
- **THEN** returns a typed Arrow table containing all scheduled games with `game_pk`, game type, teams, probable pitchers, and official statuses.

### Requirement: Live Gameday Feed Change Detection
The system MUST support polling or streaming `statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live`, comparing timestamps (`metaData.timeStamp`), and emitting only incremental play-by-play deltas.

#### Scenario: Live game monitoring
- **GIVEN** an active game with `game_pk=745789`
- **WHEN** `stream_game(game_pk, poll_interval=10)` runs during live play
- **THEN** it emits newly completed pitches, at-bats, and play events with zero redundant inserts into the downstream sink.
