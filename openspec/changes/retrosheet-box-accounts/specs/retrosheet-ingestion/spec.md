## ADDED Requirements

### Requirement: Box-Score Game Accounts
Every `.EB*` file MUST be parsed into typed per-record-kind datasets (games/info, starters, batting, pinch hitters, pinch runners, fielding, pitching, team totals, linescores, events, comments) keyed by `game_id`, with innings stored as outs; an unexpected field count MUST raise and an unknown record kind MUST be preserved in `box_unparsed` with a drift warning.

#### Scenario: Season with box accounts only
- **GIVEN** a season whose games exist only as box accounts
- **WHEN** it is ingested
- **THEN** `box_games` has one row per game and the batting lines sum to the linescore runs.
