# real-time-streaming Specification

## Purpose
Defines the specifications for low-latency live Gameday feed polling, delta detection, and streaming into real-time analytical and predictive machine learning models.

## Requirements

### Requirement: Incremental State Diffing
The system MUST track `(atBatIndex, eventIndex)` watermarks during live games and only yield new play deltas (pitches, pickoffs, balls, strikes, hits, outs).

#### Scenario: Live game polling without new events
- **GIVEN** an active game polled 5 seconds after a previous check
- **WHEN** the upstream `metaData.timeStamp` or `atBatIndex` has not advanced
- **THEN** no downstream events are emitted and no duplicate records are written to storage.

#### Scenario: New pitch thrown
- **GIVEN** a new pitch recorded in the live Gameday feed
- **WHEN** detected by the streamer
- **THEN** it immediately emits the pitch event with full coordinates, pitch type, and game context to connected consumers (`LiveEventConsumerProtocol`).

### Requirement: Idempotent Storage Upsert
Because official MLB scorers can amend plays post-facto (e.g. changing an error to a hit), real-time sinks MUST upsert records keyed by `(game_pk, at_bat_number, pitch_number)`.
