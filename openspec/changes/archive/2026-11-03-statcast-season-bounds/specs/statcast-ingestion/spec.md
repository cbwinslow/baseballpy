## ADDED Requirements

### Requirement: Season Bounds
Statcast ingestion MUST NOT request a season before 2008 for any dataset (owner rule, ADR 56), before 2021 for `pitches_minors`, or before the first season the live probe recorded for a leaderboard variant. The top end MUST NOT be a constant: it is the current year of the lake clock, and a season whose calendar start is after today MUST be skipped. Bulk ingests (`ingest_season`, `ingest_all`, `ingest_leaderboard`, `StatcastGameFeed.ingest_season`) MUST report a skipped season with its reason and make no request; single fetches (`get_leaderboard`, `extract`, `table`) MUST raise `ValueError` naming the bounds. The adapter MUST report such jobs as `skipped` with the reason, never as failed.

#### Scenario: A season before 2008 makes no request
- **WHEN** a pitch, leaderboard or game-feed ingest is asked for 1990
- **THEN** the report is skipped with a reason naming 2008 and no HTTP request is made
- Verified by `tests/test_statcast_seasons.py::test_a_season_before_2008_is_skipped_without_any_request`.

#### Scenario: The top end follows the clock
- **GIVEN** the lake clock says 2027-06-01
- **WHEN** seasons 2027 and 2028 are requested
- **THEN** 2027 is fetched and 2028 is skipped as in the future, with no code change
- Verified by `tests/test_statcast_seasons.py::test_the_top_end_follows_the_lake_clock`.

#### Scenario: A mixed selection still runs
- **WHEN** the adapter runs a pitch job for 1990
- **THEN** the job is `skipped` with the reason in its detail, not `failed`
- Verified by `tests/test_statcast_seasons.py::test_the_adapter_skips_an_excluded_season_instead_of_failing`.

#### Scenario: Single fetches are loud
- **WHEN** `extract("1990-04-01", "1990-04-05")`, `get_leaderboard(..., year=1990)` or `table("pitches", 1990)` is called
- **THEN** each raises `ValueError` naming the bounds
- Verified by `tests/test_statcast_seasons.py::test_single_fetches_raise_for_an_excluded_season`.
