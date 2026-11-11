# baseballpy Constitution

## What It Is
`baseballpy` is the next-generation, high-performance, strongly-typed baseball data ingestion layer for Python. It provides researchers, sabermetricians, data engineers, and sports analytics applications with a unified, modern interface to download, cache, normalize, and ingest baseball datasets across all major internet repositories.

**Product mission:** `baseballpy` is a reusable library and CLI distributed on PyPI. It downloads, ingests and maintains historical and real-time MLB data for other people, who query it with DuckDB, PyArrow, Polars, pandas, Parquet, CSV and PostgreSQL. Every user who runs the same workflow MUST get the same results (same rows, schema, names and bytes). The owner's lake is a test oracle, not the deliverable; defects are fixed in the workflow code and the data is rebuilt by it (`AGENTS.md` sections 0 and 15).

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

Module names behind the boxes (2026-10-29): extract and parse live together per provider in
`baseballpy.sources.<source>` (there is no `baseballpy.extract` or `baseballpy.parse` package),
strict Arrow schemas are generated into each source's `tables.py`, orchestration is
`baseballpy.ingest` (`IngestAdapter`, `plan_jobs`, `run_jobs`), storage is `baseballpy.core.stores`,
and sinks are `baseballpy.sinks`. FanGraphs and Baseball-Reference exist as optional, deferred sources
(ADR 102; see The Final Product). The method for working on the project is `docs/agents/WORK_BREAKDOWN.md`.

## The Final Product

A Python library and CLI (PyPI) that gives every user the same tables from the same workflow, for history and for
live data (`AGENTS.md` sections 0 and 15). One pipeline for every source:

```text
provider -> download (one polite HttpClient: rate limits, retries, resumable)
         -> raw (what the provider sent, kept, with sha256)        raw/<source>/...
         -> typed Arrow (registered schema; bad cells quarantined)
         -> processed Parquet                                       processed/<source>/<dataset>/[season=YYYY/]
         -> DuckDB views (views only) + bp.read / bp.sql + export (Parquet, CSV, DuckDB, PostgreSQL, ...)
```

**Target layout (ADR 95 to 97).** Raw answers are stored once in `raw/<source>/season=YYYY/seg-NNNN.parquet`
(one row per distinct URL and body, with its sha256), committed by one line in `segments.json`; processed data is
`seg-NNNN.parquet` per dataset and season (each row names its raw answer in `_raw_sha256`); a source without
seasons keeps one file per dataset. The old layout (`part-*` and `compact-*` files, one raw file per dataset) is
still read and is rebuilt from raw. A user sees the same folders, view names and columns in both.

| Source | Downloaded from | Same results because | Layout today | First command | Proved by |
|---|---|---|---|---|---|
| `statcast` | Baseball Savant CSV: pitches in 5-day windows (bisected at the 25,000-row cap), minor-league pitches, leaderboards | live upstream: every answer kept (raw), deterministic processing | parts and compacted; raw per dataset (gzip) | `baseballpy ingest statcast -s 2024 -d pitches` | lake contract tests (pitches, leaderboards) |
| `retrosheet` | the Chadwick GitHub mirror of Retrosheet at a pinned commit: event, box, roster and schedule files per season, parsed with `chadwickpy` | pinned git SHA (`core/sources_lock.json`) | parts and compacted; raw per file | `baseballpy ingest retrosheet -s 2024` | lake contract tests (season and reference) |
| `chadwick` | the Chadwick register at a pinned commit (sharded people files, names, links, countries) | pinned git SHA | one file per dataset | `baseballpy ingest chadwick` | lake contract test |
| `lahman` | the SABR release mirrored at a pinned commit (`cbwinslow/lahman-database-csv`) or a user's own import | pinned git SHA or the user's file | one file per table | `baseballpy ingest lahman` | lake contract test |
| `mlb_api` | `statsapi.mlb.com`: the endpoint registry (reference, season, per-game, people and history units) and the live game feed streamer | live upstream: every answer kept (raw), deterministic processing | parts and compacted; per-game segments available with `--option storage=segments`; raw per dataset | `baseballpy ingest mlb_api -s 2024` | lake contract tests (games as parts and as segments, every endpoint with a recorded answer) |
| `kalshi`, `polymarket` | prediction-market APIs (optional; deferred, ADR 102) | live upstream, raw kept | parts | `baseballpy ingest kalshi --dry-run` | not yet (B-433) |
| `fangraphs`, `bref` | homelab import of FanGraphs tables; Baseball-Reference WAR files (optional; deferred, ADR 102) | the files imported | parts | `baseballpy ingest bref --dry-run` | not yet (B-433) |

What users can rely on, for every source: `baseballpy ingest <source> --dry-run` says what a command would
download and what is already held; downloads are polite, resumable and skip what is held; `baseballpy catalog
status` and the view `v_season_catalog` say what the lake holds; `bp.read(...)`, `bp.sql(...)` and `baseballpy
export` give DataFrames (Polars, pandas, PyArrow), DuckDB, Parquet, CSV and PostgreSQL; every download is logged
(`logs/audit.jsonl`); nothing is dropped silently (bad cells go to `quarantine/`, unknown columns to `_extras`).

**Definition of done for the whole product.** (1) The lake contract passes for every core source on the target
layout. (2) The real lake is rebuilt from raw with the finished code and compared with the old one (row counts and
keys per dataset and season); old processed files go only after that comparison, raw is never deleted (ADR 107).
(3) For each core source a scratch download for a small window equals the lake (the rebuild check, B-408).
(4) Source pages and column descriptions state their coverage; every decision is an ADR and every behaviour has a
spec scenario with a test. (5) The owner runs the release steps (`docs/RELEASING.md`).

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
