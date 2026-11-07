# polymarket-ingestion Specification

## Purpose
Polymarket MLB prediction-market data (events, markets, outcomes, hourly price history) is downloaded from the public APIs into strongly typed Parquet and DuckDB views like every other source: shared HTTP client, per-host caps, audit log, raw bytes kept, nothing dropped.

## Requirements

### Requirement: Scope And Routes Are Data, Not Code
The sport in scope MUST be read from `GET /sports` (the entry whose `sport` is `mlb`), never hard-coded, and a missing sport MUST be an error. Events MUST be listed with the keyset route and its cursor, because the offset route stops at about 2,100 rows.

#### Scenario: The tag is looked up and the cursor is followed to the end
- **WHEN** the extractor asks for the sport and walks a two-page event list, and the sports list has no MLB
- **THEN** the tag id comes from the list, both pages are read with the returned cursor, all raw pages go into one gzip file, and a missing sport raises an error
- Verified by `tests/test_polymarket.py::test_the_sport_tag_comes_from_the_sports_list_and_a_missing_sport_is_an_error` and `tests/test_polymarket.py::test_events_follow_the_keyset_cursor_and_every_raw_page_is_kept_in_one_gzip`.

### Requirement: Typed Schemas From Probes
Every dataset MUST have a strict Arrow schema generated from live probes (`scripts/gen_polymarket_schemas.py`): prices and quantities written as decimals exact `decimal`, times `timestamp[us, UTC]`, the 77-digit outcome token ids text, nested values JSON text, keys `snake_case`, unknown keys kept in `_extras`, an uncastable cell quarantined.

#### Scenario: Registry, exact types and no lost keys
- **WHEN** the datasets are registered, a market is normalized with an unknown key, and outcomes are cut from a market
- **THEN** every dataset has its key and a trailing `_extras`, decimals and times are exact, the unknown key lands in `_extras`, and token ids stay text
- Verified by `tests/test_polymarket.py::test_every_dataset_is_registered_with_a_typed_key_and_prices_are_opt_in`, `tests/test_polymarket.py::test_a_market_is_typed_exactly_and_unknown_keys_are_kept_not_lost`, `tests/test_polymarket.py::test_keys_become_snake_case_and_a_collision_is_refused`, `tests/test_polymarket.py::test_outcome_rows_pair_labels_tokens_and_prices_and_tokens_stay_text` and `tests/test_infer_types.py::test_decimals_times_and_flags`.

### Requirement: Catalog In One Pass, Without Duplicates
One catalog job MUST fetch the events (each carrying its markets) once, cut out the markets and the outcome tokens, keep each event and market once, and store one chunk per month an event started.

#### Scenario: Events, markets and outcomes by month
- **WHEN** an event appears on two pages
- **THEN** it is stored once, its markets once, with two outcomes per market, in monthly chunks
- Verified by `tests/test_polymarket.py::test_catalog_ingest_splits_events_markets_and_outcomes_by_month_without_duplicates` and `tests/test_polymarket.py::test_split_event_keeps_the_event_free_of_its_markets`.

### Requirement: Price History In Windows The Route Accepts
Price history MUST be requested per outcome token in windows of at most 14 days (the route refuses longer ones), hourly, from the market start to a margin after its close (or now when open), one chunk and one raw gzip per market start date, newest date first, only for markets with traded volume; a point at a shared window edge MUST be kept once; a date whose markets are all closed and unchanged MUST NOT be fetched again.

#### Scenario: Windows, deduplication, resume and planning
- **WHEN** a 15-day market is fetched, run again, forced, and open markets are run again, and the lake holds traded and untraded markets
- **THEN** each token is asked per window, edge points are unique, a finished date is skipped, a forced or open date is fetched again, untraded markets are skipped and dates are planned newest first
- Verified by `tests/test_polymarket.py::test_price_windows_are_cut_at_fourteen_days_and_end_a_little_after_the_close`, `tests/test_polymarket.py::test_price_ingest_asks_each_token_per_window_and_keeps_one_point_per_token_and_time`, `tests/test_polymarket.py::test_a_finished_date_is_not_fetched_again_but_an_open_market_is` and `tests/test_polymarket.py::test_traded_markets_come_from_the_lake_skip_zero_volume_and_plan_newest_first`.

### Requirement: Adapter And Host Limits Like Every Source
Polymarket MUST plug in only through `IngestAdapter` (one catalog job, then one prices job per date that waits for it), and each Polymarket host MUST have a documented rate and in-flight default.

#### Scenario: Jobs and limits
- **WHEN** a selection with the catalog and prices is planned and run, with a limit and with an unknown dataset, and the default limits are read
- **THEN** the jobs and their dependency are right, `--limit` keeps the newest dates, an unknown dataset is refused, and the hosts have 24, 80 and 16 requests a second
- Verified by `tests/test_polymarket.py::test_adapter_plans_a_catalog_job_then_one_price_job_per_date_and_runs_them` and `tests/test_polymarket.py::test_hosts_have_documented_rate_and_in_flight_defaults`.
