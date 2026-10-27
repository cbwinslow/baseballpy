# Architecture Decision Records (ADRs)

This document records the architectural decisions, trade-offs, and rationale for `baseballpy`.

---

## ADR 1: OpenSpec & ADR-Driven Engineering Workflow

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball data ingestion involves disparate data sources (Statcast CSV/JSON endpoints, MLB Stats API JSON, Lahman CSVs, Chadwick Git repositories, Retrosheet text event files). Each source has unique edge cases, schemas, and rate limits. Ad-hoc development leads to inconsistent typing, unhandled edge cases, and brittle APIs.

### Decision
1. All changes, features, and schema additions must follow the **OpenSpec** methodology (`openspec/specs/` and `openspec/changes/`).
2. Major design choices, source strategies, rate-limiting policies, and schema definitions must be recorded as immutable ADR entries in this file (`docs/DECISIONS.md`).
3. Specifications are treated as source-of-truth contracts before code implementation.

---

## ADR 2: Decoupled Protocol Architecture (Extract, Parse/Schema, Sink)

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Existing baseball packages (e.g. `pybaseball`) tightly couple HTTP requests, pandas DataFrame transformations, and scraping logic within single functions. This prevents users from writing directly to databases (e.g. DuckDB or PostgreSQL) without materializing entire datasets in RAM as inefficient pandas objects. It also prevents caching, rate-limiting, and testing layers from being mocked cleanly.

### Decision
1. Split ingestion pipeline into three strictly decoupled phases separated by `typing.Protocol`:
   - `Extractor`: Responsible solely for network transport, authentication, HTTP/2 connection pooling, local disk caching, rate limiting, and response validation. Emits raw bytes or JSON streams.
   - `Normalizer / Schema`: Pure transformations converting raw records into strongly-typed `pyarrow.Table` or `pyarrow.RecordBatchReader`.
   - `Sink`: Consumer of Arrow streams responsible for writing to DuckDB, Parquet, Polars, or `dlt` pipeline destinations.
2. Sinks must never initiate network calls; Extractors must never know about storage destinations.

---

## ADR 3: PyArrow as Columnar Interchange Format

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball pitch-by-pitch datasets encompass tens of millions of records (Statcast has ~700,000 pitches per regular season across 90+ attributes). Legacy packages use pandas with Python object types (`VARCHAR` strings for every column), causing multi-gigabyte memory footprints, slow queries, and silent type coercion bugs.

### Decision
1. Standardize on Apache Arrow (`pyarrow`) as the canonical in-memory columnar representation.
2. Mandate explicit physical types for every column:
   - Dates: `pa.date32()` (not string)
   - Timestamps: `pa.timestamp("us", tz="UTC")`
   - Identifiers: `pa.int32()` / `pa.int64()`
   - Measurements / Speeds: `pa.float32()`
   - Counts / Flags: `pa.int16()`, `pa.int8()`, `pa.bool_()`
   - Categoricals: `pa.dictionary(pa.int8(), pa.string())` (e.g., pitch types like `FF`, `SL`, `CH`)
3. Support zero-copy handoffs to Polars (`pl.from_arrow`) and DuckDB (`duckdb.arrow()`) via the Arrow PyCapsule protocol (`__arrow_c_stream__`).

---

## ADR 4: Adaptive Multi-Target Storage via `dlt` and Native Sinks

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Users range from casual analysts running interactive Jupyter notebooks wanting a fast DuckDB table or Polars DataFrame, to data engineering teams loading entire seasons into enterprise data warehouses (PostgreSQL, Snowflake, BigQuery, MotherDuck).

### Decision
1. Provide built-in zero-dependency native sinks for common analytics:
   - `DuckDBSink`: Direct DuckDB table creation or view registration.
   - `ParquetSink`: Partitioned columnar files (`year=YYYY/month=MM/`).
   - `PolarsSink`: Eager DataFrame or LazyFrame output.
2. Integrate `dlt` (data load tool) as the first-class bridge for relational databases and cloud warehouses. `baseballpy` sources will yield Arrow tables as `dlt.resource` generators, allowing zero-copy streaming into PostgreSQL, Snowflake, Databricks, and BigQuery.

---

## ADR 5: Upstream Source Strategy & Rate-Limit Etiquette

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Aggressive scraping of baseball endpoints risks IP bans, 429 Too Many Requests errors, or 504 Gateway Timeouts.
- Baseball Savant (Statcast search) times out or caps results if date ranges exceed ~25,000 pitches.
- MLB Stats API (`statsapi.mlb.com`) is an official API, but subject to burst throttling and occasional 500 errors.
- Retrosheet requires bulk downloads to go through the Fastly CDN GitHub mirror.
- Chadwick player register is distributed as a Git repository / CSV.

### Decision
1. **Statcast Extractor:** Automatically chunk date queries into weekly or daily segments with asynchronous concurrency bounded by `aiolimiter` (e.g. max 5 concurrent requests) and exponential jitter backoff (`tenacity`).
2. **MLB Stats API Extractor:** Implement HTTP client caching with conditional requests (`ETag` and `If-Modified-Since`) to minimize unnecessary bandwidth during game polling.
3. **Retrosheet Extractor:** Mirror `retrosheetpy` policy: default exclusively to the Fastly GitHub CDN (`chadwickbureau/retrosheet`), never scraping `retrosheet.org` directly.
4. **Chadwick Register:** Cache master ID crosswalks locally and update incrementally.

---

## ADR 6: Architecture & Integration Relationship with `retrosheetpy`

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
`retrosheetpy` already exists as a mature, strongly-typed Python library for Retrosheet play-by-play event files, game logs, and rosters, relying on `chadwickpy` (a pure-Python port of the Chadwick C tools).
Crucially, Chadwick tools and `retrosheetpy` are licensed under **GPL-3.0-or-later** because they derive from Chadwick's GPL codebase.
If `baseballpy` absorbs `retrosheetpy`'s code directly into the same repository, `baseballpy` as a whole would be legally bound by GPL-3.0.
Conversely, if `baseballpy` is licensed under **Apache-2.0**, it can maintain a clean separation of concerns and include `retrosheetpy` as an optional dependency (`baseballpy[retrosheet]`) or top-level adapter module (`baseballpy.sources.retrosheet`), preserving Apache-2.0 permissiveness for users who only need Statcast, MLB API, Lahman, and Chadwick.

### Decision
1. **Evaluate Dual Approach:** Maintain `baseballpy` under **Apache-2.0** license.
2. Provide a unified top-level facade `baseballpy.retrosheet` that wraps `retrosheetpy`'s protocols and sink interfaces seamlessly.
3. If users install `baseballpy[retrosheet]`, it pulls in `retrosheetpy` and `chadwickpy` without polluting the license of pure Statcast / MLB API consumers.
4. If a monorepo setup is desired, `retrosheetpy` can be organized as a workspace package under the monorepo root alongside `baseballpy`, `sabermetricspy`, and `chadwickpy`.


---

## ADR 7: Asynchronous Concurrency with Host-Specific Rate Limiting

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Bulk baseball downloads (multi-season Statcast backfills, decade-long game log sweeps, and historical box score queries) require concurrent network requests to finish in acceptable timeframes. However, naive multithreading or unbounded `asyncio.gather()` easily triggers HTTP 429 Too Many Requests, connection resets, or 504 Gateway Timeouts from upstream servers. The MLB Stats API (`statsapi.mlb.com`) can be notably sluggish under burst loads, and Baseball Savant has aggressive connection caps.

### Decision
1. Standardize on `httpx.AsyncClient` with HTTP/2 enabled (`http2=True`) and connection pooling (`limits=httpx.Limits(max_keepalive_connections=20, max_connections=50)`).
2. Implement host-specific token bucket rate limiters via `aiolimiter.AsyncLimiter`:
   - `baseballsavant.mlb.com`: 2.5 requests/second.
   - `statsapi.mlb.com`: 8.0 requests/second.
   - `raw.githubusercontent.com`: 15.0 requests/second.
3. Bound concurrency per extraction task via `asyncio.Semaphore` (configurable via `RateLimitConfig.concurrency`, defaulting to 4 workers).
4. Synchronous API wrappers (`rs.get_statcast()`, `rs.get_schedule()`) will internally execute the async event loop using `asyncio.run()` or delegating to the current running loop, maintaining full interoperability with Jupyter notebooks (`nest_asyncio` / event loop detection).

---

## ADR 8: Real-Time Gameday Streaming & State Diffing Engine

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Researchers, live sports analytics systems, and machine learning models (e.g., real-time win probability, run expectancy, and pitch-level biomechanics) require access to live play-by-play events as games unfold. Polling `statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live` naively results in downloading 2–5MB of redundant JSON per request, re-inserting already-processed pitches into downstream databases, and generating heavy parsing overhead.

### Decision
1. Implement a dedicated `GamedayLiveStreamer` in `baseballpy.sources.mlb_api.stream`.
2. Utilize HTTP conditional headers (`If-None-Match` with `ETag`, and `timecode` parameters) to avoid downloading payloads when game state has not advanced.
3. Compute and track monotonic event sequence watermarks: `(atBatIndex, playEventIndex)`.
4. Only parse and emit new play deltas (pitches, pickoffs, at-bat outcomes, substitutions) rather than full game state trees.
5. Provide a callback / async generator interface: `async for event in stream_live_game(game_pk): yield event` allowing live ML models and dashboard sockets to consume individual pitch objects with sub-second latency.

---

## ADR 9: Schema Drift Resilience & Dead-Letter Quarantine

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Upstream baseball data providers frequently change schemas without advance notice. For example, Baseball Savant introduced bat-tracking metrics (`bat_speed`, `swing_length`) in 2024, arm strength fields in prior seasons, and modified pitch naming conventions. Rigid schemas that fail immediately upon encountering unexpected columns cause full multi-decade historical backfills to crash midway. Conversely, silently dropping invalid or unparseable rows leads to corrupted analytics.

### Decision
1. All PyArrow schemas will employ an evolutionary schema strategy: core historical columns are strictly typed; newly added columns from upstream are detected, coerced to sensible fallback types (or string/float32), and appended.
2. An active schema registry will detect newly discovered columns and log structured alerts (`logger.info("Discovered new upstream column: %s", col_name)`).
3. If an individual record or pitch row is completely unparseable (e.g. malformed JSON or corrupted CSV line), it MUST NEVER be silently discarded. Instead, it is routed to a `DeadLetterQuarantine` with original raw payload, line number, timestamp, and failure reason for auditing.

---

## ADR 10: Multi-Target Sink Threading & Connection Model

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Different analytical sinks have different concurrency and locking characteristics:
- **DuckDB:** Only one process can hold a read-write lock on a database file. Concurrent writes from multiple threads/processes against the same file fail with locking errors.
- **Parquet:** Fully thread-safe when writing partitioned files to distinct subdirectories (`data/season=2024/part-*.parquet`).
- **Polars / Arrow:** In-memory, lock-free.
- **dlt (PostgreSQL / Snowflake / BigQuery):** Manages its own connection pooling, schema migrations, and staging buffers.

### Decision
1. For DuckDB sinks, maintain a single dedicated writer connection or use in-memory staging tables before flushing to disk in bulk.
2. Support Parquet partition writes using PyArrow's multi-threaded native Parquet writer (`pyarrow.dataset.write_dataset`).
3. Sinks must expose a thread-safe / coroutine-safe interface accepting `pyarrow.RecordBatch` streams.


---

## ADR 11: Multi-Engine DataFrame Abstraction via `narwhals`

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Downstream baseball analysts and sabermetricians use varying tools: some strictly use Polars, others use pandas, and high-performance ingestion pipelines use PyArrow. Forcing users into one specific dataframe engine introduces friction or costly memory conversions. Conversely, maintaining separate normalization branches for every dataframe type causes code duplication and maintenance hazards.

### Decision
1. Standardize on `narwhals` as our lightweight, zero-dependency dataframe compatibility layer.
2. Normalization logic and post-processing transformations will use `narwhals` DataFrame/LazyFrame abstractions.
3. Users can retrieve data in their preferred format (`bb.to_polars()`, `bb.to_pandas()`, `bb.to_arrow()`) with zero unnecessary copies.

---

## ADR 12: High-Performance JSON Parsing & Streaming via `msgspec`

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
MLB Stats API feeds (specifically the live Gameday feed `statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live`) produce large, deeply nested JSON payloads (up to 5MB to 15MB per game). Python standard library `json` is a major bottleneck during multi-game polling, and Pydantic validation adds CPU overhead when decoding thousands of pitch and play objects per second.

### Decision
1. Adopt `msgspec` for all JSON decoding, encoding, and struct validation in the MLB API and live streaming components.
2. Define `msgspec.Struct` models for Gameday play events, pitches, and schedule records to achieve single-pass C-speed parsing (10–20x faster than `json`).

---

## ADR 13: Partitioned Cache Hierarchy and Hash-Based Invalidation

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball datasets originate from disparate sources with vastly different update cycles. Statcast historical seasons are immutable; Chadwick player registers update weekly/monthly; MLB live games change every few seconds. A single monolithic cache directory leads to confusion, accidental full purges, and lack of clarity.

### Decision
1. Standardize the root directory at `~/.baseballpy/` (overridable via `BASEBALLPY_HOME` or `BASEBALLPY_CACHE_DIR`).
2. Partition the cache strictly by source:
   - `~/.baseballpy/cache/statcast/`
   - `~/.baseballpy/cache/mlb_api/`
   - `~/.baseballpy/cache/chadwick/`
   - `~/.baseballpy/cache/lahman/`
   - `~/.baseballpy/cache/retrosheet/`
3. Invalidation rules:
   - **Chadwick Register:** Store remote GitHub commit SHA or `ETag`. Check hash before downloading. If unchanged, reuse local Parquet cache.
   - **MLB API Live:** Send `If-None-Match` (`ETag`) to receive `304 Not Modified` on unchanged game states.
   - **Historical Statcast / Retrosheet:** Completed seasons are immutable and never re-downloaded unless explicitly requested via `refresh=True`.

---

## ADR 14: Structured Audit Logging, Execution Benchmarking, and CLI Review Tool

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Data pipelines and analysts require visibility into what was fetched, from where, how fast, how many records were returned, and whether failures or retries occurred. Standard unstructured string logging (`print` or `logging.info`) makes post-run audit analysis and automated metrics tracking difficult.

### Decision
1. Implement a dedicated `AuditLogger` and `@benchmark` utility in `baseballpy.core.audit`.
2. Telemetry events are persisted in an append-only JSON Lines file: `~/.baseballpy/logs/audit.jsonl`.
3. Every operation records:
   - `timestamp_utc`: ISO 8601 timestamp.
   - `operation`: Function or command invoked (e.g. `statcast_search`, `chadwick_register_sync`).
   - `source`: Upstream source identifier.
   - `status`: `SUCCESS`, `FAILURE`, or `RETRY`.
   - `records_count`: Number of records parsed/emitted.
   - `duration_seconds`: Total execution time.
   - `throughput_rps`: Records processed per second.
   - `cache_hit`: Boolean indicating if data was loaded from cache.
   - `endpoint`: Upstream URL or query parameter summary.
   - `destination`: Sink destination path or table.
   - `error`: Error message and stack trace if failed.
4. Provide a rich CLI reviewer tool (`baseballpy audit summary`, `baseballpy audit tail`, `baseballpy audit stats`) to inspect and review execution logs with formatted tables.


---

## ADR 15: Full Data Preservation and Cross-Endpoint Ingestion Completeness

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball analytics pipelines frequently drop columns considered "secondary" or "redundant" (e.g. dropping player names because player IDs are present, dropping spin axes or arm angles because only pitch velocity is desired, or omitting fields from Statcast because they can also be found in MLB Gameday). This creates irreversible data loss, forces researchers to write custom scrapers for omitted attributes, and breaks analytical models relying on comprehensive feature sets (e.g. bat speed, swing length, catcher framing, umpire IDs).

### Decision
1. Ingest **all** available fields, attributes, and metrics provided by any upstream endpoint.
2. Even if an attribute is duplicated across multiple endpoints (e.g., game dates, scores, pitch velocities present in both MLB API and Statcast), each source's schema must preserve the complete raw representation.
3. Schema normalizers will define exhaustive canonical schemas for all known upstream attributes, and dynamic column discovery (ADR 9) will ensure newly introduced metrics are preserved without data truncation.


---

## ADR 16: Upstream Schema & Endpoint Cataloging Policy

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball data providers (Baseball Savant, MLB Stats API, Chadwick Bureau, Lahman, Retrosheet) distribute data with varying, poorly documented, or evolving schemas. Without an authoritative, exhaustive catalog of endpoints, parameters, tables, and column data types inside our repository, agents and developers are forced to guess data types or rely on informal scrapers, leading to inconsistent typing and missing fields.

### Decision
1. Maintain an exhaustive, human-readable and machine-auditable reference catalog for every supported data source in `docs/sources/<source>.md`.
2. Each source document must provide:
   - Complete endpoint URLs, query parameters, and supported filters.
   - Exact rate-limiting thresholds and connection caps.
   - Comprehensive column-by-column schema tables mapping: Column Name, PyArrow Physical Type, Nullable, Raw Example, and Domain Description.
   - Known anomalies, sentinel strings, and era-specific quirks.
3. Every new column or endpoint addition must be reflected in `docs/sources/` during the OpenSpec change cycle.


---

## ADR 17: Two-Phase Atomic Ingestion Gates, Manifest Checkpointing, and Raw/Processed Partitioning

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Bulk network downloads spanning entire seasons or decades are susceptible to interruption (network drops, process cancellation, rate limit pauses, power failure). Naive implementations write directly to the target file; when interrupted, they leave truncated, malformed files that crash subsequent queries or cause silent data omissions. Furthermore, without checkpoint manifests, re-running a job re-downloads gigabytes of already-fetched data.

### Decision
1. Implement a universal `AtomicFileWriter` and `ManifestTracker` in `baseballpy.core.atomic`.
2. All network payloads must be written to temporary `.part` files and atomically renamed via `os.replace()` only after verifying format integrity.
3. Partitioned sources maintain a `manifest.json` recording chunk completion status, record counts, and remote ETags/hashes, enabling instant pause and resume across runs.
4. Adopt a two-tier folder structure (`raw/` and `processed/`) for multi-file historical sources like Retrosheet. Parsers (e.g. `chadwickpy`) read from `raw/` and emit directly into strongly-typed `processed/` Parquet files.


---

## ADR 18: Pydantic Settings Runtime Configuration and Production Smoke Testing Suite

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball researchers, data engineers, and automated agent pipelines operate across wildly different infrastructure setups (local workstations, Docker containers, AWS/GCP cloud runners, Airflow pods, Databricks). Hardcoding cache directories or relying on fragile custom dictionary parsing for rate limits, base directories, and concurrency parameters limits portability. Furthermore, end-to-end multi-season workflows spanning multiple distinct data providers need deterministic regression testing that validates partition isolation, two-phase atomic write guarantees, and cache idempotency under realistic conditions.

### Decision
1. Standardize all subsystem configuration (`CacheConfig`, `AuditConfig`, `RateLimitConfig`, `StreamingConfig`, `QuarantineConfig`, `PipelineConfig`) on `pydantic-settings` (`BaseSettings`).
2. Provide seamless environment variable binding with the `BASEBALLPY_` prefix (e.g. `BASEBALLPY_CACHE_DIR`, `BASEBALLPY_RATE_MAX_CONCURRENCY`, `BASEBALLPY_HOME`), `.env` support, and runtime overrides.
3. Establish a permanent end-to-end smoke testing suite (`tests/test_smoke.py`) validating multi-season Retrosheet extraction, 15-day multi-chunk Statcast pitch searches, simulated network failure recovery with atomic rollback, and cross-source DuckDB/Polars warehouse integration.


---

## ADR 19: Lahman Database Dual-Mode Ingestion and Hex-Sharded Chadwick Register

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
1. **Lahman Database Distribution Limitations:**
   The legacy `chadwickbureau/baseballdatabank` repository is defunct and discontinued at 2021, while the official Society for American Baseball Research (SABR) distribution utilizes `sabr.app.box.com` which employs dynamic session tokens, breaking automated scrapers. 
2. **Chadwick Register Upstream Sharding:**
   Upstream `chadwickbureau/register` deprecated and removed the monolithic `data/people.csv` (returning HTTP 404), replacing it with 16 hexadecimal partitions (`people-0.csv` through `people-f.csv`) alongside metadata files `names.csv` (nicknames and aliases) and `links.csv` (external entity URLs).

### Decision
1. **Lahman Database Dual Ingestion Strategy:**
   - **Mode A (Automated Extraction):** Direct automated extraction from the verified, active GitHub repository `cbwinslow/lahman-database-csv/main/data/` (1871–2025 SABR release covering all 27 tables) with atomic `.part` writing and Parquet compilation.
   - **Mode B (Manual Local Import):** Provide `lahman.import_archive(archive_path)` allowing users to supply an official `.zip` or unzipped folder downloaded from SABR Box. The function validates the CSVs, copies them into `~/.baseballpy/cache/lahman/raw/`, and immediately compiles them into strongly-typed Parquet tables in `processed/`.
   - Provide high-level table accessors: `batting()`, `pitching()`, `people()`, `teams()`, `fielding()`, `salaries()`, `hall_of_fame()`, `allstar()`, etc.
   - Introduce `LahmanTable` enum for type-safe table references.
2. **Sharded Chadwick Register with Active Commit Tracking:**
   - `ChadwickExtractor` downloads all 16 shards (`people-0.csv` through `people-f.csv`) + `names.csv` + `links.csv` using bounded concurrency.
   - `ChadwickNormalizer` concatenates the shards into a single unified `pyarrow.Table` and processes `names.csv` for nickname aliases.
   - Tracks GitHub commit SHAs to detect upstream weekly updates automatically, eliminating unnecessary re-downloads.
   - Introduces `PlayerIdType` enum and `ChadwickRegister.resolve_id(val, from_type, to_type)` for cross-system ID translation.

---

## ADR 20: Comprehensive Domain Enums, Unified Top-Level Namespace, and Telemetry Instrumentation

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
As the `baseballpy` codebase expands to encompass 5 distinct data sources (Statcast, MLB Stats API, Retrosheet, Lahman, Chadwick) and 4 sink engines (DuckDB, Parquet, Polars, dlt), users need first-class developer ergonomics:
1. Hardcoded string literals (e.g. `"bat_tracking"`, `"FF"`, `"R"`, `"ballparks"`, `"append"`, `"snappy"`) risk typographical errors, lack IDE auto-completion, and complicate refactoring.
2. Fragmented deep import paths (e.g. `baseballpy.sources.statcast.leaderboards.get_leaderboard`, `baseballpy.sources.lahman.api.batting`) create friction for data scientists and analysts accustomed to simple top-level imports.
3. Every operation must guarantee structured telemetry tracking in `audit.jsonl` with microsecond UTC timestamps, operation labels, record counts, and zero log clobbering.

### Decision
1. **Comprehensive Subsystem Enums:**
   - Standardize all domain classifications on `enum.StrEnum` and `enum.IntEnum`:
     - **Chadwick:** `PlayerIdType` (`MLBAM`, `RETRO`, `BBREF`, `FANGRAPHS`, `PERSON`, `UUID`, etc.)
     - **Lahman:** `LahmanTable` (27 canonical tables: `BATTING`, `PITCHING`, `PEOPLE`, `TEAMS`, `FIELDING`, etc.)
     - **Statcast:** `StatcastLeaderboard` (11 leaderboards when this ADR was written; now one member per registered variant, see ADR 28), `PitchType` (14 pitch pitch types), `PlayerType` (`BATTER`, `PITCHER`)
     - **Retrosheet:** `RetrosheetReferenceTable` (`BALLPARKS`, `TEAMS`, `BIOFILE`, `EJECTIONS`, `COACHES`, `RELATIVES`), `GameLogType` (`REGULAR`, `ALLSTAR`, `POSTSEASON`, `WORLD_SERIES`), `EventCode` (24 Chadwick play outcome codes)
     - **MLB API:** `GameType` (`REGULAR`, `POSTSEASON`, `SPRING`, `ALLSTAR`), `SportId` (`MLB`, `AAA`, `AA`, etc.), `GameState` (`SCHEDULED`, `LIVE`, `FINAL`, `DELAYED`, etc.)
     - **Sinks:** `WriteMode` (`APPEND`, `REPLACE`), `CompressionCodec` (`SNAPPY`, `ZSTD`, `GZIP`, `NONE`)
   - All string comparisons preserve 100% backward compatibility via `StrEnum` subclassing.
2. **Unified Top-Level Namespace (`baseballpy`):**
   - Expose all core sources, enums, convenience extractors (`statcast`, `get_leaderboard`, `crosswalk`, `batting`, `pitching`, `teams`, `get_boxscore`, `get_schedule`, `events`, `game_logs`), and sinks (`to_duckdb`, `to_parquet`, `to_polars`) directly under `baseballpy`.
3. **Structured Telemetry Invariant:**
   - Ensure every public ingestion, transformation, and sink method executes within `default_audit_logger.track(...)` context to guarantee structured telemetry logging in `audit.jsonl` with zero clobbering.

---

## ADR 21: Consolidated Multi-Season DuckDB Catalog and Hive Partition Organization

* **Date:** 2026-10-26
* **Status:** Accepted

### Context
Baseball data is frequently downloaded across multiple sessions (e.g. fetching 2023 today, 2024 next week, and joining with cumulative Lahman 1871–2025 records). Relational database users (PostgreSQL, MySQL) expect unified single-table queries without manual file merging, clobbering, or managing fragmented folder paths. Furthermore, analysts require cross-source SQL joins (e.g. connecting Statcast pitch metrics to Chadwick crosswalk keys, Lahman biographical records, and Retrosheet boxscores) with high performance and zero storage duplication.

### Decision
1. **Statcast Hive-Partitioning Storage:**
   - Partition Statcast cache files by season: `~/.baseballpy/cache/statcast/processed/season=YYYY/*.parquet`.
   - Retain backward compatibility fallback to read legacy flat parquet chunk files if present.
2. **Consolidated DuckDB Catalog (`baseballpy.database`):**
   - Introduce `BaseballDatabase` with `connect_db()` and `sync_database()`.
   - Automatically registers consolidated DuckDB SQL views with `hive_partitioning = true` and `union_by_name = true` over all Parquet stores:
     - `statcast_pitches`
     - `retrosheet_events`, `retrosheet_boxscores_batting`, `retrosheet_boxscores_pitching`, `retrosheet_gamelogs`
     - `lahman_batting`, `lahman_pitching`, `lahman_people`, `lahman_teams` (all 27 Lahman tables)
     - `chadwick_register`
   - Enables zero-copy, cross-source SQL joins using Chadwick crosswalk keys (`key_mlbam`, `key_retro`, `key_bbref`, `key_fangraphs`).
3. **Homelab & Partition Pruning Guarantees:**
   - Because DuckDB reads Parquet files directly, queries filtering on `WHERE season = YYYY` prune unneeded season partitions without scanning their bytes.
   - Database storage overhead is near-zero because the catalog stores lightweight views pointing directly to the underlying columnar Parquet files.



---

## ADR 22: Hardened Ingestion Core (HttpClient, Freshness, Quarantine, Manifest Locking)
- **Status:** Accepted — implemented (OpenSpec change `harden-ingestion-core`).
- **Context:** Review found unused rate limiters, a never-read TTL, silent failures, a non-thread-safe manifest, and non-conformant sinks.
- **Decision:** All network I/O goes through `core/http.HttpClient`; cache freshness is a first-class `CachePolicy` (historical seasons immutable, current data TTL); unparseable rows go to a dead-letter quarantine; manifests use lockfile + merge-on-save; audit records `CANCELLED`; sinks gain keyed upsert and identifier validation.
- **Consequences:** One place to tune networking; stale-data bugs removed; slight latency cost for lock acquisition; `default_audit_logger` becomes lazy.
- **Alternatives rejected:** per-source retry decorators (duplication, drift); SQLite manifest (extra dependency for little gain over lockfile + JSON).

## ADR 23: Four-Tier Data Lake Layout (raw / processed / quarantine / cache)
- **Status:** Accepted — implemented (OpenSpec change `restructure-data-lake`); layout version 2. Implementation notes: Lahman tables without a strongly-typed schema yet and Savant leaderboards are not in the dataset registry; `BaseballDatabase` discovers them under `processed/` so their data stays queryable until `complete-source-coverage` registers typed schemas. `migrate-layout` keeps one parquet part per v1 file (no concatenation) and drops the regular-season duplicates that v1 `events_all` carried.
- **Context:** `cache/` doubled as the dataset store; sources had inconsistent tiers; datasets shared partitions causing duplicates in views.
- **Decision:** `$BASEBALLPY_HOME/{raw,processed,quarantine,cache/http,databases,logs}`; one dataset per directory; Hive `season=` partitions; `VERSION` file; pinned GitHub refs; registry-driven DuckDB views; `migrate-layout` command.
- **Consequences:** Deleting `cache/` is always safe; reprocessing from `raw/` needs no network; one-time migration for v1 users.
- **Alternatives rejected:** keeping per-source ad-hoc layouts; storing data in DuckDB only (loses columnar file portability and partial re-processing).

## ADR 24: Complete Source Coverage via Registry, Generated Schemas, and `_extras`
- **Status:** Accepted - implemented for all five sources (OpenSpec change `complete-source-coverage`): Lahman, Chadwick and Retrosheet in goal 3; Statcast/Savant and the MLB Stats API (including the live streamer, per-person stats, award recipients and boxscore players) in goal 4. Findings that justified the policy: the hand-written Chadwick `names`/`links` schemas matched neither real file; `"NA"` was silently NULLed (Namibia, Lahman `lgID` NA); the Retrosheet reference schemas were positional guesses; the git tree exposed files nothing ingested (`countries.csv`, `biofile0.csv`, `2020sched-orig.csv`, umpires, discrepancies, schedules); Savant leaderboard routes silently ignore the wrong season parameter; the pitch schema listed two columns Savant never sends and lacked 26 it does; the old name-substring typing truncated floats. See ADR 27-30 for the follow-up decisions.
- **Context:** Only a fraction of upstream endpoints/tables were ingested; schemas dropped fields; docs drifted.
- **Decision:** A `DATASETS` registry drives ingestion, views, docs and tests; schemas are generated from real upstream headers/payloads and committed; unmapped fields are never dropped (`_extras`); GitHub-hosted sources are discovered via the tree API; docs and column dictionaries are generated; `docs/ENDPOINT_CATALOG.md` + live probe track coverage.
- **Consequences:** Adding an endpoint is data + schema + fixture, not new code paths; larger storage footprint (raw JSON retained).
- **Alternatives rejected:** hand-written per-endpoint modules (does not scale to ~120 datasets); storing only flattened typed columns (violates full-preservation mandate).

## ADR 25: Unified Pipeline and Full-Surface CLI
- **Status:** Proposed (OpenSpec change `unified-pipeline-and-cli`).
- **Context:** `Pipeline.run` was mandated but absent; CLI covered one source.
- **Decision:** `Pipeline`/`Job`/`JobResult` compose registry-resolved extractor/normalizer/sink via protocols; CLI offers `ingest`, `catalog`, `db`, `stream`, `docs`, `audit`, `quarantine`, `doctor`, `migrate-layout`, `refs`; signature-level protocol contract tests.
- **Consequences:** One code path for resume/audit/quarantine; `ingest all` possible; `*Source` classes become facades.

## ADR 26: License Position, Dependency Review, CI and Docs Policy
- **Status:** Accepted — license, helpers and dependency decisions implemented; CI/docs/test-policy parts pending (OpenSpec change `repo-hygiene-and-docs-sync`).
- **Context:** `CLAUDE.md` (Apache-2.0) contradicted `LICENSE`/`pyproject` (GPL-3.0-or-later); `chadwickpy` is GPL; several dependencies were unused or under-used; no CI.
- **Decision:** Default to GPL-3.0-or-later consistently (owner may override; fallback tasks documented); isolate GPL imports in one adapter regardless; apply the dependency decision table (remove `fsspec`/`websockets` defaults, split `dlt` extras, adopt `narwhals`/`polars` helpers); add CI with coverage gate, socket guard, live-test separation; generate docs and fail CI on drift.
- **Consequences:** Smaller default install; enforced architecture boundaries by tests; license clarity for downstream users.
- **Alternatives rejected:** relicensing to Apache-2.0 now (requires removing/optionalizing GPL dependency and rewriting Retrosheet parsing).

## ADR 27: Declarative MLB Endpoint Registry with Generic Flattening
- **Status:** Accepted - implemented (`sources/mlb_api/endpoints.py`, `flatten.py`, `generic.py`; generated `mlb_tables.py`, `stat_combos.py`).
- **Context:** Nine hand-written MLB datasets selected a few fields each (violating the full-preservation mandate) and the API has hundreds of endpoint/parameter combinations (stat type x group, standings types, roster types, per-game and per-person resources).
- **Decision:** An endpoint is data (`MlbEndpoint`: path/params template, record path, fan-out scope, key). One flattener turns any JSON payload into records (nested objects -> dotted keys, arrays -> JSON text, wrapper fields carried, id-keyed maps kept as JSON, `*` walks lists and `@` walks dict values); `scripts/gen_mlb_schemas.py` probes each endpoint live, widens types over samples, verifies keys per request and writes strict schemas, fixtures and `docs/mlb_probe.json`. Stat combinations are enumerated from `/v1/statTypes` x `/v1/statGroups` (all groups), never hand-listed. Injected fan-out columns (`game_pk`, `team_id`, `sport_id`, `person_id`) are added when the payload does not repeat them. Hand-written datasets stay as they are; complete-field twins sit beside them.
- **Consequences:** Adding an endpoint is a registry entry + generator run + tests. Wide tables (hundreds of columns) for stats and play events. Schema completeness depends on the generator's samples; unknown fields still land in `_extras` with a drift warning, so nothing is lost.
- **Alternatives rejected:** per-endpoint normalizer classes (does not scale, drifts); typing from the first response only (misses fields other players/seasons have).

## ADR 28: Savant Leaderboard Variants and Season-Parameter Verification
- **Status:** Accepted - implemented (`sources/statcast/lb_catalog.py`, `lb_tables.py`, `scripts/gen_savant_schemas.py`).
- **Context:** Savant leaderboards differ per route in how the season is sent (`year`, `season_start/season_end`, `seasonStart/seasonEnd`, `season`) and some routes silently ignore the wrong one and answer with the current season for every year; some have no CSV and embed rows in the page; the `min` qualifier changes the population.
- **Decision:** One registered dataset per variant (route + fixed params), each with its own generated schema, key and first season. The probe compares payload hashes across seasons to detect ignored season parameters, picks the widest `min`, and records routes with no usable data as `unsupported` with the reason. Embedded-JSON pages are parsed with `lb_parse` (`var/const/let <name>`, list or dict-of-lists). A request that deviates from the canonical parameters returns data but is never persisted into the registered dataset; flat snapshots (pages that ignore the season) are unpartitioned.
- **Consequences:** 34 variants today; a new Savant route is a catalog entry + generator run. Pitch searches follow the same rule: filtered queries are not persisted.
- **Alternatives rejected:** one dataset per route with mixed variants (different schemas and populations in one table); trusting `year=` everywhere (silently stores the wrong season).

## ADR 29: Live Streamer - timestamps + diffPatch with a Resumable Watermark
- **Status:** Accepted - implemented (`sources/mlb_api/stream.py`), verified against recorded real feeds (24 real patches reproduced the full feed's 40 events).
- **Context:** Polling the full feed re-downloads ~1 MB per poll; AGENTS.md section 5 requires monotonic watermarks, timestamp checks, half-inning ends and `StreamExtractorProtocol`; suspended games resume months later.
- **Decision:** Baseline full fetch, then `timestamps` + `diffPatch` applied as RFC 6902 to a local copy (the server answers wide windows with the complete feed, which is accepted); fallback to the full feed (ETag / `metaData.timeStamp`) when a patch is unavailable or misses the announced timestamp. Typed immutable `LiveEvent`s with microsecond UTC timestamps keyed `(game_pk, at_bat_index, event_index)`; `to_arrow` maps them onto the historical `game_feed_play_events` schema; lifecycle (`Delayed` back-off, `Suspended`/`Postponed`/`Cancelled`/`Final` end the stream with a `game_status` event); watermark persisted under `cache/stream/<game_pk>.json`; network errors raised after the shared client's retries, undecodable payloads quarantined.
- **Consequences:** Streams are resumable and idempotent. Not yet exercised against a live game (the season was over); the replay check is the evidence.
- **Alternatives rejected:** full-feed polling only (bandwidth, latency); an in-memory-only watermark (re-emits on resume).

## ADR 30: Bounded Downloads and the No-Data-Left-Behind Sweep
- **Status:** Accepted - implemented across `complete-source-coverage` follow-ups.
- **Context:** The owner's standing rule is that no upstream data is left behind. A review against it found real gaps: stat groups skipped by choice, minor leagues defaulted out (and, found later, minor-league Statcast pitches wrongly declared unreachable: see ADR 31), hand-written datasets that dropped fields, endpoints without a generated schema skipped, boxscore players and `half_inning_end` events missing. It also found the opposite risk: all-time stat pools (`statsSingleSeason fielding` = 191,958 rows, `career fielding` = 51,241) ignore the season and made one request run for minutes.
- **Decision:** (1) Enumerate everything the provider lists (all stat groups, all sports, all standings and roster types) instead of hand-picking. (2) Endpoints with no schema still keep their raw JSON. (3) Heavy all-time pools are skipped by `ingest_season` and fetched once by `ingest_history`; a paginated request announcing more than 20,000 rows is refused after its first page unless explicitly allowed. (4) A per-request 404 for endpoints that opt in (`tolerate_missing`, e.g. awards without recipients) is recorded as an empty part and counted, never retried forever and never hidden. (5) Anything that still cannot be ingested stays registered `unsupported` with probe evidence and is listed in the docs.
- **Consequences:** Larger storage and longer first runs, in exchange for completeness; every omission is explicit and documented. Remaining known gaps are recorded in the OpenSpec tasks (Retrosheet `.EB*` box accounts raw only, `catch_probability` has no usable data).
- **Alternatives rejected:** silently skipping failing or oversized requests; ingesting all-time pools once per season (duplicates ~190k rows per season).

## ADR 31: Minor-League Statcast Pitches Are a Separate Dataset (`minors=true`)
- **Status:** Accepted - implemented (OpenSpec change `statcast-minor-league-pitches`).
- **Context:** ADR 30 and `docs/sources/statcast.md` stated that minor-league pitch search is unreachable because `sportId`/`hfLevel` returned nothing. The probes had used the wrong parameters; `minors=true` returns the minor-league export (119 identical columns, 2021 onwards) and `hfLevel` works only together with it.
- **Decision:** `statcast.pitches_minors` (same schema and key as `pitches`, own raw/processed dataset, view `statcast_pitches_minors`); `StatcastQuery(minors, levels)`; only the unfiltered minors population is persisted; the season window is the union of the sports 11-14 calendars; seasons before 2021 are skipped with a recorded reason.
- **Consequences:** The "unsupported" claim is withdrawn; the lesson is recorded in AGENTS.md section 11: an `unsupported` verdict needs more than the first parameter guesses (search the provider's own UI/requests and documented clients before concluding).
- **Alternatives rejected:** mixing minors into `pitches` (breaks every MLB analysis and the unique key assumptions); adding a derived `level` column (not upstream data).

## ADR 32: Statcast Persisted Windows Lie on a Fixed Grid
- **Status:** Accepted - implemented (OpenSpec change `statcast-chunk-alignment`).
- **Context:** Windows were anchored at the caller's start date and stored as `part-<start>_<end>.parquet`; two overlapping requests wrote different parts holding the same pitches, so the DuckDB view returned them twice (6,042 duplicate keys found in a live check). AGENTS.md section 3 requires idempotent upserts keyed by `(game_pk, at_bat_number, pitch_number)`.
- **Decision:** `grid_windows`: block k of a year = January 1 + k x `chunk_days`, clipped at December 31; every day belongs to exactly one window; `extract` fetches whole windows and filters the result to the requested days; a duplicate-key check runs after persisted extracts.
- **Consequences:** A one-day request downloads up to `chunk_days` days (stored, resumable); part names are grid-aligned; no migration for unaligned parts written before this change (none exist outside scratch lakes).
- **Alternatives rejected:** de-duplicating at read time in the view (hides the problem, costs every query); storing one part per request (unbounded overlap).

## ADR 33: Retrosheet Box-Score Game Accounts (Interim, Empirical Layouts)
- **Status:** Accepted - interim; OpenSpec change `retrosheet-box-accounts` stays open until the owner supplies Retrosheet's `boxfile.txt`.
- **Context:** Retrosheet publishes box-score game accounts (`.EBA`/`.EBN`/`.EBE`/`.EBR`/`.EBF`) that no dataset covered. Their format document (`boxfile.txt`) was not available when the work was done, so record layouts could only be read off real files.
- **Decision:** parse by observed layout, strictly. `id`, `version`, `info`, `start` and `stat,bline` (23 fields) become typed tables (`box_games`, `box_starters`, `box_batting_lines`); every other record (`stat,phline/prline/dline/pline/tline`, `line`, `event,*`, `com`, and any unknown kind) is kept losslessly in `box_records` with its raw line and positional fields. A line whose field count differs from the observed layout raises `BoxParseError` instead of guessing. Column names for the untyped kinds are deliberately not invented.
- **Consequences:** nothing is dropped (a test reconciles every line of real games with the four tables); live check of 1964 gives 1634 games, every one of the 1626 regular-season game-log games present, the 8 extra being the All-Star game and the 7 World Series games. Typing the remaining record kinds waits for `boxfile.txt`.
- **Alternatives rejected:** guessing names for the unseen columns; skipping unrecognised lines.

## ADR 34: Column Descriptions Come From Provider Metadata, With Cited Sources
- **Status:** Accepted - implemented (archived `column-descriptions-from-provider-metadata`); Retrosheet and Savant leaderboard content continues in `column-descriptions-retrosheet-and-leaderboards`.
- **Context:** generated column dictionaries had empty description cells.
- **Decision:** `docs/columns/<source>.json` holds descriptions with a `_sources` map; each cell cites a source key or is flagged `authored`; missing ones render `TODO`; `baseballpy docs coverage` reports per-source counts and a ratchet test (`coverage_baseline.json`) stops regressions. `scripts/build_column_descriptions.py` builds MLB content from `/v1/baseballStats`, `gameTypes`, `pitchTypes`, `positions` (plus authored structural suffix meanings) and Statcast from Savant's `csv-docs` page, Lahman from the SABR `readme2025.txt` and Chadwick from the register README. Where the provider's response key differs from its metadata name, nothing is guessed.
- **Consequences:** coverage 2026-10-27: mlb_api 53.1%, statcast 26.4%, lahman 97.2%, chadwick 72.1%, retrosheet 1.1% (retrosheet.org refused connections, so its format documents were not read).
- **Alternatives rejected:** inventing prose; matching metadata to response keys by similarity.

## ADR 37: The First Catalog Audit Found Wrong `unsupported` Verdicts; Probe Protocol
- **Status:** Accepted - implemented (OpenSpec change `catalog-audit-first-run-fixes`; library and CLI from `catalog-completeness-audit`).
- **Context:** `baseballpy catalog audit` compares provider lists with the registry and re-probes `unsupported` items. Its first run (2026-10-27) found: `active_spin` and `catch_probability` leaderboards wrongly marked unsupported (the first probe added a parameter the route rejects: `min=q`, `type=Fielder`), roster types `allTime`/`coach`/`gameday` and standings type `currentHalf` missing, the `GameType` enum covering 5 of 11 provider game types, and 30 stat types with no data in any generated combination.
- **Decision:** register the two leaderboards with the parameters that work, add the roster/standings types, complete the enum (equality test with `/v1/gameTypes`), keep the audit as the standing check, and propose `mlb-parameterized-stat-types` for the NO_DATA stat types. Probe protocol: bare route first, then add one parameter at a time; every `unsupported` entry records `verified_on` and `tried`; the audit re-probes with default parameters.
- **Consequences:** `unsupported` is a dated claim; a first-run audit on any new source is part of its change. The 26 remaining NO_DATA stat types stay visible until the follow-up lands.
- **Alternatives rejected:** trusting earlier probes; failing the audit on NO_DATA (some stat types legitimately need a player/team/metric parameter).

## ADR 38: Parameterized MLB Stat Types Are Registered as Fan-Out Dimensions
- **Status:** Accepted - implemented (OpenSpec change `mlb-parameterized-stat-types`).
- **Context:** The first audit (ADR 37) listed stat types that returned nothing from a bare request because the provider needs a parameter (`sitCodes`, `metrics`, an opposing player or team id) or a different group.
- **Decision:** discover per stat type and group with the probe protocol (bare route, then one parameter at a time; `scripts/gen_mlb_schemas.py` `probe_param_combos`) and register each productive combination as a `person_season` endpoint with `fan_out` dimensions (`metric`, `opposing_team_id`, `opposing_player_id`) whose values are injected as key columns; `sitCodes` go in one request. 58 parameterized combinations exist (`statSplits`, `statSplitsAdvanced`, `careerStatSplits`, `metricAverages`, `metricLog`, `vsPlayer*`, `vsTeam*`, `projected_Zips*`). Metric and matchup families are opt-in (`families=("metrics","matchups")`; matchups need the opposing ids) because their cross product is large; league-wide situational splits are `heavy`. Twelve stat types stay `unsupported` with `verified_on` and `tried` (e.g. `projectedRos`, `standard`, `advanced`, `tracking`). A request the provider answers with HTTP 500 for every person is recorded in `PROVIDER_ERRORS` with its evidence instead of being swallowed: `metricAverages` + pitching + `barreledBall` (the same metric works for hitting and for `metricLog`).
- **Consequences:** the audit reports no stat type that is neither registered nor `unsupported`. Live check (2024, players 592450 and 543037): every new family returned rows except `vsPlayer5Y`/`vsTeam5Y` for pairs without recent matchups and `metricAverages`/`metricLog` hitting, which the provider answers with empty splits.
- **Alternatives rejected:** fetching every stat type with every parameter by default; swallowing the 500 responses.
