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
