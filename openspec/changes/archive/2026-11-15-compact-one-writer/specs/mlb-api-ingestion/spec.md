## ADDED Requirements

### Requirement: Games The Provider Cannot Serve Are Listed With Evidence And Not Asked For Again
The package MUST ship `sources/mlb_api/unavailable_games.json`: one entry per game that answers HTTP 500 on every URL, with its season, status, probe date, the URLs and the evidence (audit-log counts and a fresh probe). `ingest_game_segments` MUST NOT request a listed game that is not stored, MUST NOT count it as failed, MUST name it in `GameSegmentReport.unavailable`, and the job report MUST count it as `missing`. A game that is not listed and fails MUST still be a failure and MUST be fetched again next time. `scripts/probe_unavailable_games.py` MUST say, with one request per listed game, which games answer again.

#### Scenario: A listed game is skipped, an unlisted failing game is not
- **WHEN** a season's games are ingested and one game is listed as unavailable, one unlisted game answers HTTP 500, and the shipped list is read
- **THEN** the listed game is not requested, not failed and reported as unavailable (missing in the job report), the unlisted game fails and is retried next time, and every shipped entry carries status, probe date, URLs and evidence
- Verified by `tests/test_mlb_unavailable_games.py::test_a_listed_game_is_not_requested_and_is_not_a_failure`, `tests/test_mlb_unavailable_games.py::test_a_game_that_is_not_listed_still_fails_and_is_retried_next_time`, `tests/test_mlb_unavailable_games.py::test_the_job_report_counts_listed_games_as_missing_not_as_errors`, `tests/test_mlb_unavailable_games.py::test_the_shipped_list_is_valid_and_every_entry_carries_its_evidence` and `tests/test_mlb_unavailable_games.py::test_the_probe_script_names_the_games_that_answer_again`.
