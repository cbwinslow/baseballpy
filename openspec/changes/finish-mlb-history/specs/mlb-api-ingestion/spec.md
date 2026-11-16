## ADDED Requirements

### Requirement: A Games Run Fetches Only The Games
The job planned for the `games` dataset unit MUST run the per-game datasets and the schedule they need, and MUST NOT repeat the reference tables or the season datasets (those have their own job). A job without the `games_only` parameter MUST keep the earlier behavior.

#### Scenario: Games only
- **WHEN** the plan for `-d games` is built and its job is run, and an older job without `games_only` is run
- **THEN** the new job asks the source for `include_season=False` and the older one for `include_season=True`
- Verified by `tests/test_mlb_game_levels.py::test_a_games_run_fetches_only_the_games_not_the_season_datasets_again`.

### Requirement: A Game Without Plays Has No Win Probability, And That Is Not A Failure
A 404 for the win probability of a game MUST be recorded as an empty, counted result and MUST NOT fail the job or be asked for again; a 404 for any other per-game dataset MUST still fail loudly.

#### Scenario: A cancelled game
- **WHEN** the win probability of a cancelled game answers 404, and the dataset is ingested twice
- **THEN** the first run counts one missing request and no error, the second asks nothing, and the boxscore does not tolerate a 404
- Verified by `tests/test_mlb_coverage.py::test_a_cancelled_game_has_no_win_probability_and_that_is_not_a_failure`.

### Requirement: A Stored Game Is Whole Only When Every URL Has An Answer On Record
`ingest_game_segments` MUST, for the games it is asked about that are already stored, look at the answers on record in their segment and request only the URLs that have none (a 200, or a 404 of a URL that tolerates it, counts as an answer), then refresh the segment with the old and the new answers (the raw file keeps every old row). A 404 of a tolerated URL MUST be stored as an answer so that it is not asked again; a URL that cannot be fetched (a server error) MUST leave the game as it was and be reported as failed; a game that is not in the requested list MUST NOT be touched. The report MUST count the completed games and MUST NOT count the refreshed segment's rows as new.

#### Scenario: Missing URLs are fetched once, 404s are remembered, errors are not hidden
- **WHEN** a game stored with two of its five URLs is ingested again, once with the provider answering, once with a 404 for a tolerated URL, once with a 500, and once with the game not requested
- **THEN** only the missing URLs are requested and all datasets of the game get rows, a second run asks for nothing, the 404 is on record and not asked again, the 500 fails the game and keeps what was stored, and the unrequested game is left alone
- Verified by `tests/test_mlb_complete_units.py::test_only_the_missing_urls_are_fetched_and_the_game_gets_all_its_rows`, `tests/test_mlb_complete_units.py::test_a_second_run_asks_for_nothing`, `tests/test_mlb_complete_units.py::test_an_answer_of_404_for_a_tolerated_url_is_stored_so_it_is_not_asked_again`, `tests/test_mlb_complete_units.py::test_a_server_error_while_completing_fails_the_game_and_keeps_what_was_stored` and `tests/test_mlb_complete_units.py::test_a_game_that_is_not_in_the_requested_list_is_left_alone`.
