# Polymarket Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** Polymarket (prediction market). Public market data needs no key. Terms of use for redistributing the data are not stated on the pages read; baseballpy shares the code, not the data (see `docs/DATA_LICENSES.md`).
- **Scope (owner decision, `market-sources` M1):** every MLB market. The sport is looked up in `GET /sports` (`sport = "mlb"`, its `primaryTagId`, 100381 when probed), never hard-coded; events are listed by that tag. At probe time: 11,653 events, 233,923 markets, 467,846 outcome tokens, 2024-08 to 2026-11.
- **Endpoints**
  | Purpose | Host | Method + path | Paging |
  | --- | --- | --- | --- |
  | Sports list (tag id) | `gamma-api.polymarket.com` | `GET /sports` | none |
  | Events with their markets | `gamma-api.polymarket.com` | `GET /events/keyset?tag_id=<id>&limit=100` | `after_cursor` = the answer's `next_cursor` |
  | Price history of one token | `clob.polymarket.com` | `GET /prices-history?market=<token id>&startTs&endTs&fidelity=60` | explicit window |
- **Why keyset:** the offset route `GET /events` stops at about 2,100 rows (`offset too large, use /events/keyset`); the keyset route answers 100 events a page and reached all 11,653 in 117 requests (about 66 seconds).
- **Price history windows:** `startTs` and `endTs` are required for closed markets; a window longer than 15 days is refused with HTTP 400 (15 days answered, 16 refused), so a market's life is cut into windows of at most 14 days. History is hourly (`fidelity=60`, minutes). The route takes one token per call; the batch route (`POST /batch-prices-history`, up to 20 tokens) is not used because the shared client sends GET requests only.
- **Trades (not ingested yet):** the old `data-api.polymarket.com/trades` route is retired (HTTP 410); the v2 route is `GET /v2/trades?condition=<condition id>&limit=1000` and answers `{data, pagination{limit, offset, has_more, next_cursor}}` with wallet addresses and profile names of the traders. It is recorded here as probe evidence and is a later opt-in dataset (personal data to decide on first).
- **Rate limit:** the documented limits are sliding 10-second windows (over-limit requests are throttled and queued): Gamma `/events` 500, `/markets` 300, CLOB `/prices-history` 1,000, Data API `/trades` 200. Defaults are 80% of the lowest limit used per host: `gamma-api.polymarket.com` 24 requests/second (8 in flight), `clob.polymarket.com` 80 (16), `data-api.polymarket.com` 16 (8). Set `BASEBALLPY_RATE_POLYMARKET_GAMMA_RPS`, `BASEBALLPY_RATE_POLYMARKET_CLOB_RPS` and `BASEBALLPY_RATE_POLYMARKET_DATA_RPS` to override; `baseballpy audit speed` checks the real speeds. Throttled requests are delayed, not refused, so p95 latency is the signal to watch.
- **Threads:** one `catalog` job (the events list is one cursor chain, about a minute); the `prices` dataset is opt-in and one job per UTC **start date** of a market (a date that never changes), newest first, run on the runner's worker threads; inside a job the tokens are fetched on up to 8 threads. The host caps decide the real request rate.
- **Prices (opt-in, large):** `baseballpy ingest polymarket --datasets prices` (`--limit N` keeps the newest N dates). Only markets with traded volume are fetched. One Parquet chunk per start date and one raw `prices-<date>.jsonl.gz` (a file per request would be hundreds of thousands of files). A date whose markets are all closed and unchanged is skipped on a rerun; a date with an open market is fetched again; `--refresh` fetches every selected date again.
- **Storage:** raw answers at `raw/polymarket/<dataset>/<name>.jsonl.gz` (sha256 in the manifest); typed Parquet at `processed/polymarket/<dataset>/part-<chunk>.parquet` (catalog: one chunk per month an event started; prices: one chunk per market start date).

## Datasets
| Dataset | View | Upstream route(s) | Key |
| --- | --- | --- | --- |
| `events` | `polymarket_events` | `/events/keyset` (the event without its markets) | `id` |
| `markets` | `polymarket_markets` | `/events/keyset` (the markets inside each event, plus `event_id`) | `id` |
| `outcomes` | `polymarket_outcomes` | `/events/keyset` (`outcomes`, `clobTokenIds`, `outcomePrices` of each market, one row per outcome) | `market_id`, `outcome_index` |
| `prices` (opt-in) | `polymarket_prices` | `/prices-history` | `token_id`, `t` |

## Schema notes (verified against the real data)
- Schemas are **generated from live probes** (`scripts/gen_polymarket_schemas.py`, which crawls the whole catalog and samples price history): every key seen gets the narrowest exact type; types never come from column names. Run `uv run python scripts/gen_polymarket_schemas.py --check` to see whether `tables.py` is stale.
- Keys arrive in `camelCase` and are stored as `snake_case` (`clobTokenIds` is `clob_token_ids`). Prices and quantities written as decimals are exact `decimal` columns; times are `timestamp[us, UTC]`; the lists Polymarket sends as JSON text (`outcomes`, `clobTokenIds`, `outcomePrices`) and nested values (`tags`, `series`) stay JSON text. Outcome token ids are 77-digit numbers and are kept as text.
- A key the probe has not seen goes to `_extras` with a one-time `schema_drift` warning; rerun the generator to type it.

## How the data is verified (2026-11-12)
`baseballpy verify-roundtrip polymarket` counts the distinct ids in the raw JSON pages and compares them with the stored rows: `events` 11,653 and `markets` 233,923 (nested in the event pages) are exact. `outcomes` (467,846: every entry of each market's outcome list) and `prices` (16,043,908 distinct token and time pairs) are exact too.

## Dataset reference (generated)

<!-- BEGIN GENERATED:polymarket.description_sources -->
### Description sources

No column descriptions have been written for this source yet.

<!-- END GENERATED:polymarket.description_sources -->

<!-- BEGIN GENERATED:polymarket.events -->
### Dataset: events

Polymarket MLB events (one game or one season-long question per event).

- **View:** `polymarket_events`
- **Processed path:** `processed/polymarket/events/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `active` | bool | yes | — | TODO |
| `archived` | bool | yes | — | TODO |
| `automatically_active` | bool | yes | — | TODO |
| `automatically_resolved` | bool | yes | — | TODO |
| `closed` | bool | yes | — | TODO |
| `closed_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `comment_count` | int32 | yes | — | TODO |
| `competitive` | double | yes | — | TODO |
| `created_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `created_by` | int32 | yes | — | TODO |
| `creation_date` | timestamp[us, tz=UTC] | yes | — | TODO |
| `cumulative_markets` | bool | yes | — | TODO |
| `cyom` | bool | yes | — | TODO |
| `deploying` | bool | yes | — | TODO |
| `deploying_timestamp` | timestamp[us, tz=UTC] | yes | — | TODO |
| `description` | string | yes | — | TODO |
| `elapsed` | string | yes | — | TODO |
| `enable_neg_risk` | bool | yes | — | TODO |
| `enable_order_book` | bool | yes | — | TODO |
| `end_date` | timestamp[us, tz=UTC] | yes | — | TODO |
| `ended` | bool | yes | — | TODO |
| `estimate_value` | bool | yes | — | TODO |
| `event_date` | date32[day] | yes | — | TODO |
| `event_metadata` | string | yes | — | TODO |
| `event_week` | int32 | yes | — | TODO |
| `featured` | bool | yes | — | TODO |
| `featured_order` | int32 | yes | — | TODO |
| `finished_timestamp` | timestamp[us, tz=UTC] | yes | — | TODO |
| `game_id` | int32 | yes | — | TODO |
| `gmp_chart_mode` | string | yes | — | TODO |
| `icon` | string | yes | — | TODO |
| `id` | int32 | yes | — | TODO |
| `image` | string | yes | — | TODO |
| `liquidity` | decimal128(18, 5) | yes | — | TODO |
| `liquidity_amm` | int32 | yes | — | TODO |
| `liquidity_clob` | decimal128(18, 5) | yes | — | TODO |
| `live` | bool | yes | — | TODO |
| `neg_risk` | bool | yes | — | TODO |
| `neg_risk_augmented` | bool | yes | — | TODO |
| `neg_risk_market_id` | string | yes | — | TODO |
| `new` | bool | yes | — | TODO |
| `open_interest` | double | yes | — | TODO |
| `parent_event_id` | int32 | yes | — | TODO |
| `pending_deployment` | bool | yes | — | TODO |
| `period` | string | yes | — | TODO |
| `resolution_source` | string | yes | — | TODO |
| `restricted` | bool | yes | — | TODO |
| `score` | string | yes | — | TODO |
| `series` | string | yes | — | TODO |
| `series_slug` | string | yes | — | TODO |
| `show_all_outcomes` | bool | yes | — | TODO |
| `show_market_images` | bool | yes | — | TODO |
| `slug` | string | yes | — | TODO |
| `sort_by` | string | yes | — | TODO |
| `sport` | string | yes | — | TODO |
| `start_date` | timestamp[us, tz=UTC] | yes | — | TODO |
| `start_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `tags` | string | yes | — | TODO |
| `teams` | string | yes | — | TODO |
| `ticker` | string | yes | — | TODO |
| `title` | string | yes | — | TODO |
| `updated_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `version` | string | yes | — | TODO |
| `volume` | double | yes | — | TODO |
| `volume1mo` | double | yes | — | TODO |
| `volume1wk` | double | yes | — | TODO |
| `volume1yr` | double | yes | — | TODO |
| `volume24hr` | double | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:polymarket.events -->

<!-- BEGIN GENERATED:polymarket.markets -->
### Dataset: markets

Polymarket MLB markets (one row per question, with its token ids and volume).

- **View:** `polymarket_markets`
- **Processed path:** `processed/polymarket/markets/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `accepting_orders` | bool | yes | — | TODO |
| `accepting_orders_timestamp` | timestamp[us, tz=UTC] | yes | — | TODO |
| `active` | bool | yes | — | TODO |
| `approved` | bool | yes | — | TODO |
| `archived` | bool | yes | — | TODO |
| `automatically_active` | bool | yes | — | TODO |
| `automatically_resolved` | bool | yes | — | TODO |
| `best_ask` | decimal128(9, 3) | yes | — | TODO |
| `best_bid` | decimal128(9, 3) | yes | — | TODO |
| `clear_book_on_start` | bool | yes | — | TODO |
| `clob_rewards` | string | yes | — | TODO |
| `clob_token_ids` | string | yes | — | TODO |
| `closed` | bool | yes | — | TODO |
| `closed_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `combo_status` | string | yes | — | TODO |
| `competitive` | double | yes | — | TODO |
| `condition_id` | string | yes | — | TODO |
| `created_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `custom_liveness` | int32 | yes | — | TODO |
| `cyom` | bool | yes | — | TODO |
| `deploying` | bool | yes | — | TODO |
| `deploying_timestamp` | timestamp[us, tz=UTC] | yes | — | TODO |
| `description` | string | yes | — | TODO |
| `enable_order_book` | bool | yes | — | TODO |
| `end_date` | timestamp[us, tz=UTC] | yes | — | TODO |
| `end_date_iso` | date32[day] | yes | — | TODO |
| `event_id` | int32 | yes | — | TODO |
| `fallback_resolution_type` | string | yes | — | TODO |
| `featured` | bool | yes | — | TODO |
| `fee` | int64 | yes | — | TODO |
| `fee_schedule` | string | yes | — | TODO |
| `fee_type` | string | yes | — | TODO |
| `fees_enabled` | bool | yes | — | TODO |
| `fpmm_live` | bool | yes | — | TODO |
| `funded` | bool | yes | — | TODO |
| `game_start_time` | timestamp[us, tz=UTC] | yes | — | TODO |
| `group_item_threshold` | int32 | yes | — | TODO |
| `group_item_title` | string | yes | — | TODO |
| `has_reviewed_dates` | bool | yes | — | TODO |
| `holding_rewards_enabled` | bool | yes | — | TODO |
| `icon` | string | yes | — | TODO |
| `id` | int32 | yes | — | TODO |
| `image` | string | yes | — | TODO |
| `last_trade_price` | decimal128(9, 3) | yes | — | TODO |
| `line` | decimal128(9, 1) | yes | — | TODO |
| `liquidity` | decimal128(18, 5) | yes | — | TODO |
| `liquidity_amm` | int32 | yes | — | TODO |
| `liquidity_clob` | decimal128(18, 5) | yes | — | TODO |
| `liquidity_num` | decimal128(18, 5) | yes | — | TODO |
| `maker_base_fee` | int32 | yes | — | TODO |
| `manual_activation` | bool | yes | — | TODO |
| `market_maker_address` | string | yes | — | TODO |
| `market_metadata` | string | yes | — | TODO |
| `neg_risk` | bool | yes | — | TODO |
| `neg_risk_market_id` | string | yes | — | TODO |
| `neg_risk_other` | bool | yes | — | TODO |
| `neg_risk_request_id` | string | yes | — | TODO |
| `new` | bool | yes | — | TODO |
| `notifications_enabled` | bool | yes | — | TODO |
| `one_day_price_change` | decimal128(9, 4) | yes | — | TODO |
| `one_hour_price_change` | decimal128(9, 4) | yes | — | TODO |
| `one_month_price_change` | decimal128(9, 4) | yes | — | TODO |
| `one_week_price_change` | decimal128(9, 4) | yes | — | TODO |
| `one_year_price_change` | int32 | yes | — | TODO |
| `order_min_size` | int32 | yes | — | TODO |
| `order_price_min_tick_size` | decimal128(9, 3) | yes | — | TODO |
| `outcome_prices` | string | yes | — | TODO |
| `outcomes` | string | yes | — | TODO |
| `pending_deployment` | bool | yes | — | TODO |
| `position_ids` | string | yes | — | TODO |
| `question` | string | yes | — | TODO |
| `question_id` | string | yes | — | TODO |
| `ready` | bool | yes | — | TODO |
| `ready_for_cron` | bool | yes | — | TODO |
| `resolution_mechanism` | string | yes | — | TODO |
| `resolution_source` | string | yes | — | TODO |
| `resolved_by` | string | yes | — | TODO |
| `restricted` | bool | yes | — | TODO |
| `rewards_max_spread` | decimal128(9, 1) | yes | — | TODO |
| `rewards_min_size` | int32 | yes | — | TODO |
| `rfq_enabled` | bool | yes | — | TODO |
| `seconds_delay` | int32 | yes | — | TODO |
| `sent_discord` | bool | yes | — | TODO |
| `series_color` | string | yes | — | TODO |
| `show_gmp_outcome` | bool | yes | — | TODO |
| `show_gmp_series` | bool | yes | — | TODO |
| `slug` | string | yes | — | TODO |
| `sports_market_type` | string | yes | — | TODO |
| `spread` | decimal128(9, 3) | yes | — | TODO |
| `start_date` | timestamp[us, tz=UTC] | yes | — | TODO |
| `start_date_iso` | date32[day] | yes | — | TODO |
| `submitted_by` | string | yes | — | TODO |
| `taker_base_fee` | int32 | yes | — | TODO |
| `trading_eligible` | bool | yes | — | TODO |
| `uma_bond` | int32 | yes | — | TODO |
| `uma_end_date` | string | yes | — | TODO |
| `uma_end_date_iso` | date32[day] | yes | — | TODO |
| `uma_resolution_status` | string | yes | — | TODO |
| `uma_resolution_statuses` | string | yes | — | TODO |
| `uma_reward` | decimal128(9, 1) | yes | — | TODO |
| `updated_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `version` | string | yes | — | TODO |
| `volume` | decimal128(38, 16) | yes | — | TODO |
| `volume1mo` | double | yes | — | TODO |
| `volume1mo_amm` | int32 | yes | — | TODO |
| `volume1mo_clob` | double | yes | — | TODO |
| `volume1wk` | double | yes | — | TODO |
| `volume1wk_amm` | int32 | yes | — | TODO |
| `volume1wk_clob` | double | yes | — | TODO |
| `volume1yr` | double | yes | — | TODO |
| `volume1yr_amm` | int32 | yes | — | TODO |
| `volume1yr_clob` | double | yes | — | TODO |
| `volume24hr` | double | yes | — | TODO |
| `volume24hr_amm` | int32 | yes | — | TODO |
| `volume24hr_clob` | double | yes | — | TODO |
| `volume_amm` | int32 | yes | — | TODO |
| `volume_clob` | double | yes | — | TODO |
| `volume_num` | double | yes | — | TODO |
| `wide_format` | bool | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:polymarket.markets -->

<!-- BEGIN GENERATED:polymarket.outcomes -->
### Dataset: outcomes

Polymarket MLB outcomes (one row per outcome token of a market: label, token id, last price).

- **View:** `polymarket_outcomes`
- **Processed path:** `processed/polymarket/outcomes/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `market_id`, `outcome_index`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `condition_id` | string | yes | — | TODO |
| `market_id` | int32 | yes | — | TODO |
| `outcome` | string | yes | — | TODO |
| `outcome_index` | int32 | yes | — | TODO |
| `price` | decimal128(9, 4) | yes | — | TODO |
| `token_id` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:polymarket.outcomes -->

<!-- BEGIN GENERATED:polymarket.prices -->
### Dataset: prices

Polymarket MLB hourly price history (one price per outcome token and hour).

- **View:** `polymarket_prices`
- **Processed path:** `processed/polymarket/prices/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `token_id`, `t`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `p` | decimal128(9, 4) | yes | — | TODO |
| `t` | timestamp[us, tz=UTC] | yes | — | TODO |
| `token_id` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:polymarket.prices -->
