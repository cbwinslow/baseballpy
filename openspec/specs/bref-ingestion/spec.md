# bref-ingestion Specification

## Purpose
Baseball-Reference WAR (batting and pitching) is downloaded from the two files the site publishes for download into strongly typed Parquet and DuckDB views like every other source, with the fewest possible requests and no way to get the session blocked.

## Requirements

### Requirement: Only The Published Files, Few Requests, Kept Raw
The source MUST fetch only the two published WAR files, at most two requests per run, none when a file was downloaded in the last 12 hours, keep the raw bytes with the sha256 of the original, and apply a rate cap far below the 20 requests a minute at which Sports Reference blocks a session.

#### Scenario: One download, reuse while recent, checksum of the original
- **WHEN** a file is fetched, fetched again, and fetched with refresh
- **THEN** the first call makes one request, the second makes none (read from `raw/`), the refresh makes one, and the stored gzip decompresses to the original whose sha256 is in the manifest
- Verified by `tests/test_bref.py::test_a_file_is_downloaded_once_kept_with_its_checksum_and_reused_while_recent` and `tests/test_slow_hosts.py::test_baseball_reference_is_far_below_the_documented_block_threshold`.

### Requirement: A Refusal Is Never Retried
The host MUST be asked exactly once per request (no retry), a refusal or a web page instead of the data MUST stop the run with a message to wait 24 hours, and nothing MUST be stored from it. A rate below one request a second MUST work in the shared limiter.

#### Scenario: One request after a 429, a clear stop
- **WHEN** the host answers 429, or sends an HTML page
- **THEN** the shared client makes one request, the extractor raises an error that says to stop for 24 hours, and no raw file is stored
- Verified by `tests/test_bref.py::test_the_shared_client_makes_exactly_one_request_when_baseball_reference_refuses`, `tests/test_bref.py::test_a_refusal_or_a_web_page_stops_the_run_and_says_to_wait_a_day`, `tests/test_slow_hosts.py::test_baseball_reference_is_never_retried_after_a_refusal` and `tests/test_slow_hosts.py::test_a_rate_below_one_per_second_is_one_request_per_interval`.

### Requirement: Typed From The Whole File, NULL Is Missing
Schemas MUST be generated from the whole files (`scripts/gen_bref_schemas.py`): exact decimals, integers, text; the word `NULL` MUST become a missing value while `NA` stays a value; an unknown header MUST land in `_extras`; rows MUST be stored as one chunk per season.

#### Scenario: Typing, missing values, drift and chunks
- **WHEN** a file with `NULL` cells, a league code `NA` and an unknown extra column is normalized and ingested
- **THEN** WAR is an exact decimal, `NULL` cells are missing, `NA` is kept, the extra column is in `_extras`, and each season has its own chunk with every row
- Verified by `tests/test_bref.py::test_null_cells_are_null_numbers_are_exact_and_unknown_headers_are_kept`, `tests/test_bref.py::test_the_files_are_registered_with_season_partitions_and_unique_keys`, `tests/test_bref.py::test_ingest_stores_one_chunk_per_season_with_every_row` and `tests/test_bref.py::test_adapter_plans_one_job_and_runs_it`.
