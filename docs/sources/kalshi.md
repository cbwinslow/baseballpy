# Kalshi Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** Kalshi (CFTC-regulated prediction market). Public market data needs no key. Terms of use for redistributing the data are not stated on the pages read; baseballpy shares the code, not the data (see `docs/DATA_LICENSES.md`).
- **Scope (owner decision, `market-sources` M1):** every MLB market. A series is in scope when its ticker contains `MLB` or is one of the league and World Series tickers listed in `sources/kalshi/endpoints.py::MLB_SCOPE`, unless it is tagged Esports. Currently 189 of 4,155 Sports series.
- **Endpoints** (base `https://api.elections.kalshi.com/trade-api/v2`)
  | Purpose | Method + path | Paging |
  | --- | --- | --- |
  | Series list | `GET /series?category=Sports` | none |
  | Events | `GET /events?series_ticker=<T>&limit=200` | `cursor` |
  | Live markets | `GET /markets?series_ticker=<T>&limit=1000` | `cursor` |
  | Archived markets | `GET /historical/markets?series_ticker=<T>&limit=1000` | `cursor` |
- **Live and archived:** settled markets older than `GET /historical/cutoff` (`market_settled_ts`) are only in the archived list; the downloader reads both and keeps, per ticker, the row with the newest `updated_time`.
- **Rate limit:** unsigned 4 requests/second and 4 in flight (pages of 200 to 1,000 records were throttled with HTTP 429 at about 10/second); signed 20 requests/second and 16 in flight (the documented Basic tier is 200 tokens/second at 10 per request; a real run of 781 requests was clean). Set `BASEBALLPY_RATE_KALSHI_RPS` and `BASEBALLPY_RATE_KALSHI_CONCURRENCY` to override; `baseballpy audit speed --host api.elections.kalshi.com` checks the real speeds against the caps.
- **Threads:** one `catalog` job; inside it every in-scope series is fetched on a worker thread (`resolve_concurrency`), and the host caps above decide the real request rate.
- **Keys (optional):** set `BASEBALLPY_KALSHI_KEY_ID` (alias `KALSHI_TOKEN`) and `BASEBALLPY_KALSHI_PRIVATE_KEY_PATH` (alias `KALSHI_PRIVATE_KEY_PATH`) in your environment, or in a dotenv file named by `BASEBALLPY_ENV_FILE`, to sign requests (RSA-PSS, SHA-256). The values are never logged or stored; `.env*`, `*.pem`, `*.key` and `kalshi*.txt` are git-ignored.
- **Storage:** raw JSON pages at `raw/kalshi/<dataset>/<route>-<series>-pNNNNN.json` (sha256 in the manifest); typed Parquet at `processed/kalshi/<dataset>/part-<SERIES>.parquet`, one chunk per series.

## Datasets
| Dataset | View | Upstream route(s) | Key |
| --- | --- | --- | --- |
| `series` | `kalshi_series` | `/series` | `ticker` |
| `events` | `kalshi_events` | `/events` | `event_ticker` |
| `markets` | `kalshi_markets` | `/markets`, `/historical/markets` | `ticker` |

## Schema notes (verified against the real data)
- Schemas are **generated from live probes** (`scripts/gen_kalshi_schemas.py`): every key seen over the sampled pages of every in-scope series gets the narrowest exact type; types never come from column names.
- Prices (`*_dollars`) are `decimal(9,4)` and quantities (`*_fp`) are `decimal(18,2)`: exact, and stored by Parquet as 4- and 8-byte integers. Times are `timestamp[us, UTC]`. Nested values (`price_ranges`, `custom_strike`, `product_metadata`, `tags`, `settlement_sources`) are JSON text.
- A key the probe has not seen goes to `_extras` with a one-time `schema_drift` warning; rerun the generator to type it.

<!-- BEGIN GENERATED:kalshi.description_sources -->
### Description sources

No column descriptions have been written for this source yet.

<!-- END GENERATED:kalshi.description_sources -->

## Dataset reference (generated)

<!-- BEGIN GENERATED:kalshi.events -->
### Dataset: events

Kalshi MLB events (one game or one season-long question per event).

- **View:** `kalshi_events`
- **Processed path:** `processed/kalshi/events/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `event_ticker`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `category` | string | yes | — | TODO |
| `collateral_return_type` | string | yes | — | TODO |
| `event_ticker` | string | yes | — | TODO |
| `exchange_index` | int32 | yes | — | TODO |
| `fee_multiplier_override` | int32 | yes | — | TODO |
| `fee_type_override` | string | yes | — | TODO |
| `last_updated_ts` | timestamp[us, tz=UTC] | yes | — | TODO |
| `mutually_exclusive` | bool | yes | — | TODO |
| `product_metadata` | string | yes | — | TODO |
| `series_ticker` | string | yes | — | TODO |
| `settlement_sources` | string | yes | — | TODO |
| `strike_period` | string | yes | — | TODO |
| `sub_title` | string | yes | — | TODO |
| `title` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:kalshi.events -->

<!-- BEGIN GENERATED:kalshi.markets -->
### Dataset: markets

Kalshi MLB markets (live and archived merged; one row per tradable outcome).

- **View:** `kalshi_markets`
- **Processed path:** `processed/kalshi/markets/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `ticker`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `can_close_early` | bool | yes | — | TODO |
| `cap_strike` | int32 | yes | — | TODO |
| `close_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `created_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `custom_strike` | string | yes | — | TODO |
| `early_close_condition` | string | yes | — | TODO |
| `event_ticker` | string | yes | — | TODO |
| `exchange_index` | int32 | yes | — | TODO |
| `expected_expiration_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `expiration_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `expiration_value` | string | yes | — | TODO |
| `floor_strike` | double | yes | — | TODO |
| `last_price_dollars` | decimal128(9, 4) | yes | — | TODO |
| `latest_expiration_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `market_type` | string | yes | — | TODO |
| `no_ask_dollars` | decimal128(9, 4) | yes | — | TODO |
| `no_bid_dollars` | decimal128(9, 4) | yes | — | TODO |
| `no_sub_title` | string | yes | — | TODO |
| `notional_value_dollars` | decimal128(9, 4) | yes | — | TODO |
| `occurrence_datetime` | timestamp[us, tz=UTC] | yes | — | TODO |
| `open_interest_fp` | decimal128(18, 2) | yes | — | TODO |
| `open_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `previous_price_dollars` | decimal128(9, 4) | yes | — | TODO |
| `previous_yes_ask_dollars` | decimal128(9, 4) | yes | — | TODO |
| `previous_yes_bid_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_level_structure` | string | yes | — | TODO |
| `price_ranges` | string | yes | — | TODO |
| `primary_participant_key` | string | yes | — | TODO |
| `result` | string | yes | — | TODO |
| `rules_primary` | string | yes | — | TODO |
| `rules_secondary` | string | yes | — | TODO |
| `settlement_bounds_type` | string | yes | — | TODO |
| `settlement_timer_seconds` | int32 | yes | — | TODO |
| `settlement_ts` | timestamp[us, tz=UTC] | yes | — | TODO |
| `settlement_value_dollars` | decimal128(9, 4) | yes | — | TODO |
| `status` | string | yes | — | TODO |
| `strike_type` | string | yes | — | TODO |
| `subtitle` | string | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `title` | string | yes | — | TODO |
| `updated_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `volume_24h_fp` | decimal128(18, 2) | yes | — | TODO |
| `volume_fp` | decimal128(18, 2) | yes | — | TODO |
| `yes_ask_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_size_fp` | decimal128(18, 2) | yes | — | TODO |
| `yes_bid_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_size_fp` | decimal128(18, 2) | yes | — | TODO |
| `yes_sub_title` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:kalshi.markets -->

<!-- BEGIN GENERATED:kalshi.series -->
### Dataset: series

Kalshi MLB series (a template for repeated markets, with its fee terms).

- **View:** `kalshi_series`
- **Processed path:** `processed/kalshi/series/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `ticker`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `additional_prohibitions` | string | yes | — | TODO |
| `categories` | string | yes | — | TODO |
| `category` | string | yes | — | TODO |
| `contract_terms_url` | string | yes | — | TODO |
| `contract_url` | string | yes | — | TODO |
| `exchange_index` | int32 | yes | — | TODO |
| `fee_multiplier` | double | yes | — | TODO |
| `fee_type` | string | yes | — | TODO |
| `frequency` | string | yes | — | TODO |
| `last_updated_ts` | timestamp[us, tz=UTC] | yes | — | TODO |
| `settlement_sources` | string | yes | — | TODO |
| `tags` | string | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `title` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:kalshi.series -->
