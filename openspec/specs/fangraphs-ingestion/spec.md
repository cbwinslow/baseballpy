# fangraphs-ingestion Specification

## Purpose
FanGraphs tables the user already holds (or exports as a member) are typed into strongly typed Parquet and DuckDB views from files in an inbox folder, as private research data. baseballpy downloads only slowly, honestly and with a hard stop at the first refusal, or types files you supply.

## Requirements

### Requirement: No Request To FanGraphs Without The Download Option, Files From An Inbox
Without `-o download=yes` the source MUST read only files in `inbox/fangraphs/` (`<dataset>.csv` or `.csv.gz`), MUST make no network request, MUST name the missing file and where to put it when a dataset is asked for by name without one, and MUST list the datasets without a file when none were named.

#### Scenario: Missing files and no network
- **WHEN** a dataset is asked for without its file, and the default run has one file of ten
- **THEN** the named dataset raises an error that gives the file name, the default run types the one file and lists the others as missing, and no HTTP client is used
- Verified by `tests/test_fangraphs.py::test_a_missing_file_is_named_or_listed_and_nothing_is_ever_requested`.

### Requirement: Registered As Private On-Demand Datasets
Each of the ten files MUST be a registered dataset that needs an input (`on_demand`), has its key inside its strict schema, ends with `_extras`, and says "private" in its description.

#### Scenario: Registry
- **WHEN** the registry is listed
- **THEN** ten FanGraphs datasets exist with the declared keys and descriptions
- Verified by `tests/test_fangraphs.py::test_ten_files_are_registered_as_on_demand_datasets_with_keys_in_the_schema`.

### Requirement: Typed From The Whole File, Nothing Lost
Schemas MUST be generated from the whole files (`scripts/gen_fangraphs_schemas.py`): counts as integers (a whole number written as `157.0` is the integer 157), numbers with more than 8 decimals or in scientific notation as `float64`, shorter decimals exact, times as timestamps; empty cells are NULL; a header the schema does not know MUST land in `_extras`; the raw bytes MUST be kept with the sha256 of the original; a file whose bytes are unchanged MUST be skipped and `--refresh` MUST type it again; no cell of a clean file MUST be quarantined.

#### Scenario: Types, raw bytes, reruns and drift
- **WHEN** files with leading-dot decimals, whole numbers written as floats and an extra column are ingested, gzipped or not, twice, and with refresh
- **THEN** values are exact, nothing is quarantined, the extra column is in `_extras`, the raw bytes verify against their checksum, the second run skips and the refresh types again
- Verified by `tests/test_fangraphs.py::test_values_are_typed_exactly_and_nothing_is_set_aside`, `tests/test_fangraphs.py::test_whole_numbers_written_as_floats_load_as_integers`, `tests/test_fangraphs.py::test_a_new_column_lands_in_extras_and_nothing_is_dropped`, `tests/test_fangraphs.py::test_the_file_may_be_gzipped_and_the_raw_bytes_are_kept_with_their_checksum`, `tests/test_fangraphs.py::test_an_unchanged_file_is_left_alone_and_refresh_types_it_again`, `tests/test_infer_types.py::test_a_whole_number_written_with_a_zero_fraction_loads_as_that_integer` and `tests/test_infer_types.py::test_long_or_scientific_numbers_in_text_are_floats_when_asked`.

### Requirement: A Read-Only Copy From The Homelab
`scripts/export_homelab_fangraphs.py` MUST copy a homelab table with one read-only `psql \copy ... to stdout` over key-based `ssh`, refuse database, schema or table names that are not plain words, and write into the inbox.

#### Scenario: One command, odd names refused
- **WHEN** a table is exported and odd names are tried
- **THEN** one ssh command with a read-only copy is built, and names with spaces or SQL are refused
- Verified by `tests/test_fangraphs.py::test_the_export_script_refuses_odd_names_and_builds_one_read_only_copy_command` and `tests/test_fangraphs.py::test_adapter_plans_one_job_and_reports_missing_files`.

### Requirement: A Slow Honest Downloader For Leaderboards And Projections
`ingest fangraphs -o download=yes` MUST download leaderboard seasons and projection snapshots from FanGraphs' website JSON routes through the shared client, at one request every two seconds with one in flight, with a user agent that names baseballpy and its address (never a browser, app or library disguise), with no retry after a refusal, and MUST stop with a message that points to the files-you-supply route at HTTP 403, 429 or 503 or when a web page arrives where data should be, storing nothing from it. A past season already stored MUST NOT be fetched again unless asked; a projection row MUST be stored only when its values changed since the player's last snapshot; keys MUST be renamed by the rule the existing columns follow so a download and a file meet in the same typed columns; the importer and the downloader MUST write the same chunk names.

#### Scenario: Honest, slow, stops, shapes, dedupes
- **WHEN** seasons and projections are downloaded from a fake FanGraphs, refused with 403, 429 and 503, answered with a web page, and the same data is fetched twice
- **THEN** the user agent names baseballpy, the host is capped at 0.5 requests a second with one attempt, a refusal or a challenge stops the run and stores nothing, rows are typed into the batting and projection tables with unknown keys in `_extras`, a past season and unchanged projections are skipped, and a season from a file is replaced by the downloaded one
- Verified by `tests/test_fangraphs_download.py::test_the_user_agent_is_honest_and_set_for_this_host_only`, `tests/test_fangraphs_download.py::test_a_refusal_stops_the_run_with_a_clear_message`, `tests/test_fangraphs_download.py::test_a_web_page_instead_of_data_is_a_bot_challenge_and_stops_the_run`, `tests/test_fangraphs_download.py::test_the_shared_client_makes_exactly_one_request_when_fangraphs_refuses`, `tests/test_fangraphs_download.py::test_the_host_is_slow_and_one_request_at_a_time`, `tests/test_fangraphs_download.py::test_a_season_is_typed_into_the_same_columns_and_unknown_keys_are_kept`, `tests/test_fangraphs_download.py::test_a_past_season_is_not_fetched_again_but_the_current_one_always_is`, `tests/test_fangraphs_download.py::test_a_downloaded_season_replaces_the_same_season_from_a_file_without_duplicates`, `tests/test_fangraphs_download.py::test_projection_rows_are_stored_only_when_their_values_changed` and `tests/test_fangraphs_download.py::test_the_row_hash_follows_the_values_not_the_bookkeeping`.

#### Scenario: Column names, modes and the option switch
- **WHEN** keys such as `1B`, `BB%` and `-WPA` are renamed, every existing column name is renamed again, the adapter plans with and without the download option, and the command gets a good and a bad `--option`
- **THEN** names follow the rule and are stable under it, files are planned by default and downloads only on request (non-downloadable datasets refused), and a bad option is a usage error
- Verified by `tests/test_fangraphs_download.py::test_keys_become_the_column_names_the_tables_use`, `tests/test_fangraphs_download.py::test_every_existing_column_name_is_stable_under_the_rule`, `tests/test_fangraphs_download.py::test_the_adapter_plans_files_by_default_and_downloads_only_when_asked` and `tests/test_fangraphs_download.py::test_the_option_switch_reaches_the_planner_and_a_bad_one_is_refused`.
