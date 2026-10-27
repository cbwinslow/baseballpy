## ADDED Requirements

### Requirement: Minor-League Pitches
The system MUST ingest Savant's minor-league pitch export (`statcast_search/csv` with `minors=true`) into the dataset `statcast.pitches_minors` with the same strict schema and key as `pitches`, partitioned by season, for every season with data (2021 onwards). The unfiltered minors population is persisted; a `hfLevel` filter is returned but never persisted. Minor-league and MLB pitches MUST NOT share a dataset.

#### Scenario: Level filter
- **GIVEN** `StatcastQuery(minors=True, levels=("AAA",))`
- **THEN** rows are returned and nothing is written to `pitches_minors`.

#### Scenario: Season before minor-league tracking
- **WHEN** `ingest_season(2019, minors=True)` is requested
- **THEN** it reports that no minor-league data exists before 2021 and makes no pitch requests.
