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
- **Trades and candlesticks (opt-in, large):** `baseballpy ingest kalshi --datasets trades,candlesticks` (`--limit N` keeps the newest N dates). Only markets with traded volume are fetched (706,068 of 900,555; the rest have no trades, only quotes). Work is one job per UTC **open date** of a market (a date that never changes; a season-long market can close years from now), newest first, one Parquet chunk and one raw `<dataset>-<date>.jsonl.gz` per dataset and date (a file per request would be about a million files). A date whose markets are all `finalized` and unchanged is skipped on a rerun; a date with a market that can still trade is fetched again; `--refresh` fetches every selected date again.
- **Routes follow the archive cutoff** (`GET /historical/cutoff`): trades created before `trades_created_ts` are archived only, markets settled before `market_settled_ts` have archived candles only (one call per market); newer markets use the live routes. A market spanning the cutoff reads both and keeps each `trade_id` once.
- **Candles are hourly** (`period_interval=60`); the API refuses more than 5,000 candles in one call, so a long market is fetched in windows of at most 4,500 periods and joined by `(ticker, end_period_ts)`. The answer carries both a legacy `price_*` set and a `price_*_dollars` set; both are kept as typed columns (in the first 18,061 candles the legacy set was empty and the dollars set full).
- **Storage:** raw JSON pages at `raw/kalshi/<dataset>/<route>-<series>-pNNNNN.json` (sha256 in the manifest); typed Parquet at `processed/kalshi/<dataset>/part-<SERIES>.parquet`, one chunk per series.

## Datasets
| Dataset | View | Upstream route(s) | Key |
| --- | --- | --- | --- |
| `series` | `kalshi_series` | `/series` | `ticker` |
| `events` | `kalshi_events` | `/events` | `event_ticker` |
| `markets` | `kalshi_markets` | `/markets`, `/historical/markets` | `ticker` |
| `trades` (opt-in) | `kalshi_trades` | `/markets/trades`, `/historical/trades` | `trade_id` |
| `candlesticks` (opt-in) | `kalshi_candlesticks` | `/markets/candlesticks` (up to 100 live markets a call), `/historical/markets/{ticker}/candlesticks` | `ticker`, `end_period_ts` |

## Schema notes (verified against the real data)
- Schemas are **generated from live probes** (`scripts/gen_kalshi_schemas.py`): every key seen over the sampled pages of every in-scope series gets the narrowest exact type; types never come from column names.
- Prices (`*_dollars`) are `decimal(9,4)` and quantities (`*_fp`) are `decimal(18,2)`: exact, and stored by Parquet as 4- and 8-byte integers. Times are `timestamp[us, UTC]`. Nested values (`price_ranges`, `custom_strike`, `product_metadata`, `tags`, `settlement_sources`) are JSON text.
- A key the probe has not seen goes to `_extras` with a one-time `schema_drift` warning; rerun the generator to type it.

<!-- BEGIN GENERATED:kalshi.description_sources -->
### Description sources

No column descriptions have been written for this source yet.

<!-- END GENERATED:kalshi.description_sources -->

## How the data is verified (2026-11-12)
`baseballpy verify-roundtrip kalshi` counts the distinct ids in the raw JSON pages and compares them with the stored rows: `events` 55,197 and `markets` 900,555 are exact. `trades` (110,994,885 distinct trade ids) and `candlesticks` (14,903,320 distinct ticker and end-of-period pairs, read from both the single-market and the batch pages) are exact too. `series` is not counted on purpose: the raw pages list every series (4,156), the table keeps the 189 MLB ones.

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

<!-- BEGIN GENERATED:kalshi.candlesticks -->
### Dataset: candlesticks

Kalshi MLB hourly candlesticks (traded price, bid and ask, volume, open interest).

- **View:** `kalshi_candlesticks`
- **Processed path:** `processed/kalshi/candlesticks/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `ticker`, `end_period_ts`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `end_period_ts` | timestamp[us, tz=UTC] | yes | — | TODO |
| `open_interest` | decimal128(18, 2) | yes | — | TODO |
| `open_interest_fp` | decimal128(18, 2) | yes | — | TODO |
| `price_close` | decimal128(9, 4) | yes | — | TODO |
| `price_close_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_high` | decimal128(9, 4) | yes | — | TODO |
| `price_high_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_low` | decimal128(9, 4) | yes | — | TODO |
| `price_low_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_mean` | decimal128(9, 4) | yes | — | TODO |
| `price_mean_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_open` | decimal128(9, 4) | yes | — | TODO |
| `price_open_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_previous` | decimal128(9, 4) | yes | — | TODO |
| `price_previous_dollars` | decimal128(9, 4) | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `volume` | decimal128(18, 2) | yes | — | TODO |
| `volume_fp` | decimal128(18, 2) | yes | — | TODO |
| `yes_ask_close` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_close_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_high` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_high_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_low` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_low_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_open` | decimal128(9, 4) | yes | — | TODO |
| `yes_ask_open_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_close` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_close_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_high` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_high_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_low` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_low_dollars` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_open` | decimal128(9, 4) | yes | — | TODO |
| `yes_bid_open_dollars` | decimal128(9, 4) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:kalshi.candlesticks -->

<!-- BEGIN GENERATED:kalshi.trades -->
### Dataset: trades

Kalshi MLB trades (every fill of a market that traded: price, size, taker side).

- **View:** `kalshi_trades`
- **Processed path:** `processed/kalshi/trades/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `trade_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `count_fp` | decimal128(18, 2) | yes | — | TODO |
| `created_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `is_block_trade` | bool | yes | — | TODO |
| `no_price_dollars` | decimal128(9, 4) | yes | — | TODO |
| `taker_book_side` | string | yes | — | TODO |
| `taker_outcome_side` | string | yes | — | TODO |
| `taker_side` | string | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `trade_id` | string | yes | — | TODO |
| `yes_price_dollars` | decimal128(9, 4) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:kalshi.trades -->
