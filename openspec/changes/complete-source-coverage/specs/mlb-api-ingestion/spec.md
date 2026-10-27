## MODIFIED Requirements

### Requirement: Endpoint Coverage
The system MUST ingest every endpoint family listed in `docs/ENDPOINT_CATALOG.md` §MLB (reference/meta, seasons, sports, leagues, divisions, teams and rosters of every roster type, venues, people, people stats for every stat type and group, standings of every type, league stats and leaders, awards, attendance, draft and prospects, transactions, jobs, schedules of every game type, and per-game feed/linescore/boxscore/play-by-play/win-probability/context/content data). Endpoints that do not respond MUST be recorded as `unsupported` with probe evidence.

#### Scenario: Full game ingest
- **GIVEN** a Final regular-season `game_pk`
- **WHEN** the game is ingested
- **THEN** tables `game_feed_plays`, `game_feed_play_events`, `game_feed_runners`, `game_feed_boxscore_players`, `game_feed_linescore_innings` and `game_feed_officials` contain rows for that `game_pk`
- **AND** every pitch event row carries pitch speed, coordinates, breaks, spin, zone and, for batted balls, `hitData` launch speed/angle/distance.

### Requirement: No Field Loss
Fields not mapped to typed columns MUST be preserved in `_extras` and logged as schema drift.

### Requirement: Rate Limiting and Pooling
All MLB API requests MUST go through `HttpClient` (HTTP/2, 8 req/s default, bounded concurrency).

### Requirement: Live Streaming
The streamer MUST implement `StreamExtractorProtocol`, use `diffPatch`/`timestamps` or `metaData.timeStamp` comparison, emit complete pitch/hit/result content with µs UTC timestamps, handle delay/suspension/postponement, and never swallow errors.

#### Scenario: Suspended game
- **WHEN** the game status becomes `Suspended`
- **THEN** a `game_status` event is emitted and the stream ends cleanly
- **AND** a later stream for the same `game_pk` resumes from the stored watermark without re-emitting events.
