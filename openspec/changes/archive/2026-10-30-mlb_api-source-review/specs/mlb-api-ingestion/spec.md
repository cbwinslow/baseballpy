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

### Requirement: League-Wide Pools Survive A Refused Pool Route
When `/v1/stats` answers HTTP 406 for a league-wide player pool, the pool MUST be fetched through `/v1/people?personIds=...&hydrate=stats(...)` in batches of the sport's players, every provider response MUST be kept as raw bytes, and the splits MUST be normalised with the same schema as the direct route.

#### Scenario: A 406 on the pool route
- **WHEN** the direct route answers 406 and the people route answers 200
- **THEN** the pool's rows are stored and the raw hydrate pages are kept
- Verified by `tests/test_mlb_coverage.py::test_a_refused_league_wide_pool_is_fetched_through_people_hydrate`.

### Requirement: A Probe Reports Provider Health
`baseballpy probe` MUST send one small request to each provider route the project depends on, print the status and time of each, name a fallback where one exists, and exit with code 1 when any route does not answer 200.

#### Scenario: One route is down
- **WHEN** the league-wide pool route answers 406 and the others 200
- **THEN** the table marks that route FAILED with its fallback and the exit code is 1
- Verified by `tests/test_probe.py::test_probe_names_the_failing_route_and_its_fallback` and `tests/test_probe.py::test_probe_passes_when_every_route_answers`.
