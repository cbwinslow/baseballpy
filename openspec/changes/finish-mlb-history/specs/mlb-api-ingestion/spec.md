## ADDED Requirements

### Requirement: A Games Run Fetches Only The Games
The job planned for the `games` dataset unit MUST run the per-game datasets and the schedule they need, and MUST NOT repeat the reference tables or the season datasets (those have their own job). A job without the `games_only` parameter MUST keep the earlier behavior.

#### Scenario: Games only
- **WHEN** the plan for `-d games` is built and its job is run, and an older job without `games_only` is run
- **THEN** the new job asks the source for `include_season=False` and the older one for `include_season=True`
- Verified by `tests/test_mlb_game_levels.py::test_a_games_run_fetches_only_the_games_not_the_season_datasets_again`.
