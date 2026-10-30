## ADDED Requirements

### Requirement: Every Operation Is Audit-Logged and Timed
Every Statcast operation that downloads or stores data (pitch search windows, leaderboards, game-feed fetches and game-feed season ingests) MUST write one structured audit event (operation, endpoint, destination, records, duration, cache hit, status), and a failure MUST be logged with status FAILURE and re-raised.

#### Scenario: Game feeds leave a trail
- **WHEN** a game feed is fetched by a season ingest and the season is ingested again
- **THEN** the log holds one fetch event and two season events, the second one a cache hit
- Verified by `tests/test_statcast_coverage.py::test_game_feed_fetches_and_season_ingests_are_audit_logged`.
