# baseballpy Constitution

## What It Is
`baseballpy` is the next-generation, high-performance, strongly-typed baseball data ingestion layer for Python. It provides researchers, sabermetricians, data engineers, and sports analytics applications with a unified, modern interface to download, cache, normalize, and ingest baseball datasets across all major internet repositories.

Supported and planned data sources:
- **Statcast (Baseball Savant):** Pitch-level tracking data, batted-ball trajectories, expected metrics (xBA, xwOBA, xSLG), sprint speed, arm strength, catcher pop times, and swing tracking.
- **MLB Stats API (`statsapi.mlb.com`):** Official schedule, live Gameday JSON feeds, boxscores, play-by-play, team/player rosters, transactions, draft, and awards.
- **Lahman Baseball Database:** Historical season-level records (1871–present) for batting, pitching, fielding, teams, post-season, and Hall of Fame voting.
- **Chadwick Bureau Names Register (`register`):** Master player ID crosswalk resolving discrepancies between MLBAM, Retrosheet, Baseball-Reference, FanGraphs, and Lahman.
- **Retrosheet:** Play-by-play event files (`.EVA`/`.EVN`), historical game logs, rosters, ballparks, biofiles, and schedules (integrated via `retrosheetpy` and `chadwickpy`).
- **FanGraphs & Baseball-Reference:** Advanced leaderboards, contract tables, and park factors.

## Boundaries & Architecture
```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Data Sources                                  │
│   Statcast (Savant) │ MLB Stats API │ Lahman │ Chadwick │ Retrosheet    │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       baseballpy.extract                                │
│   - Async HTTP/2 Connection Pooling (httpx)                             │
│   - Smart Local Caching (fsspec / hashed payload storage)               │
│   - Rate Limiting (aiolimiter token bucket) & Exponential Backoff       │
│   - Batch Window Chunking (auto-splitting date ranges for Statcast)     │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       baseballpy.parse & schemas                        │
│   - Strict PyArrow Schemas (date32, timestamp_s, int16, float32, bool)  │
│   - Normalization & Data Cleansing (handling missing/sentinel values)   │
│   - Master ID Resolution (Chadwick Person ID mapping)                   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       baseballpy.sink                                   │
│   - DuckDBSink (zero-copy Arrow tables & views, partitioned files)      │
│   - PolarsSink (LazyFrame / DataFrame generation)                       │
│   - ParquetSink (compressed, partitioned on disk)                       │
│   - DltSink (PostgreSQL, BigQuery, Snowflake, MotherDuck pipelines)    │
│   - LiveStreamSink (real-time Gameday state diffs)                      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Architectural Invariants
1. **Strictly Typed Columnar Data, Never Raw Strings:**
   Every dataset must be parsed directly into strongly-typed PyArrow Tables with optimized physical storage types (e.g. `uint16` for pitch speeds, `date32` for game dates, `timestamp[us, tz="UTC"]` for pitch timestamps, dictionary-encoded categorical strings for pitch types).
2. **Decoupled Extract / Parse / Sink via Protocols:**
   The Extract, Parse, and Sink stages communicate exclusively through abstract Python `typing.Protocol` interfaces. Sinks have no knowledge of HTTP protocols; Extractors have no knowledge of database connection strings.
3. **Adaptive Dataframe & Storage Interface:**
   The user chooses the destination: DuckDB, Polars, Parquet, or `dlt` (for PostgreSQL / cloud warehouses). Conversion is zero-copy wherever the Arrow PyCapsule interface is supported.
4. **Reliable Upstream Etiquette:**
   Never hammer endpoints. Statcast queries are chunked into daily or weekly ranges; Retrosheet files are pulled from GitHub raw mirrors; MLB Stats API calls use client caching headers (`ETag`/`If-None-Match`) and respect HTTP 429 rate limits.
5. **Real-Time & Incremental Capability:**
   In addition to bulk historical ETL, the library supports polling or streaming active Gameday events during live games, calculating deltas, and upserting state.
6. **Full Data Preservation Across Endpoints:**
   Always ingest all fields, measurements, and attributes offered by an endpoint without arbitrary truncation, even when overlapping data exists across sources. Downstream users rely on full source fidelity.

## Core Phases & Roadmap
- **Phase 1: Foundation, OpenSpec & Protocols:** Project scaffolding, core `typing.Protocol` definitions for Extractor, Normalizer, and Sink; initial CLI structure.
- **Phase 2: Master Player ID Register (Chadwick):** Fast local caching and Arrow lookup table linking MLBAM ID, Retrosheet ID, Fangraphs ID, Baseball-Reference ID, and Lahman ID.
- **Phase 3: Statcast (Baseball Savant) Ingestion Engine:** Robust chunked search query extractor, comprehensive 90+ column PyArrow schema, handling pitch tracking and Statcast leaderboards.
- **Phase 4: MLB Stats API Engine (Live & Historical):** Schedule, boxscore, and Gameday live feed extractor with streaming change-detection.
- **Phase 5: Lahman & Retrosheet Integration:** Historical Lahman database ingestion (SQLite/CSV to Parquet/DuckDB) and unified Retrosheet facade (via `retrosheetpy`).
- **Phase 6: Multi-Target Sinks:** Production-grade sinks for DuckDB, Parquet, Polars, and `dlt` (Postgres/Cloud).
