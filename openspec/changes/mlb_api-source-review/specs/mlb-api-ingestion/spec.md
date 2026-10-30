## ADDED Requirements

### Requirement: Raw Files Record an Upstream Fingerprint
Every raw MLB Stats API payload MUST record an upstream fingerprint in its manifest entry: the provider's ETag when the response carries one, else the sha256 of the payload.

#### Scenario: Fingerprints are recorded
- **WHEN** endpoint payloads are stored
- **THEN** each raw manifest entry holds a fingerprint
- Verified by `tests/test_mlb_coverage.py::test_every_mlb_raw_file_records_an_upstream_fingerprint`.

### Requirement: Stored Tables Follow the Schema
A stored table MUST NOT be served when its recorded schema digest differs from the dataset's current schema (ADR 49); it is fetched again without `--refresh`.

#### Scenario: A schema change refetches
- **WHEN** a stored table's schema digest differs from the dataset's
- **THEN** the next call fetches it again
- Verified by `tests/test_mlb_api.py::test_a_teams_table_written_under_another_schema_is_fetched_again`.

### Requirement: No Hard-Coded Default Season
A function that defaults a season or year MUST default to the current season of the calendar, never to a fixed year, and `refresh=True` MUST reach the network for every dataset.

#### Scenario: Defaults follow the calendar and refresh is honoured
- **WHEN** standings, transactions and the draft are requested without a season, and standings with refresh
- **THEN** the requests carry the calendar's season and refresh fetches again
- Verified by `tests/test_mlb_api.py::test_default_seasons_follow_the_calendar_and_standings_honour_refresh`.

### Requirement: Every Dataset Is Reachable From Python
`baseballpy.sources.mlb_api.table(name, season, **arguments)` MUST return any registered MLB dataset by its registry name, `datasets()` MUST list exactly the registered names, and an unknown name MUST raise an error that lists the valid ones.

#### Scenario: Names resolve
- **WHEN** a hand-written dataset and an unknown name are requested
- **THEN** the table comes back and the unknown name raises
- Verified by `tests/test_mlb_api.py::test_table_reaches_hand_written_and_declarative_datasets_by_name`.

### Requirement: A Refused Request Does Not Stop The Rest
A single-endpoint call MUST raise when the provider refuses a request (HTTP error status). In a season, history or people-stats run (`keep_going`), the other requests MUST still be ingested; the endpoint report MUST list the refusals and the ingest job MUST end with status failed, a detail line and an error naming the first refusals, while the stored data stays.

#### Scenario: A 406 on one game
- **WHEN** one of two game requests answers 406 and the other succeeds
- **THEN** the report has rows and one error, and the job result is failed with the rows of the successful request
- Verified by `tests/test_mlb_coverage.py::test_one_refused_request_does_not_stop_the_others_and_fails_the_job_afterwards`.
