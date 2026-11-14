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

- `kalshi_get_candlesticks`: https://docs.kalshi.com/api-reference/market/get-market-candlesticks
- `kalshi_get_event`: https://docs.kalshi.com/api-reference/events/get-event
- `kalshi_get_market`: https://docs.kalshi.com/api-reference/market/get-market
- `kalshi_get_series`: https://docs.kalshi.com/api-reference/market/get-series
- `kalshi_get_trades`: https://docs.kalshi.com/api-reference/market/get-trades

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
| `category` | string | yes | — | Event category; deprecated in favor of the series-level category. (src: kalshi_get_event) |
| `collateral_return_type` | string | yes | — | Collateral-return netting type for this event. (src: kalshi_get_event) |
| `event_ticker` | string | yes | — | Unique identifier for this event. (src: kalshi_get_event) |
| `exchange_index` | int32 | yes | — | Identifier for an exchange shard. (src: kalshi_get_event) |
| `fee_multiplier_override` | int32 | yes | — | Fee multiplier override for this event. (src: kalshi_get_event) |
| `fee_type_override` | string | yes | — | Fee type override for this event. (src: kalshi_get_event) |
| `last_updated_ts` | timestamp[us, tz=UTC] | yes | — | Timestamp of when this event's metadata was last updated. (src: kalshi_get_event) |
| `mutually_exclusive` | bool | yes | — | True only when collateral_return_type is MECNET, meaning at most one market in this event can resolve to yes. (src: kalshi_get_event) |
| `product_metadata` | string | yes | — | Additional metadata for the event. (src: kalshi_get_event) |
| `series_ticker` | string | yes | — | Unique identifier for the series this event belongs to. (src: kalshi_get_event) |
| `settlement_sources` | string | yes | — | The official sources used for the determination of markets within this event. (src: kalshi_get_event) |
| `strike_period` | string | yes | — | The time period this event covers. (src: kalshi_get_event) |
| `sub_title` | string | yes | — | Shortened descriptive title for the event. (src: kalshi_get_event) |
| `title` | string | yes | — | Full title of the event. (src: kalshi_get_event) |
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
| `cap_strike` | int32 | yes | — | Maximum expiration value that leads to a YES settlement. (src: kalshi_get_market) |
| `close_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `created_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `custom_strike` | string | yes | — | Expiration value for each target that leads to a YES settlement. (src: kalshi_get_market) |
| `early_close_condition` | string | yes | — | The condition under which the market can close early. (src: kalshi_get_market) |
| `event_ticker` | string | yes | — | TODO |
| `exchange_index` | int32 | yes | — | Identifier for an exchange shard. (src: kalshi_get_market) |
| `expected_expiration_time` | timestamp[us, tz=UTC] | yes | — | Time when this market is expected to expire. (src: kalshi_get_market) |
| `expiration_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `expiration_value` | string | yes | — | The value that was considered for the settlement. (src: kalshi_get_market) |
| `floor_strike` | double | yes | — | Minimum expiration value that leads to a YES settlement. (src: kalshi_get_market) |
| `last_price_dollars` | decimal128(9, 4) | yes | — | Price for the last traded YES contract on this market in dollars. (src: kalshi_get_market) |
| `latest_expiration_time` | timestamp[us, tz=UTC] | yes | — | Latest possible time for this market to expire. (src: kalshi_get_market) |
| `market_type` | string | yes | — | Identifies the type of market. (src: kalshi_get_market) |
| `no_ask_dollars` | decimal128(9, 4) | yes | — | Price for the lowest NO sell offer on this market in dollars. (src: kalshi_get_market) |
| `no_bid_dollars` | decimal128(9, 4) | yes | — | Price for the highest NO buy offer on this market in dollars. (src: kalshi_get_market) |
| `no_sub_title` | string | yes | — | Deprecated; use yes_sub_title instead. (src: kalshi_get_market) |
| `notional_value_dollars` | decimal128(9, 4) | yes | — | The total value of a single contract at settlement in dollars. (src: kalshi_get_market) |
| `occurrence_datetime` | timestamp[us, tz=UTC] | yes | — | The recorded datetime when the underlying event occurred, if available. (src: kalshi_get_market) |
| `open_interest_fp` | decimal128(18, 2) | yes | — | String representation of the number of contracts bought on this market. (src: kalshi_get_market) |
| `open_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `previous_price_dollars` | decimal128(9, 4) | yes | — | Price for the last traded YES contract on this market a day ago in dollars. (src: kalshi_get_market) |
| `previous_yes_ask_dollars` | decimal128(9, 4) | yes | — | Price for the lowest YES sell offer on this market a day ago in dollars. (src: kalshi_get_market) |
| `previous_yes_bid_dollars` | decimal128(9, 4) | yes | — | Price for the highest YES buy offer on this market a day ago in dollars. (src: kalshi_get_market) |
| `price_level_structure` | string | yes | — | Price level structure for this market, defining price ranges and tick sizes. (src: kalshi_get_market) |
| `price_ranges` | string | yes | — | Valid price ranges for orders on this market. (src: kalshi_get_market) |
| `primary_participant_key` | string | yes | — | TODO |
| `result` | string | yes | — | TODO |
| `rules_primary` | string | yes | — | A plain language description of the most important market terms. (src: kalshi_get_market) |
| `rules_secondary` | string | yes | — | A plain language description of secondary market terms. (src: kalshi_get_market) |
| `settlement_bounds_type` | string | yes | — | Which settlement bounds apply to this market. (src: kalshi_get_market) |
| `settlement_timer_seconds` | int32 | yes | — | The amount of time after determination that the market settles. (src: kalshi_get_market) |
| `settlement_ts` | timestamp[us, tz=UTC] | yes | — | Timestamp when the market was settled. (src: kalshi_get_market) |
| `settlement_value_dollars` | decimal128(9, 4) | yes | — | Only filled after determination. (src: kalshi_get_market) |
| `status` | string | yes | — | The current status of the market in its lifecycle. (src: kalshi_get_market) |
| `strike_type` | string | yes | — | Strike type defines how the market strike is defined and evaluated. (src: kalshi_get_market) |
| `subtitle` | string | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `title` | string | yes | — | TODO |
| `updated_time` | timestamp[us, tz=UTC] | yes | — | Time of the last non-trading metadata update. (src: kalshi_get_market) |
| `volume_24h_fp` | decimal128(18, 2) | yes | — | String representation of the 24h market volume in contracts. (src: kalshi_get_market) |
| `volume_fp` | decimal128(18, 2) | yes | — | String representation of the market volume in contracts. (src: kalshi_get_market) |
| `yes_ask_dollars` | decimal128(9, 4) | yes | — | Price for the lowest YES sell offer on this market in dollars. (src: kalshi_get_market) |
| `yes_ask_size_fp` | decimal128(18, 2) | yes | — | Total contract size of orders to sell YES at the best ask price. (src: kalshi_get_market) |
| `yes_bid_dollars` | decimal128(9, 4) | yes | — | Price for the highest YES buy offer on this market in dollars. (src: kalshi_get_market) |
| `yes_bid_size_fp` | decimal128(18, 2) | yes | — | Total contract size of orders to buy YES at the best bid price. (src: kalshi_get_market) |
| `yes_sub_title` | string | yes | — | Shortened title for the yes side of this market. (src: kalshi_get_market) |
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
| `additional_prohibitions` | string | yes | — | A list of additional trading prohibitions for this series. (src: kalshi_get_series) |
| `categories` | string | yes | — | The list of discovery categories for this series. (src: kalshi_get_series) |
| `category` | string | yes | — | The primary category of this series. (src: kalshi_get_series) |
| `contract_terms_url` | string | yes | — | The URL to the current terms of the contract underlying the series. (src: kalshi_get_series) |
| `contract_url` | string | yes | — | A direct link to the original filing of the contract which underlies the series. (src: kalshi_get_series) |
| `exchange_index` | int32 | yes | — | Identifier for an exchange shard. (src: kalshi_get_series) |
| `fee_multiplier` | double | yes | — | A floating point multiplier applied to the fee calculations. (src: kalshi_get_series) |
| `fee_type` | string | yes | — | A string representing the series' fee structure. (src: kalshi_get_series) |
| `frequency` | string | yes | — | Description of the frequency of the series. (src: kalshi_get_series) |
| `last_updated_ts` | timestamp[us, tz=UTC] | yes | — | Timestamp of when this series' metadata was last updated. (src: kalshi_get_series) |
| `settlement_sources` | string | yes | — | The official sources used for the determination of markets within the series. (src: kalshi_get_series) |
| `tags` | string | yes | — | The subjects that this series relates to. (src: kalshi_get_series) |
| `ticker` | string | yes | — | Ticker that identifies this series. (src: kalshi_get_series) |
| `title` | string | yes | — | Title describing the series. (src: kalshi_get_series) |
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
| `end_period_ts` | timestamp[us, tz=UTC] | yes | — | Unix timestamp for the inclusive end of the candlestick period. (src: kalshi_get_candlesticks) |
| `open_interest` | decimal128(18, 2) | yes | — | TODO |
| `open_interest_fp` | decimal128(18, 2) | yes | — | String representation of the number of contracts bought on the market by end of the candlestick period. (src: kalshi_get_candlesticks) |
| `price_close` | decimal128(9, 4) | yes | — | The close of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_close_dollars` | decimal128(9, 4) | yes | — | The close of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_high` | decimal128(9, 4) | yes | — | The high of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_high_dollars` | decimal128(9, 4) | yes | — | The high of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_low` | decimal128(9, 4) | yes | — | The low of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_low_dollars` | decimal128(9, 4) | yes | — | The low of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_mean` | decimal128(9, 4) | yes | — | TODO |
| `price_mean_dollars` | decimal128(9, 4) | yes | — | TODO |
| `price_open` | decimal128(9, 4) | yes | — | The open of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_open_dollars` | decimal128(9, 4) | yes | — | The open of the open/high/low/close data for trade YES contract prices on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `price_previous` | decimal128(9, 4) | yes | — | TODO |
| `price_previous_dollars` | decimal128(9, 4) | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `volume` | decimal128(18, 2) | yes | — | TODO |
| `volume_fp` | decimal128(18, 2) | yes | — | String representation of the number of contracts bought on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_close` | decimal128(9, 4) | yes | — | The close of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_close_dollars` | decimal128(9, 4) | yes | — | The close of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_high` | decimal128(9, 4) | yes | — | The high of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_high_dollars` | decimal128(9, 4) | yes | — | The high of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_low` | decimal128(9, 4) | yes | — | The low of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_low_dollars` | decimal128(9, 4) | yes | — | The low of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_open` | decimal128(9, 4) | yes | — | The open of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_ask_open_dollars` | decimal128(9, 4) | yes | — | The open of the open/high/low/close data for YES sell offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_close` | decimal128(9, 4) | yes | — | The close of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_close_dollars` | decimal128(9, 4) | yes | — | The close of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_high` | decimal128(9, 4) | yes | — | The high of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_high_dollars` | decimal128(9, 4) | yes | — | The high of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_low` | decimal128(9, 4) | yes | — | The low of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_low_dollars` | decimal128(9, 4) | yes | — | The low of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_open` | decimal128(9, 4) | yes | — | The open of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
| `yes_bid_open_dollars` | decimal128(9, 4) | yes | — | The open of the open/high/low/close data for YES buy offers on the market during the candlestick period. (src: kalshi_get_candlesticks) |
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
| `count_fp` | decimal128(18, 2) | yes | — | String representation of the number of contracts bought or sold in this trade. (src: kalshi_get_trades) |
| `created_time` | timestamp[us, tz=UTC] | yes | — | Timestamp when this trade was executed. (src: kalshi_get_trades) |
| `is_block_trade` | bool | yes | — | True if this trade was matched off-book as a block trade. (src: kalshi_get_trades) |
| `no_price_dollars` | decimal128(9, 4) | yes | — | No price for this trade in dollars. (src: kalshi_get_trades) |
| `taker_book_side` | string | yes | — | Same directional bit as taker_outcome_side in book vocabulary. (src: kalshi_get_trades) |
| `taker_outcome_side` | string | yes | — | The outcome side the taker is positioned for. (src: kalshi_get_trades) |
| `taker_side` | string | yes | — | Deprecated; use taker_outcome_side (or taker_book_side) instead. (src: kalshi_get_trades) |
| `ticker` | string | yes | — | Unique identifier for the market. (src: kalshi_get_trades) |
| `trade_id` | string | yes | — | Unique identifier for this trade. (src: kalshi_get_trades) |
| `yes_price_dollars` | decimal128(9, 4) | yes | — | Yes price for this trade in dollars. (src: kalshi_get_trades) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:kalshi.trades -->
