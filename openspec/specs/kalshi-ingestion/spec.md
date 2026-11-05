# kalshi-ingestion Specification

## Purpose
Kalshi MLB prediction-market data (series, events, markets) is downloaded from the public API into strongly typed Parquet and DuckDB views like every other source: shared HTTP client, per-host caps, audit log, raw bytes kept, nothing dropped.

## Requirements

### Requirement: Scope Is Data, Not Code
The in-scope series MUST come from one declarative rule (`MLB_SCOPE`): a series is in scope when its ticker contains an MLB marker or is a listed league ticker, unless it carries an excluded tag.

#### Scenario: Look-alikes are excluded
- **WHEN** the scope rule is applied to MLB, league-champion, esports and other-sport series
- **THEN** MLB and league series are kept and the esports and NPB series are dropped.
- Verified by `tests/test_kalshi.py::test_the_scope_rule_keeps_mlb_series_and_drops_look_alikes`.

### Requirement: Exact Types
Prices and quantities MUST be exact decimal columns, times MUST be timestamps, nested values MUST be JSON text, and a key without a typed column MUST be kept in `_extras`, never dropped; an uncastable cell MUST be quarantined, never silently NULLed.

#### Scenario: A market is typed exactly
- **WHEN** a market record with decimal text, ISO times and nested values is normalized
- **THEN** prices are `decimal(9,4)`, quantities `decimal(18,2)`, times keep microseconds, nested values are JSON text, and an unknown key lands in `_extras`.
- Verified by `tests/test_kalshi.py::test_a_market_is_typed_exactly_and_unknown_keys_are_kept_not_lost` and `tests/test_market_types.py::test_records_become_typed_columns_and_nothing_is_lost`.

#### Scenario: Decimals are stored as integers and read by DuckDB
- **WHEN** a decimal column is written to Parquet
- **THEN** it is stored as a 4-byte integer and DuckDB reads it as `DECIMAL(9,4)`.
- Verified by `tests/test_market_types.py::test_decimal_columns_are_stored_as_integers_and_duckdb_reads_them`.

### Requirement: Threaded Catalog Ingest Under Host Caps
The catalog ingest MUST fetch each in-scope series on a worker thread, merge live and archived markets keeping the newest row per ticker, store one chunk per series, keep every raw page with its sha256, and let only the shared HTTP client's per-host caps decide the request rate.

#### Scenario: Series on threads, live and archived merged
- **WHEN** the catalog is ingested from stubbed pages
- **THEN** only in-scope series are requested, every page is followed to the end, the newer of a live and an archived row wins, and one Parquet part per series is written.
- Verified by `tests/test_kalshi.py::test_catalog_ingest_runs_series_on_threads_and_merges_live_with_archived` and `tests/test_kalshi.py::test_extractor_follows_the_cursor_and_keeps_every_raw_page`.

#### Scenario: A dataset subset asks only for its routes
- **WHEN** only the events dataset is selected
- **THEN** only the series and events routes are requested and an unknown dataset name raises.
- Verified by `tests/test_kalshi.py::test_a_dataset_subset_only_asks_for_its_routes`.

### Requirement: Adapter Contract
Kalshi MUST meet the lake only through `IngestAdapter`: one season-less `catalog` job whose subset is a job parameter.

#### Scenario: One job, rows reported
- **WHEN** the adapter plans and runs
- **THEN** one `kalshi:catalog` job is planned (a subset adds a `datasets` parameter) and the run reports its rows.
- Verified by `tests/test_kalshi.py::test_the_adapter_plans_one_catalog_job_and_reports_rows`.

### Requirement: Optional Request Signing
Requests MUST be unsigned by default. When the user's environment names a Kalshi key id and an RSA private key file, every attempt MUST be signed freshly (RSA-PSS, SHA-256, timestamp in milliseconds, query not signed), the host's default caps MUST rise to the documented Basic tier, and no credential value may be logged, repr'd or stored.

#### Scenario: The signature verifies and retries are signed again
- **WHEN** a request is signed and a throttled request is retried
- **THEN** the signature verifies with the public key, the query string is not part of the signed text, and the retry carries a new signature.
- Verified by `tests/test_kalshi.py::test_a_signature_verifies_with_the_public_key_and_ignores_the_query` and `tests/test_kalshi.py::test_the_header_hook_signs_every_attempt_and_other_hosts_stay_unsigned`.

#### Scenario: Caps follow the configuration
- **WHEN** no credentials are set, then a key id and key file are set
- **THEN** the defaults are 4 requests a second and 4 in flight, then 20 and 16, and the key id never appears in a repr.
- Verified by `tests/test_kalshi.py::test_signing_is_off_without_a_configured_key_and_on_with_one` and `tests/test_kalshi.py::test_the_kalshi_host_has_its_own_rate_and_in_flight_caps`.
