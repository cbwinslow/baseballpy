## ADDED Requirements

### Requirement: Plan Stages Carry Source Options And Run Seasons Newest First
A plan stage MUST accept `options` (a table of name = value pairs whose values are text, numbers or booleans, passed to the adapter as the same pairs as `ingest --option`) and `order` (`newest-first`, the default, or `oldest-first`); a malformed `options` or an unknown `order` MUST be refused with a message that names it. The package MUST ship the built-in plans `minors` (the MLB games of every level from 2021) and `minors-all` (from 2008), each with `options = { sports = "all" }` and a size estimate.

#### Scenario: Options reach the adapter, order is respected, the plans load
- **WHEN** a plan stage with options and seasons is planned, a stage has a bad option or order, and the built-in plans are loaded
- **THEN** the adapter receives the option pairs, the seasons run newest first unless the stage says otherwise, bad values are refused naming `options` or `order`, and both built-in plans ask for every level
- Verified by `tests/test_backfill_options.py::test_stage_options_reach_the_adapter_as_option_pairs`, `tests/test_backfill_options.py::test_bad_options_are_refused`, `tests/test_backfill_options.py::test_seasons_of_a_stage_run_newest_first`, `tests/test_backfill_options.py::test_the_oldest_first_order_can_be_asked_for` and `tests/test_backfill_options.py::test_the_built_in_plans_for_minor_leagues_load_and_ask_for_every_level`.

### Requirement: The Package Offers `download`, `update` And `backfill` As Python Functions
`baseballpy.download(source, seasons, datasets, **options)`, `baseballpy.update()` and `baseballpy.backfill(plan)` MUST do what `ingest`, `update` and `backfill` do (plan, check the disk, run through the adapters, sync the DuckDB views when something was stored) and return the report; seasons MAY be a year, a list or the text of the commands; keyword arguments MUST be the source's options; an unknown source MUST raise a `ValueError` that lists the known ones; a plan that does not fit the disk MUST raise `BackfillError` before anything runs; `dry_run` MUST plan and run nothing.

#### Scenario: One call does the work and returns the report
- **WHEN** the functions are called with fake adapters for a source, a plan object, a built-in plan name and the daily plan
- **THEN** seasons run newest first, datasets, options and refresh reach the adapter, the views are synced only after a stored job, a plan that does not fit is refused, a dry run runs nothing and `update` runs the daily stages
- Verified by `tests/test_python_api.py::test_download_runs_the_seasons_newest_first_and_returns_the_report`, `tests/test_python_api.py::test_datasets_options_and_refresh_reach_the_adapter`, `tests/test_python_api.py::test_an_unknown_source_is_a_clear_error_that_lists_the_known_ones`, `tests/test_python_api.py::test_the_views_are_synced_after_a_download_that_stored_something`, `tests/test_python_api.py::test_nothing_is_synced_when_every_job_failed_or_sync_is_off`, `tests/test_python_api.py::test_backfill_runs_a_plan_object_with_the_disk_guard`, `tests/test_python_api.py::test_backfill_dry_run_plans_and_runs_nothing`, `tests/test_python_api.py::test_backfill_takes_the_name_of_a_built_in_plan_and_selects_stages` and `tests/test_python_api.py::test_update_is_the_daily_plan`.
