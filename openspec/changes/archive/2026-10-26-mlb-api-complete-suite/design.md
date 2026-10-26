# Design: MLB Stats API Complete Suite & Real-Time Streaming

## 1. Concurrency, Network Architecture & Rate Limits
- Base URL: `https://statsapi.mlb.com/api`
- Standardize on `httpx.AsyncClient` with HTTP/2 enabled (`http2=True`) and persistent connection pooling (`Limits(max_keepalive_connections=20, max_connections=50)`).
- Host rate limit: 8.0 requests/second enforced via `aiolimiter.AsyncLimiter`.
- Exponential jitter backoff via `tenacity` on HTTP 429, 500, 502, 503, 504.

## 2. Real-Time Streaming & State Diffing Architecture
Live game feeds can be up to 10MB of JSON per request. Polling naively causes CPU saturation and network waste.
```text
┌──────────────────────────────────────────────┐
│  GamedayLiveStreamer (Async Generator)      │
└──────────────────────┬───────────────────────┘
                       │ GET /api/v1.1/game/{pk}/feed/live
                       │ Headers: If-None-Match: <ETag>
                       ▼
            ┌──────────────────────┐
            │ HTTP 304 Not Mod?    │─── Yes ───► Wait poll_interval (1.5s)
            └──────────┬───────────┘
                       │ No (HTTP 200)
                       ▼
            ┌──────────────────────┐
            │ msgspec.decode()     │  (C-speed struct parsing)
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │ State Diffing Engine │  (Compare against watermark (atBatIndex, eventIndex))
            └──────────┬───────────┘
                       │
                       ▼
         Yield only NEW discrete PlayEvent objects
```

## 3. Physical PyArrow Schemas
All tables coerced to explicit physical types:
- `game_pk`: `pa.int32()`
- Dates: `pa.date32()` or ISO strings
- Timestamps: `pa.timestamp("us", tz="UTC")`
- Coordinates: `pa.float32()`
- Stats / Counts: `pa.int16()`, `pa.int8()`
- Flags: `pa.bool_()`

## 4. Multi-Target Sinks
- `PolarsSink`: Wraps `pl.from_arrow(table)` returning eager `pl.DataFrame` or lazy `pl.LazyFrame`.
- `DltSink`: Wraps Arrow tables as `dlt.resource` to stream directly into PostgreSQL, Snowflake, BigQuery, or MotherDuck with schema auto-evolution.
