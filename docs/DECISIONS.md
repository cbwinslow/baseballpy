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
* **Status:** Accepted; the license decision is superseded by ADR 26 (GPL-3.0-or-later)

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
- **Status:** Implemented 2026-10-28 (OpenSpec change `unified-pipeline-and-cli`, design sections 8-10; archived; spec `cli-and-ingest`).
- **Context:** `Pipeline.run` was mandated but absent; CLI covered one source. The per-source orchestrators already existed and were verified, so the pipeline layers on them instead of replacing them.
- **Decision:** `Pipeline`/`Job`/`JobResult` compose registry-resolved extractor/normalizer/sink via protocols; CLI offers `ingest`, `catalog`, `db`, `stream`, `docs`, `audit`, `quarantine`, `doctor`, `migrate-layout`, `refs`; signature-level protocol contract tests.
- **As built:** `baseballpy.ingest` (source-agnostic `Job`/`JobResult`/`RunReport`, `parse_seasons`, `IngestAdapter` Protocol + registry, bounded-concurrency runner that collects failures and maps Ctrl-C to CANCELLED) plus one thin adapter per source under `sources/<source>/adapter.py`; commands `ingest`, `catalog status`, `doctor` in `cli_ingest.py`. Adding a source is one adapter and one registration; the runner and CLI never import a concrete source (tested). First delegated code (agy), reviewed by Claude.
- **Final shape:** the planned `Pipeline` class and a `cli/` package were not built: the adapter layer plus one registration module per command group (`cli_ingest`, `cli_catalog`, `cli_db`, `cli_stream`, `cli_quarantine`) covers the same ground with less coupling (compare dlt's per-object command groups). Added after the first cut: `db views|query|shell` (read-only), `stream` (JSONL and idempotent DuckDB upsert), `quarantine list|show` (no `replay`: a record does not carry the normalizer that rejected it), `audit --source --status --since`, `catalog list|show` and `source:dataset` filters, an opt-in dotenv file (`BASEBALLPY_ENV_FILE`), and `docs/CLI.md` generated from the click tree.
- **Consequences:** One code path for resume/audit/quarantine at job level; `ingest all` possible; dataset filters are per source (a name unknown to one adapter is a usage error), so cross-source `--datasets` uses `source:dataset`. Resume relies on per-chunk files and manifests, so a hard kill loses at most the chunk in flight (verified live).

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
- **Consequences:** coverage 2026-10-27: mlb_api 56.7%, statcast 26.4%, lahman 97.2%, chadwick 72.1%, retrosheet 66.9% (event, daily-split and substitution fields from the Chadwick tool documents; retrosheet.org refused connections, so Retrosheet's own format documents were not read).
- **Alternatives rejected:** inventing prose; matching metadata to response keys by similarity.

## ADR 35: A Completeness Audit Compares Every Provider List With the Registry
- **Status:** Accepted (change `catalog-completeness-audit`, implemented 2026-10-27/28; written down 2026-10-29 when the change was closed).
- **Context:** three coverage gaps found late (hand-picked stat groups, minor leagues defaulted out, minor-league pitches wrongly `unsupported`) were completeness defects no test caught.
- **Decision:** `baseballpy catalog audit [--source S] [--json]` re-runs the cheap provider probes and reports MISSING (provider lists it, registry lacks it), STALE (registry has it, provider dropped it), REVIVED (an `unsupported` item now returns data) and DRIFT; exit code is non-zero on MISSING or REVIVED. Every `unsupported` entry stores `verified_on` and `tried`. A weekly job in `live.yml` runs the audit and opens or updates one issue.
- **Consequences:** coverage claims are checked against the providers' own lists; the first run (ADR 37) found wrong verdicts. Not verified: a real run of the weekly job on GitHub (Actions not enabled by the owner).
- **Alternatives rejected:** relying on the generators being run by hand; automatic fixing of findings.

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

## ADR 39: The IngestAdapter Is the Enforced Source Boundary; Extractor/Normalizer Protocols Are Optional
- **Status:** Accepted (OpenSpec change `unified-pipeline-and-cli`, design section 9); amends ADR 2 and ADR 25.
- **Context:** `ExtractorProtocol`/`NormalizerProtocol` were mandated as the boundary between sources and everything else, but nothing consumes extractors or normalizers polymorphically: no function takes them, the extractor signature is `(*args, **kwargs)` so a signature test cannot fail, and the declared return type does not match what extractors return. Only two of six extractors and two of six normalizers satisfy them; the others serve many datasets (27 Lahman tables, hundreds of MLB endpoints, 34 leaderboards) where a single `schema` has no meaning. The pipeline that does consume sources goes through `IngestAdapter` (ADR 25 as built).
- **Decision:** enforce the contracts that are consumed: `SinkProtocol`, `StreamExtractorProtocol`, `LiveEventConsumerProtocol` and `IngestAdapter`, plus the import-boundary tests. Keep `ExtractorProtocol`/`NormalizerProtocol` in `core/protocols.py` as documented optional guides for single-dataset sources. New contract test `tests/test_ingest_contract.py`: every source that owns datasets has a registered adapter satisfying `IngestAdapter` whose planned jobs carry its name.
- **Consequences:** no wrapper code written only to satisfy an unused Protocol. Limitation: adapters do not declare which datasets their tasks cover, so the test cannot prove each dataset is reachable from some job; that would need a declared task-to-dataset mapping (not invented here).
- **Alternatives rejected:** multi-dataset extractor/normalizer Protocols plus adapting eight classes (new code and tests with no consumer and no breakage prevented).


## ADR 40: The Default User-Agent Is the One pybaseball Sends; It Is Overridable
- **Status:** Accepted (owner instruction, 2026-10-28).
- **Context:** after about three hours of continuous requests `statsapi.mlb.com` answered HTTP 500 and then 403 to `baseballpy (+https://github.com/cbwinslow/baseballpy)` on every route, from this PC and from the homelab, while `python-requests/2.32.3`, `baseballpy/0.1`, `python-httpx/0.27` and `curl/8` got 200 for the same URLs and Savant was unaffected. The block lasted more than two hours of retests. Search found no statement from MLB.
- **Decision:** the default agent of `HttpClient` is `python-requests/2.32.3`, what pybaseball (the most used client of these hosts) sends; `BASEBALLPY_USER_AGENT` or the `user_agent` argument override it.
- **Consequences:** MLB can no longer tell this client apart from other `requests` users, so its politeness rests on the rate limits in `core/http.py`, which are unchanged. If MLB publishes an identification rule, set the variable to follow it. It is the owner's decision and risk; if the host blocks that string too, the override is the escape hatch.
- **Alternatives rejected:** waiting (the block did not lift); a browser agent (impersonating a browser is a bigger step than reusing an API client's own string).

## ADR 41: The Retrosheet CSV Bundles Are Not Ingested
- **Status:** Accepted (owner decision, 2026-10-29); OpenSpec change `retrosheet-csv-bundles` archived unimplemented.
- **Context:** retrosheet.org also publishes its corpus as master and per-season CSV bundles (gameinfo, teamstats, batting, pitching, fielding, plays, allplayers). baseballpy already ingests the same games from the pinned `chadwickbureau/retrosheet` git tree (event and box files parsed with Chadwick, game logs, schedules, rosters, reference tables). The bundles come only from retrosheet.org, which times out from this PC and the homelab, and ingesting them means new schemas, a generator, adapter wiring and a licence note.
- **Decision:** do not ingest the bundles. The corpus they package is already in the lake through the git-tree sources, so no upstream data is left behind; only the alternative packaging is not stored. If the bundles ever appear in a GitHub repository the ingest already reads, this can be reopened.
- **Consequences:** `sources/retrosheet/` is unchanged and keeps pulling from the pinned tree; the "never leave data behind" rule is read at the level of data, not of every packaging of it. Backlog items B-20 to B-26 are removed.
- **Alternatives rejected:** implementing the bundles from the owner's local 2024 and 2025 zips (schemas from two seasons, unreproducible for other seasons); registering them as `unsupported` (they are reachable, just not wanted).

## ADR 42: dlt Is the Load and Normalize Layer, Introduced Behind IngestAdapter, MLB API First
- **Status:** SUPERSEDED by ADR 44 (2026-10-29); was UNDER REVIEW (2026-10-29): the owner rejected the adapter design that follows from this decision (B-43) and wants the existing tools used better, not replaced; see `docs/agents/HANDOFF_B43.md`. The spike evidence below stands; the Decision paragraph does not until the redesign.
- **Original status:** Accepted (owner direction 2026-10-29; scoped by the spike of `dlt-pipeline-core`); implements the intent of ADR 4.
- **Context:** ADR 4 made `dlt` the bridge to any destination, but only a sink was built; our own flatten, `_extras`, drift-regeneration and resume code does what `dlt` does natively. The spike (`scripts/dlt_spike.py`, evidence in the change's `design.md`) loaded three MLB endpoints through `dlt` from the same bytes: every column matched ours, nested lists became child tables, types agreed except `int32` widened to `BIGINT`; it lost the parent context our flattener carries, cannot `merge` on the Parquet destination, and does not keep raw bytes, quarantine or rate-limit.
- **Decision:** adopt `dlt` for the normalize and load stage, starting with the MLB API and behind `IngestAdapter` (no source changes the runner or CLI): resources are generated from the dataset registry; our `HttpClient` stays the only network path (passed to `dlt` as its session) so rate limits and the User-Agent stay in one place; generated schemas become `columns=` hints so types stay strict; a map step re-attaches the parent context; the raw store and quarantine stay ours; merge targets a SQL destination. Statcast and Retrosheet follow only if this holds.
- **Consequences:** `_extras`, `flatten.py` and the schema-drift regeneration can be retired for MLB once equivalence tests pass (task 3.2); `dlt` becomes a core dependency in practice, not an optional sink; adopting it is reversible per source because the adapter boundary is unchanged.
- **Alternatives rejected:** a full rewrite of every source now (no evidence for Statcast/Retrosheet); keeping our own normalizer and `dlt` only as a sink (what caused the friction); `dlt`'s `rest_api` source as the extractor (it would bypass our rate limiter and User-Agent).

## ADR 43: Upstream Change Detection Uses a Per-File Fingerprint and One Shared Check
- **Status:** Accepted (owner took the recommended default 2026-10-29; change `data-workflow-standard`).
- **Context:** the five sources share one storage flow (raw bytes with sha256, typed Parquet, DuckDB views) but decide "is my cached copy current?" differently: a pinned git commit for Chadwick, Lahman and Retrosheet, a time-to-live for Statcast and the MLB API. The stored sha256 is never checked (`RawStore.verify` has no callers), ETags are stored but only the live stream sends them back, and the git tree listing's per-file blob SHAs are discarded.
- **Decision:** every raw file records an upstream fingerprint in its manifest entry: the git blob SHA for GitHub sources, the ETag or Last-Modified for plain HTTP, the content sha256 for API payloads. One shared `is_current()` replaces the per-source checks, moved over one source at a time. API sources keep a time-to-live for how often they ask, and skip re-typing when the downloaded bytes hash the same. `baseballpy cache check` verifies local sha256 and lists files whose upstream fingerprint changed.
- **Consequences:** exact per-file updates for one API call on git sources; the hashes we already store become useful; new shared code in `core/`; sources migrate inside their own review tracks (tasks 2.1 to 2.3 of `data-workflow-standard`).
- **Alternatives rejected:** keeping pin plus time-to-live only (hashes stay unused, no per-file view); always re-downloading and comparing sha256 (wasteful, rate-limit heavy for Statcast and MLB).

## ADR 44: dlt Is the Send-It-Anywhere Layer Over the Cached Parquet; Extract and Typing Stay Ours
- **Status:** Accepted as direction (owner took the recommended default 2026-10-29); the exact design is settled in the B-43 brainstorm. Refines ADR 4 and supersedes the Decision of ADR 42.
- **Context:** the spike of `dlt-pipeline-core` showed `dlt` matches our columns but loses parent context and cannot merge on Parquet; the owner rejected `dlt` replacing the extractor, normalizer and flatten code.
- **Decision:** downloading (`HttpClient`), raw storage, strict Arrow typing and the Parquet lake stay as they are. `dlt` is used for delivery: a registry-driven export (`baseballpy export --format parquet|csv|duckdb|polars|postgres --out PATH`) reads the cached typed data and writes it to the chosen destination through `SinkProtocol` implementations (a CSV sink is added; PostgreSQL and warehouses go through `dlt`).
- **Consequences:** no per-endpoint code for export; every existing tool stays; PostgreSQL needs the optional extra.
- **Alternatives rejected:** `dlt` also doing extract and typing (ADR 42's original decision); leaving `dlt` as a Python-only optional sink (no uniform user-facing export).

## ADR 45: The Chadwick Lookup Is Lazy, Nicknames Come From the Data, Fuzzy Search Is a Shared DuckDB Helper
- **Status:** Accepted (owner chose data-driven nicknames with a fallback, 2026-10-29; change `chadwick-source-review`).
- **Context:** the register built a 526,894-row Python index on every load (12.4 s, also on every ingest job), kept a hand-typed 70-entry nickname table although the register shows which first names go with which given names, and ran fuzzy search with `difflib` over Python objects (11-13 s).
- **Decision:** (1) ingest (`sources/chadwick/ingest.py`) never builds a lookup; the register builds each id index lazily from the non-null values with Arrow and logs repeated ids (first row wins); (2) names are searched with vectorised Polars operations; (3) nickname pairs are learned from the register (`name_first` against the first word of `name_given`, at least 5 people and at least 10% of the top long form), with a 24-entry fallback list, and a person's own `name_nick` plus the `names.csv` spellings act as aliases; (4) fuzzy ranking is `core/similarity.py::top_matches`, DuckDB Jaro-Winkler over an Arrow column, so sources reach DuckDB only through `core`; the default `min_score` is 0.9, measured to behave like the old difflib 0.8.
- **Consequences:** construct 12.4 s to instant, fuzzy search 0.3 s, ingest job 15.3 s to 1.8 s (4.4 s on an empty home, 0.05 s cached) on the real register; identical top results on 24 fixed queries; the fuzzy score scale differs from before, so callers that pass an explicit `min_score` may need to retune it; learned nicknames depend on the register's data.
- **Alternatives rejected:** keeping the hand-typed table (stays hand-maintained, one entry was a no-op); importing DuckDB in the source (breaks the source/database boundary of `tests/test_architecture.py`); adding `rapidfuzz` (a new dependency for something DuckDB, already a core tool, does).

## ADR 46: Export Is Hybrid and Registry-Driven: pyarrow Files, dlt for Server Databases, Verified and Typed
- **Status:** Accepted (owner took all four recommendations 2026-10-29; change `export-workflow`). Implements ADR 44.
- **Context:** tests on real Chadwick data showed `dlt` keeps our types exactly in Parquet, DuckDB and PostgreSQL but adds bookkeeping folders to file output and makes untyped CSV; native pyarrow files are exact and clean.
- **Decision:** (A) hybrid: Parquet and CSV are written by pyarrow through our sinks (CSV with a `<dataset>.schema.json` sidecar holding each column's Arrow type and nullability; empty cell = NULL), server databases and warehouses (PostgreSQL first) go through `dlt` with the registry key as primary key, and DuckDB uses the native `DuckDBSink` (a local file engine; `dlt` would add `_dlt_*` tables to the file). (B) database tables use the registry `view` name (`chadwick_register`) in one schema named `baseballpy` (configurable). (C) exports go to `$BASEBALLPY_HOME/exports/<source>/<dataset>/` (override `BASEBALLPY_EXPORTS_ROOT_OVERRIDE` or `--out`; season-partitioned datasets use `season=YYYY/`). (D) PostgreSQL is tested against a disposable embedded server, `pgserver`, a dev-only dependency. Every export reads only the cached typed Parquet, supports `replace`, `append` and `merge` (files: replace only), is verified by reading it back (rows and types) and is written to the audit log; credentials come from `--url` or `BASEBALLPY_POSTGRES_URL`, never from files.
- **Consequences:** one registry-driven path for every source with no per-source code; exceptions (season-wise replace, streaming of very large datasets, datasets without a unique key) are listed in `export-workflow/design.md`.
- **Alternatives rejected:** `dlt` for every target (clutter, untyped CSV); schema per source; always requiring `--out`; testing only against a shared server.

## ADR 47: Lahman Is Checked at Both Cache Tiers by Git Fingerprint; Database Exports Keep Identifier Names
- **Status:** Accepted (owner took all six recommendations 2026-10-29; change `lahman-source-review`). Applies ADR 43 and ADR 46 to Lahman and fixes a gap in ADR 46.
- **Context:** Lahman served its processed Parquet without asking the extractor or upstream, stored only an ETag, kept two manifest entries per file with an off-by-one row count, dropped the mirror's README, licence and data dictionary, ran its orphan check only when `People` happened to be stored first, and exported to PostgreSQL through `dlt`, which rewrote `playerID` to `player_id` and `2B` to `_2_b` (26 of 27 read-back checks failed).
- **Decision:** (1) stay pinned: a raw file is current when its stored git blob SHA equals the one the pinned tree lists (the pinned commit decides when no tree is available), and the processed Parquet is current only when it was built from the raw file held; (2) one manifest entry per raw file with an exact data-row count; (3) the mirror's README, `LICENSE` and `data/readme*.txt` are kept in `raw/lahman/documents/` through the shared `core/documents.py` helper (Chadwick uses it too), and the licence (CC BY-SA 3.0, ShareAlike) is stated in `docs/DATA_LICENSES.md`; (4) supplied releases keep their documents, unknown CSVs stay raw only, a mixed release warns once; (5) one `lahman.table(name)` accessor, names ignore letter case, tables are remembered in process; (6) relationships between tables are one declarative table checked by one function and rechecked when a parent arrives later, findings printed by `catalog status`; (7) `DltSink` builds destinations with `naming_convention="direct"` so database identifiers equal the Arrow schema.
- **Consequences:** moving the pin refetches only changed files; a clean ingest reports exactly the one real finding (5 `AllstarFull` rows); all 27 tables verify on every export target; PostgreSQL SQL must quote mixed-case names; keys with empty values still cannot be merged (`AllstarFull`, `AwardsPlayers`, `CollegePlaying`); the import path was never run on a real SABR zip.
- **Addendum (Opus 5.5 review, 2026-10-29):** dlt refuses to change the naming of a pipeline that already loaded tables, so the PostgreSQL export pipeline is now named `baseballpy_export_direct` and a replace export drops a table whose columns differ from the data (a table left by the first version kept its `player_id` columns). Raw Lahman files stored without a fingerprint are identified by their stored sha256, so their Parquet is not rebuilt in every process.
- **Alternatives rejected:** floating with a time-to-live (results can change under the user); 27 named accessors; changing registry keys to avoid empty values (alters what unique means); dlt default snake_case names (breaks the read-back contract).

## ADR 48: Retrosheet Keeps Every Event Field, Is Checked by Git Fingerprint, Quarantines Broken Rows and Exports One Season at a Time
- **Status:** Accepted (owner took the reviewer's recommendations 2026-10-30; change `retrosheet-source-review`). Applies ADR 43, 46 and 47 to Retrosheet.
- **Context:** an independent Opus 5.5 review plus our own checks found that the event parser stores 98 of the 164 fields `chadwickpy` returns (the play id `EVENT_ID`, cwevent standard field 96, is dropped, so the events key `GAME_ID` collapses a game to one row on merge); processed Parquet is never rebuilt when the pin moves; only an ETag is stored; the README and notice of `chadwickbureau/retrosheet` (its root holds only `README.md` and `.gitattributes`; the README carries the Retrosheet notice) are ignored; `--datasets` rejects 14 of 25 registry names; short game-log rows and extra fields vanish silently; export loads every season into memory.
- **Decision:** (D1) store all event fields as typed columns and key events on `(GAME_ID, EVENT_ID)`, accepting a one-time re-parse; (D2) the raw tier compares the stored git blob SHA with the pinned tree, the processed tier records a combined fingerprint of the raw files it was built from, so a pin move rebuilds only what changed; (D3) a short or unreadable game-log or roster row goes to quarantine and is counted, extra fields go to `_extras`; (D4) export streams one season at a time, as a shared fix in this review.
- **Consequences:** merge exports become correct; existing event Parquet is re-parsed once (real check on the homelab 2015-2024 lake); the first run after upgrading downloads again because stored ETags do not match blob SHAs.
- **Alternatives rejected:** keeping 98 columns plus `_extras` (play id stays buried, key problem remains); rebuilding everything on every pin move; raising on a bad row (one line blocks a season).

## ADR 49: A Schema Change Invalidates Stored Chunks (schema digest in the manifest)
- **Status:** Accepted (task 3.4 of `retrosheet-source-review`, 2026-10-30; extends ADR 43).
- **Context:** after adding columns and changing keys on Retrosheet datasets the raw files were unchanged, so the stored Parquet still looked current and had to be deleted by hand; a user who upgrades would keep old-shaped files.
- **Decision:** `ProcessedStore.put` and `put_stream` record `schema_sha256` (digest of column names and types) in each chunk's manifest entry; `ProcessedStore.is_cached`, Lahman's `_processed_is_current` and the MLB API cache check use the shared `schema_matches(spec, entry)` and treat a different digest as stale. Chunks without a digest (written earlier) are trusted.
- **Consequences:** a release that changes a dataset schema rebuilds those chunks automatically; chunks written by older releases are rebuilt once only with `--refresh`. A parser change that keeps the schema (a bug fix in a value) is not detected: that case still needs `--refresh`, or a parser version later.
- **Alternatives rejected:** a global lake version bump (rebuilds everything for one dataset's change); comparing the Parquet footer schema at read time (costs a file open per chunk and misses key-only changes recorded in the registry).

## ADR 50: dlt Does Not Write the Processed Tier; It Stays the Delivery Layer
- **Status:** Accepted as the reviewer's recommendation (change `dlt-processed-tier-spike`, 2026-10-30); owner may overrule. Confirms ADR 44, keeps ADR 49.
- **Context:** the owner asked whether dlt should do more (schema versions, loads, evolution). A measured spike wrote the same 27 Lahman tables (706,466 rows) through `ProcessedStore` and through dlt's filesystem destination. With `SCHEMA__NAMING=direct` dlt matched our column names, types and rows exactly; its default naming rewrote every table and column name; writing took about 40% longer; a repeat run rewrote everything; a crash left the earlier file intact. A season-partitioned dataset cannot be rebuilt one season at a time: `replace` of one season removed the others, and `append` duplicated files.
- **Decision:** keep our `ProcessedStore` (atomic part files, manifests, fingerprints, schema digest) as the processed tier. dlt remains the way to deliver data to databases and warehouses (`baseballpy export`), where it creates and evolves tables. Evidence and numbers: `openspec/changes/archive/2026-10-30-dlt-processed-tier-spike/design.md`, script `scripts/dlt_processed_spike.py`.
- **Consequences:** no migration; task 3.4 and ADR 49 stay. Expanding dlt's role goes where it fits: incremental sync of a database from the lake (dlt state and schema contracts on the database side) is a candidate follow-up change if the owner wants it.
- **Alternatives rejected:** dlt as the lake writer for all sources (season rebuilds impossible without custom deletion); dlt for unpartitioned sources only (two writers, no gain: slower, bigger, no currency check); one dlt table per season (changes view names and the registry).

## ADR 51: Retrosheet Event Text Is NULL When Missing; a Dataset Revision Replaces Chunks an Older Parser Wrote
- **Status:** Accepted (change `retrosheet-source-review` task 5.19, 2026-10-30; extends ADR 49).
- **Context:** the export read-back check (task 3.2) failed for `events` and `events_postseason` to CSV in every season: 20 text columns held empty strings, which a CSV cannot tell from NULL; every other dataset stores NULL for a missing value. The fix keeps all column names and types, so the ADR 49 schema digest could not see that stored data was stale.
- **Decision:** the event parser stores NULL for an empty text field. `DatasetSpec.revision` (default 0) is part of the stored digest (`spec_fingerprint`); a revision above 0 also marks any chunk without a digest as stale. Retrosheet `events`, `events_postseason` and `events_deduced` are at revision 1.
- **Consequences:** the next ingest rebuilds those chunks without `--refresh`; a revision of 0 changes nothing for existing digests; a parser fix that changes values bumps the revision of the datasets it touches.
- **Alternatives rejected:** keeping empty strings and teaching CSV to quote them (every consumer would have to treat `''` and NULL alike for this one dataset); asking users to run `--refresh` (silent stale data).

## ADR 52: Statcast Applies the Source-Review Standard: Content Fingerprints, Kept Dictionary Page, Schema-Following Chunks, One Python Entry Point
- **Status:** Accepted (change `statcast-source-review`, 2026-10-30). Applies ADR 43, 46, 49 and 51 to Statcast.
- **Context:** Savant sends no version marker, so raw files carried no fingerprint; its data dictionary page was not kept; processed pitch and leaderboard chunks ignored the schema digest; only leaderboards had a by-name Python entry point; the game feed was not audit-logged; the Parquet and CSV export read-back failed for pitches because stored parts carry different dictionaries.
- **Decision:** each raw file records the ETag when sent, else its sha256 (`response_fingerprint`); the `csv-docs` page is kept in `raw/statcast/documents/` by a `documents` job; pitch and leaderboard chunks are reused only when `schema_matches`; `statcast.table(name, season)` and `datasets()` reach every registered dataset; the game feed is audit-logged; the export compares dictionary columns as values.
- **Consequences:** a schema change refetches stored windows without `--refresh`; chunks written before this change carry no digest and are trusted (no Statcast dataset has a parser revision yet); Savant leaderboard columns without a published definition stay undescribed.
- **Alternatives rejected:** treating Savant corrections by hashing every window on every run (about 150 requests per season for no known benefit; the trailing days are already refetched).

## ADR 53: League-Wide MLB Pools Fall Back to People Hydrate; A Probe Command Shows Provider Health
- **Status:** Accepted (owner asked for a permanent fix, 2026-10-30; change `mlb_api-source-review`). Extends ADR 40.
- **Context:** `GET /api/v1/stats` answers HTTP 406 for every query (all user agents, headers, parameters, seasons), while the other stats routes, the live feed and `v1/people?hydrate=stats(...)` answer 200. Our user agent is already the one pybaseball sends (ADR 40); no 403 was reproduced. Long ingests failed hours in because nothing checked the routes first.
- **Decision:** (1) when `/v1/stats` is refused with 406, a league-wide player pool is fetched by hydrating the sport's players (`/v1/sports/{id}/players`, then `/v1/people?personIds=...&hydrate=stats(...)` in batches of 150), keeping every response as raw bytes and normalising the identical split objects with the same schema; (2) `baseballpy probe` sends one small request per provider route in about three seconds and exits 1 when one fails, naming the fallback.
- **Consequences:** a provider fault on that route no longer blocks the pools that have a season; a season run keeps going after any refused request (task 5.7); the all-time pools stay on the direct route; two unknown hydrate fields landed in `_extras` until the schemas are regenerated through the fallback. **Amended 2026-10-31 (ADR 55):** the batch is a *ceiling* (halved on HTTP 414), every multi-value hydrate parameter is list-encoded because a comma list silently keeps its first value, a stat type with no person equivalent raises instead of storing an empty part, and the split pools carry parser revision 2 so parts written by the earlier fallback are refetched. One more unknown key family (`gameType`, `numTeams`, `sport.abbreviation`) appeared in the live split run and is preserved in `_extras` until a regeneration covers it.
- **Alternatives rejected:** changing the user agent or headers (shown irrelevant by the probes); waiting for the provider; scraping another site.

## ADR 54: The Live Feed's `fields=` Is a Snapshot Ability, Never a Streaming Mode; Field Sets Are Data
- **Status:** Accepted (owner chose the full plan on 2026-10-31; change `mlb-live-feed-projection`). Extends ADR 29.
- **Context:** the complete `feed/live` document is 663,043 bytes (0.33 s). The provider's `fields=` parameter selects key names: the shipped `score` set answers 368 bytes and `state` 141 bytes (game 745000, measured 2026-10-31). Three behaviours decide the design: a projection needs every parent key (a set without `gameData`/`liveData` answered 17 bytes), dotted paths are not a filter (`fields=gameData.status.detailedState` answered 2 bytes), and `diffPatch` ignores `fields` (the same patch answers 38,541 bytes with or without it and addresses paths such as `/liveData/plays/allPlays/62/about/endTime`). A projected baseline plus an unprojected patch therefore cannot work: `apply_patch` would fail on the first missing path and force a full feed on every poll.
- **Decision:** (1) add `GamedayLiveStreamer.snapshot(game_pk, fields=None, timecode=None)` and `snapshot_bytes()`: one request, no watermark read or write, the complete document when `fields` is absent; (2) keep named projections in the declarative `LIVE_FIELD_SETS` table of dotted paths and expand every path to its parent keys, because the wire format is a flat list of key names; (3) a bare string is a set name and an unknown one raises with the valid names listed, while a sequence or a comma/dotted string is a raw projection; (4) a decoded answer that lacks a document container the set names raises `SnapshotError` and is quarantined; (5) a projection is refused by `stream_live_events`/`stream_events` with an error that points at `snapshot()`.
- **Consequences:** a dashboard or a model feature build reads the state in 141–368 bytes instead of 663 KB, and a post-game review uses the same shapes through `timecode`; the streaming/patch algorithm is untouched, so nothing gets slower. Names match globally, so a common name (`description`, `name`) pulls a whole branch; every set is measured and a set that is not clearly smaller is not shipped (a `plays` set measured 144,027 bytes and was dropped in favour of the stored `game_play_by_play` dataset). The audit record has no byte field; the snapshot logs the projection name and seconds, and the byte counts live in the change's evidence.
- **Alternatives rejected:** adding `fields=` to the polling loop (unsound and slower, see context); per-consumer hand-written `fields` strings (code branches instead of data); caching a projected answer (serves stale scores); passing dotted paths on the wire (the provider ignores them).

## ADR 55: Multi-Value Hydrate Parameters Are List-Encoded; a Pool With No Person Equivalent Is Refused
- **Status:** Accepted (owner approved the fix on 2026-10-31; change `mlb-pool-fallback-completion`). Extends ADR 53.
- **Context:** ADR 53's fallback builds `hydrate=stats(...)` from the `/v1/stats` parameters. Inside that expression the provider silently keeps only the first value of a comma list: for Aaron Judge, 2025, `sitCodes=vr,vl` returned one split (`vr`) and `sitCodes=[vr,vl]` returned two (`vr`, `vl`); the person route accepts the comma list and returns two, so the defect is the expression builder. Two more gaps: `statsSingleSeason` and `statsSingleSeasonAdvanced` have no person form (`/v1/people/{id}/stats?stats=statsSingleSeason` answers 200 with `"stats":[]`, while `career` returns 2,747 games for the same player), so a 406 there would store zero rows silently; and a 1,200-id hydrate request is an 8,399-character URL the provider answers with 414, while 800 ids (5,599 characters) answered 200. The 602-code expression plus the current batch of 150 ids is about 5,520 characters and is accepted.
- **Decision:** (1) list-encode every multi-value hydrate parameter (`group`, `type`, `sitCodes`, `metrics`) in one function, splitting a comma-joined value first; the person route stays comma-based; (2) keep `POOL_BATCH = 150` and halve a batch on 414, down to one id, then raise; (3) list stat types with no person equivalent in `NO_PERSON_EQUIVALENT` with the measured evidence and raise `PoolFallbackUnavailableError` instead of calling the fallback or storing an empty part; (4) invalidate stored split parts with a per-stat-type parser revision (the ADR 51 mechanism), so the old single-code data is refetched without `--refresh`; (5) verify every `stats_stat_splits_*` pool live and compare a sampled subject's codes with the person route; (6) keep the single-season family on the direct route. Rebuilding it season by season (`/v1/sports/1/players?season=Y` plus `type=[season],season=Y`) is a separate change.
- **Consequences:** the split pools keep every code the provider serves (0–153 splits per player-season; about 1,097 bytes per split, 791,247 bytes for 10 players in 1.23 s); a 406 on a no-person-equivalent pool is a loud failure, not an empty success; the 414 path is a safety net for a longer expression, not the normal path; the split pools stay heavy (about 12 MB per 150-id request) and belong on the homelab with manifest resume; the single-season pools remain blocked by deep-offset 503s and are not marked `unsupported`, because the provider's data exists and the direct route is the block.
- **Alternatives rejected:** one situation code per request (multiplies the request count by the number of codes); a URL-length budget instead of the 414 guard (duplicates a rule the provider enforces and still needs the 414 path); the per-person `statsSingleSeason` route (returns no splits); marking the single-season pools `unsupported` (a wrong verdict that hides a real dataset); bumping the global `MLB_REVISION` (rebuilds every MLB dataset for a defect in one stat-type family).

## ADR 56: Statcast Starts in 2008 for Every Dataset; the Top End Follows the Clock
- **Status:** Accepted (owner decision 2026-11-03; change `statcast-season-bounds`).
- **Context:** only `all` respected the 2008 start; a named season (`-s 1850`) reached Savant. Test runs wrote 1890-1990 pitch folders (1990: 558,042 rows) and 1850 leaderboard folders into the real lake. Savant does return rows before 2008, so this is a deliberate exception to "never leave upstream data behind", not a provider limit.
- **Decision:** (1) the floor is 2008 for every Statcast dataset, 2021 for `pitches_minors`, and the probe's first season for a leaderboard that starts later (`lb_schema.min_year`); (2) the top is the lake clock's current year, with no constant, and a season whose MLB calendar start is after today is skipped; (3) the rule lives in `sources/statcast/seasons.py` and every entry point applies it before any request; (4) bulk ingests report a skip with its reason, single fetches raise; (5) the stray pre-2008 data was deleted.
- **Consequences:** a mixed selection (`ingest all -s 1990-2024`) runs the other sources and shows Statcast as `skipped`; lowering the floor later is one constant plus a live probe; pre-2008 Savant rows are not kept.
- **Alternatives rejected:** a hard-coded top year (goes stale every season); failing the whole command on an old season (breaks mixed selections); a floor per entry point (the rule drifts).

## ADR 57: In-Flight Limits Are Per Host; MLB Requests Run in Parallel; Jobs Can Name Prerequisites
- **Status:** Accepted (owner asked on 2026-11-03 that the code do what the specs intend; change `request-parallelism-and-host-limits`). Extends ADR 7 (host-specific rate limiting).
- **Context:** the audit log of the 2024 MLB season run showed 12,216 requests at 3.78 requests/s and 0.97 in flight against an allowed 8/s, because the requests of one endpoint ran one at a time. One global in-flight limit (4) was shared by every host, so a slow Savant download (9.9 s for one day) could hold the slots of fast hosts, and `ingest -c N` could not make the network faster. Running named endpoint jobs in parallel also exposed a race: `team_roster_active` ran at the same time as `teams_season`, found no teams and reported "completed, 0 rows".
- **Decision:** (1) the in-flight limit is per host (`max_concurrency` for each host, `host_concurrency` overrides); the token bucket stays per host; (2) the requests of one MLB endpoint run on a pool of at most `max_concurrency` workers behind the same host gates, fail-fast without `keep_going`, with the 404 count summed; (3) `Job.needs` names prerequisite jobs, the runner honours it in both paths, a failed prerequisite fails its dependents visibly, cycles are rejected; the MLB planner derives the needs from the endpoint registry (`prerequisites`); (4) an endpoint whose fan-out is empty logs a warning; (5) the CLI states workers and the network limit; (6) Savant's default in-flight limit is 8 (`savant_concurrency`), the other hosts keep 4, because a Savant pitch window takes seconds and four in flight cannot reach its 2.5 requests/second rate.
- **Consequences:** MLB fan-out can reach the host's 8 requests/s; a slow host no longer starves another; the number printed by the CLI is the one that limits the network; a mis-ordered `--datasets` list no longer silently stores nothing. Raising a host's in-flight limit never raises its rate. Threads inside one run can reach `workers x max_concurrency` but real requests stay bounded by the per-host gates.
- **Alternatives rejected:** a global limit raised to 32 (ignores the provider's rate and the AGENTS.md bound); making `-c` the network limit (job workers and in-flight requests are different things); sorting `--datasets` by hand in the planner (a hidden special case instead of declared prerequisites); failing an endpoint with no fan-out values (a season with no teams is legitimate for some sports).

## ADR 58: Adaptive Per-Host Concurrency Was Measured and Rejected; In-Flight Limits Stay Fixed
- **Status:** Accepted (change `adaptive-host-concurrency`, archived as rejected). Keeps ADR 57.
- **Context:** the 2024 MLB season ran at the host rate (8 requests/s) for 20 minutes but looked slow in two stretches with 17-19 s per request in the audit log. Little's law suggested more requests in flight for slow answers, so a gate that follows rate x latency (floor 4, ceiling 16, error back-off) was built and tested.
- **Decision:** do not ship it. Live measurements (design.md of the archived change): the heavy pools are rate-bound (7.2 of 8 calls/s, 0.03-0.14 s network time per call; the long per-request times in the log were waiting for the token bucket); the one slow endpoint (`stats_leaders`, 4-8 s per call) was not faster with adaptive (40.9 s against 31.9 s mean wall) and each call was slower, because the server slows under more concurrent requests and the slowest single request sets the wall time; Savant gave the same rows per second at 16 as at 8 (about 3,100 rows/s, set by its server). The fixed limits of ADR 57 stay (4 per host, 8 for Savant).
- **Consequences:** no extra moving part; audit-log durations must be read as "time in the client", not network time (they include waiting for the rate limiter); benchmarks must use fresh seasons or date ranges because both providers cache repeated requests. Speed on rate-bound work can now only come from a higher host rate (separate, measured decision) or from fewer requests.
- **Alternatives rejected:** keeping the gate behind a default-off switch (dead, untested-in-production code); a higher fixed ceiling for MLB (the slow endpoint got slower with more concurrency); lowering Savant to 4 (no measured benefit, and 8 was measured faster than 4 earlier).

## ADR 59: The MLB Stats API Host Rate Is 10 Requests per Second
- **Status:** Accepted (owner asked for maximum safe download speed on 2026-11-03; change `mlb-rate-10`). Extends ADR 57 and 58; stays inside `AGENTS.md` section 4 (8-10 requests/s).
- **Context:** after ADR 57 the 2024 season ran at exactly 8 requests/s for most of its 38 minutes, so the remaining time was bound by the token bucket (ADR 58 showed that more threads or in-flight requests do not help).
- **Decision:** the default `statsapi_rps` is 10.0 (still overridable with `BASEBALLPY_RATE_STATSAPI_RPS`). Evidence: four cold-season runs with 0 errors and unchanged network time per call, and a full 2024 season at 10 requests/s with 12,309 requests, 0 errors, no 429, in 1,749 s (2,264 s at 8, 3,234 s before ADR 57). Nothing above 10 without a new decision.
- **Consequences:** a season is about 23% faster than at 8; retries with `Retry-After` still back off if the provider ever answers 429; one dataset (`standings_by_organization`) came back as a valid partial answer in one run (106 of 201 records) and not in the others, which a re-fetch fixes; the client cannot detect that (B-235).
- **Alternatives rejected:** staying at 8 (measured slower, no measured benefit); above 10 (outside the contract); per-endpoint rates (a special case with no evidence of need).

## ADR 60: Small Low-Volume MLB Answers Are Fetched Twice and the Largest Is Kept
- **Status:** Accepted (owner chose "verify small answers" on 2026-11-03; change `verify-small-answers`, backlog B-235). Applies ADR 43's idea of per-answer checks to API answers cheaply; does not reverse its rejection of re-downloading everything.
- **Context:** in the second full 2024 run the single `/v1/standings?standingsTypes=byOrganization` request returned a valid but partial document (106 of 201 team records, 19 of 30 organizations, 308,486 of 573,230 bytes) and five later fetches were complete. The client stored it as complete. A web search found no documented case and no baseball library that checks for it.
- **Decision:** a single non-paginated MLB request in a call of at most `verify_max_requests` requests (5, 0 disables) whose first answer is a 200 of at most `verify_max_bytes` (1,000,000) is fetched again; identical bodies are stored; differing bodies get a third fetch, the largest is kept (ties: the latest) and `provider_inconsistent` is logged with the sizes. Nothing in it names an endpoint.
- **Consequences:** at most 86 extra requests in a 12,309-request season (0.7 percent); a partial answer on a low-volume request is caught on the first fetch of any lake; fan-outs (team, player, game, pools) are not covered; a legitimate update between two fetches can only make the kept body the newer, not the partial one.
- **Alternatives rejected:** record only (a partial answer would stay unnoticed); a declared expected record count per endpoint (no stable count: the same endpoint returned 200 and 201 rows on one day); a shrink guard on re-fetch only (does not protect a first fetch into a fresh lake); verifying every request (doubles the season).

## ADR 61: Retrosheet Parses in Parallel Through One Shared Process Pool, 32 Workers at Most
- **Status:** Accepted (owner asked for maximum speed per source on 2026-11-03; change `retrosheet-parallel-parse`).
- **Context:** one 2022 season took 236.5 s on a 56-core machine: 25 s of downloads and about 210 s of build steps that parse in one process (`parse_workers` defaulted to 0) and run one after another. A pool per build step at 16 workers gave 70.7 s and at 32 workers 87.1 s, because every step started and stopped its own processes.
- **Decision:** (1) `parse_workers` defaults to the CPU count capped at 32 (0 or 1 still parses in the calling process); (2) every parse stream of a run shares one persistent process pool (kept per worker count, discarded if a worker dies, shut down at exit); (3) a stream keeps at most twice the worker count of files in flight and yields tables in input order, so stored rows equal a single-process run; (4) the tests pin in-process parsing unless a test asks for a pool; (5) running the build steps of one season together is not built (see the change's design).
- **Consequences:** a season takes 35.6 s (6.6 times faster), five seasons 98 s; memory peaks about 6.5 GB higher for five seasons at 32 workers; on a machine with few cores the default is simply its core count; the first stream of a run pays the pool start (about 8 s of the 15 s events step).
- **Alternatives rejected:** a pool per step (measured slower at 32 workers); all cores without a cap (48 workers was no faster than 32); running the steps of a season on threads (little gain once seasons overlap, shared state in the source object); a default of 0 as before (uses one core of 56).

## ADR 62: The Default Data Folder Is `.baseballpy` in the Project Folder
- **Status:** Accepted (owner, 2026-11-04; change `project-local-data-folder`).
- **Context:** the default was `~/.baseballpy`, away from the code; the owner wants the data close, tidy and compact inside the project.
- **Decision:** with no `BASEBALLPY_HOME` or `BASEBALLPY_CACHE_DIR`, the data folder is `.baseballpy/` in the nearest folder above the working directory that holds `pyproject.toml` or `.git`; with no such folder it is `~/.baseballpy/`. The folder is git-ignored. Backfill ranges: Lahman, Chadwick and Retrosheet all history; Statcast and the MLB API 2008 to the current year, taken from the clock.
- **Consequences:** a fresh clone writes inside itself; two projects never share data unless `BASEBALLPY_HOME` says so; the data can be deleted with the folder.
- **Alternatives rejected:** fixed absolute path; install folder; keeping `~/.baseballpy` as the only default.

## ADR 63: Short Part Names and `_manifest.json`
- **Status:** Accepted (owner asked for readable, navigable names that every tool can read, 2026-11-04; change `readable-lake-names`).
- **Context:** parts were named after the full chunk id, repeating the dataset and the season already in the folders (683 files such as `part-award_recipients_2024_AAACMVP.parquet` in one season); `manifest.json` in each dataset folder made `pandas.read_parquet(folder)` and `pyarrow.dataset` fail.
- **Decision:** the part name is the chunk id minus the `<dataset>_` prefix and the season token (`part-data` when empty), decided in one function (`part_filename`); two chunks that would share a name are refused; the manifest is `_manifest.json` (pyarrow skips underscore files) and an old `manifest.json` is renamed on first use.
- **Consequences:** shorter, readable trees and working whole-folder reads; manifests keep the full chunk id as key; lakes written with the old names must be re-ingested.
- **Alternatives rejected:** renaming chunk ids in every source; leaving `manifest.json` and telling users to filter.

## ADR 64: Bad Cells in Box Accounts Become NULL and Quarantine, Not a Failed Season
- **Status:** Accepted (found by the first all-history Retrosheet run, 2026-11-05; change `tolerant-box-cells`).
- **Context:** 22 of 157 seasons failed because the strict box-account parser raised on stray cells (`2i`, `NA`, blanks, `FALSE`) in numeric or flag positions, losing every row of those seasons.
- **Decision:** cells that do not fit their type are stored as NULL and written to quarantine with their value; `true`/`false` match in any case; blank values are no value; a wrong field count or a record before any id still raises.
- **Consequences:** all seasons load; unreadable cells are visible in `quarantine/`; the raw bytes remain in `raw/`.
- **Alternatives rejected:** skipping lines; failing seasons; rewriting values by guessing (`2i` to `2`).

## ADR 65: One Underscore Name per Table: Folder, Registry Key and View
- **Status:** Accepted (owner chose underscores on 2026-11-05; change `underscore-table-names`). Follows ADR 63 (readable names).
- **Context:** Lahman had `lahman/AwardsShareManagers` (folder) and `lahman_awardssharemanagers` (view). SQL ignores letter case, so CamelCase did not survive in queries. The owner's PostgreSQL `raw` schema uses lower-case words with underscores and was named as the style model.
- **Decision:** every table is lower-case words joined by underscores; the view is `<source>_<folder>` (`mlb_` for the MLB API). Lahman's own spelling is kept only at the provider boundary (file name, URL, git tree). One test enforces the rule for every dataset. Singular and plural stay as each source has them.
- **Consequences:** `db sync` now drops views whose data folder is gone (found when the Lahman rename left 17 broken views); one rule with no special case; old CamelCase Lahman folders are not read (re-ingest, 13 s); a lake migrated from layout v1 needs the same re-ingest for Lahman. Column names keep the provider's spelling.
- **Alternatives rejected:** view-only rename; CamelCase everywhere; forcing singular names (style only, hundreds of renames).

## ADR 66: A Season Exists Once Its First Day Has Arrived (MLB Calendar, Not the Clock's Year)
- **Status:** Accepted (owner asked how the code knows which seasons are available, and what happens between New Year and spring training, 2026-11-05; change `season-calendar`). Extends ADR 56.
- **Context:** `all_seasons()` ended at the clock's year. The MLB calendar lists next year's season months ahead, so from 1 January the code planned a season with no games; only Statcast pitches skipped it, nothing else checked.
- **Decision:** `core/season_calendar.py` reads `/v1/seasons/all` once (cached twelve hours; only the current year needs it) and a season counts once its spring-training day (else opening day) has arrived. The Statcast and MLB adapters end `all_seasons()` there and skip any job of a not-started season with the reason. A calendar that cannot be read raises.
- **Consequences:** January and February plan the last season and skip the new one; from the first spring-training day the new season is planned; `is_finished` tells whether the postseason is over. Retrosheet keeps the provider's own listing.
- **Alternatives rejected:** a hard-coded month; trusting provider listings (they show next year early); falling back to the clock year when the calendar is unreachable (silent guess).

## ADR 67: Every Real Request Is Audited and `audit speed` Checks the Log Against the Caps
- **Status:** Accepted (owner asked whether the logs prove the speeds and whether tests and real runs agree, 2026-11-05; change `audit-speed-check`). Builds on ADR 57-59 and 61; extends the audit log, adds no new tool.
- **Context:** audit events wrap whole operations and their durations include waiting for the limiter (ADR 58), so the 2026-11-05 Retrosheet log could not show requests per second or requests in flight (60 events completed in one second against a 15/s cap).
- **Decision:** `HttpClient` writes one `http_request` event per real attempt with the true send time; `baseballpy audit speed` (new command in the existing `audit` group, analysis in `core/speed.py`) checks them against `RateLimitConfig`: starts in a window of W seconds must not exceed `rate*(W+1)+1` (the bucket's capacity plus its leak), in-flight must not exceed the host limit, failures are reported; rows per second per source come from the ingest jobs. It exits 1 on a broken cap.
- **Consequences:** tests, configuration and real logs answer to the same caps; the log grows by one line per request (about 500 bytes; the 19-season MLB backfill is about 230,000 requests); runs made before this change cannot be checked for rates.
- **Alternatives rejected:** inferring rates from operation events (they are not requests); a second log file (the audit log already has filters and readers); a plain mean-rate check (ignores the limiter's burst).
- **Amendment (2026-11-05, change `lahman-folder-case`):** CI on Linux found what Windows hides: any spelling of a Lahman table now resolves to the one underscore folder in the extractor, `migrate-layout` names Lahman folders from the registry, and tests compare real folder names. The suite can be run case-sensitively on Windows with `fsutil file setCaseSensitiveInfo <dir> enable` and `pytest --basetemp <dir>t`.
- **Amendment (2026-11-05, change `mlb-backfill-fixes`):** the first real MLB run found two faults, both fixed. Manifest saves used `json.dumps(indent=2)` (slow encoder), so a 3,200-entry manifest saved by many threads timed out on its lock and lost season 2011; saves now write one field per line without indent and wait up to 30 s. The request end was logged after the slot was released, so `audit speed` saw a fifth request in flight; the duration is now measured inside the slot (the re-run of 2011 peaked at 4 of 4). Not separately unit-tested: the timing fix, checked on the real re-run only.

## ADR 68: A Refused `/v1/stats` Is Remembered, Not Asked on Every Request
- **Status:** Accepted (owner: "deprecate the route that MLB refuses", 2026-11-05; change `mlb-stats-route-memory`). Builds on ADR 55 (people-route fallback).
- **Context:** the 2008-2012 MLB run sent 3,399 league-wide `/v1/stats` requests (5% of 62,033), every one answered HTTP 406, then fetched the same data through `/v1/people?hydrate`. The data was complete, the requests were wasted and every `audit speed` report counted them as failures.
- **Decision:** the extractor records when `/v1/stats` last answered 406 and, for one hour, sends league-wide pools straight to the people route; after an hour one request asks again, and a 200 clears the memory. The route is not marked `unsupported` (it has a working fallback and a 200 on other days).
- **Consequences:** about 3 refused requests per run instead of thousands; a recovered route is noticed within an hour of running; stat types with no person-level equivalent still fail with their evidence message.
- **Alternatives rejected:** marking the route `unsupported` (hides a recovery, the rule is a 200 control); a permanent file-based flag (stale after a fix); skipping silently without the hourly retest.

## ADR 69: Tightening Is Behaviour-Preserving, One Slice Per Commit, Proven by Comparison
- **Status:** Accepted (owner asked for a tightening pass while the MLB backfill ran, 2026-11-05; change `code-tightening`).
- **Context:** `ruff` with a complexity limit of 15 flagged 7 functions. Three of them decide what is downloaded (`requests_for`, the Statcast adapter's `run`, the season parser), so a slip would change data silently.
- **Decision:** each flagged function is split into small named helpers (a dispatch table where the function branches on a kind), one function or pair per commit, all gates after each. Where the function decides what is requested or stored, the old version (git HEAD) is run side by side with the new one and the outputs compared: `requests_for` on 364 endpoints x 6 contexts (2,184, 0 differences), `parse_box_text` on 428 real box files (identical tables), the Statcast `run` on 7,680 stubbed cases (0 differences). Comparison scripts must not write into the real lake (the box comparison left 50 duplicate quarantine files, removed).
- **Consequences:** the complexity check is clean at 15; no dataset, schema or request changed.
- **Alternatives rejected:** a rewrite into classes (more change than the finding asked for); relying on the test suite alone (it did not prove equality of requests).

## ADR 70: Kalshi Is a Standard Source: Typed Decimals, Threaded Catalog, Optional Signing
- **Status:** Accepted (owner: treat Kalshi and Polymarket like the other sources, strongly typed, as fast as safely possible, 2026-11-05; change `market-sources`).
- **Context:** the owner wants market prices to compare predictions against. The public Kalshi API needs no key. A first real run at 20 requests a second unsigned was throttled (HTTP 429 on 585 of 1,402 requests at about 10 a second); signed requests (account tier Basic, 200 tokens a second) ran 781 requests clean at 20 a second.
- **Decision:** `kalshi` is a source behind `IngestAdapter` with a declarative route table and scope rule, schemas generated from live probes (`scripts/gen_kalshi_schemas.py`), prices as `decimal(9,4)` and quantities as `decimal(18,2)` (the shared type vocabulary gained `decimal(P,S)`, stored as integers in Parquet), nested values as JSON text, unknown keys in `_extras`. The catalog is one job that fetches each series on a worker thread under the shared client's per-host caps. Signing is optional (`KalshiAuthConfig`, a per-host header hook in `HttpClient` that signs every attempt); default caps are 4 requests a second unsigned and 20 signed, 4 and 16 in flight. Credentials come only from the user's environment and are never logged, repr'd or stored; `.env` and key files are git-ignored.
- **Consequences:** 189 series, 55,197 events and 900,555 markets (all MLB; 9,394 game-winner markets, equal to the homelab count) in 41 MB of Parquet from 2.2 GB of raw JSON, with no `_extras` rows; the speed audit is clean. Candlesticks and trades follow in the next slices.
- **Alternatives rejected:** a plain float column (inexact prices); downloading with dlt (a second set of rate and audit rules); unsigned at 20 a second (throttled); reading the key from a dotenv file implicitly (breaks the rule that nothing is read implicitly from the working directory).

## ADR 71: Kalshi Trades and Candlesticks Are Opt-In, Per Open Date, From the Catalog
- **Status:** Accepted (owner asked for candles and trades, 2026-11-05; change `market-sources`). Extends ADR 70.
- **Context:** 706,068 of 900,555 catalog markets traded; trades exist only per market (1,000 a page), archived candles only per market, so the full job is about 1.7 million requests (about 22 hours at 20 a second). Grouping by close date put season-long markets in 2030 to 2032; the API refuses candle calls over 5,000 periods; a request log file per call would be about a million files.
- **Decision:** `trades` and `candlesticks` are opt-in datasets. The work list is read from the catalog in the lake (traded markets, grouped by open date, newest first), one resumable job and chunk per date; routes follow the archive cutoff; candles are hourly in windows of at most 4,500 periods; raw answers are one gzip of JSON lines per dataset and date, bodies verbatim; a final, unchanged date is skipped; chunk ids and file names must pass `portable_name_problem` (no Windows-illegal characters, no reserved names, no case-insensitive clashes), checked by tests and by a scan of the whole lake (413,148 names, none wrong).
- **Consequences:** a real run of three dates made 6,078 requests with no retry and no 429 at 20 a second signed; 346,259 trades (unique ids, prices inside 0.001 to 0.999, yes plus no equal to 1 on every trade) and 18,061 candles, none in `_extras`.
- **Alternatives rejected:** close-date chunks (future dates); one raw file per request; fetching markets without volume (about 194,000 requests for quotes only; kept as a possible opt-in); fetching global trades by time window (every sport, 26 times more rows than MLB).

## ADR 72: One baseballpy Process Per Remote Host
- **Status:** Accepted (found in a real run, 2026-11-06; change `market-sources`). Extends ADR 57 and 67.
- **Context:** the per-host rate and in-flight caps live inside one `HttpClient`, so two baseballpy programs on one host (the Kalshi catalog re-run beside the Kalshi trades backfill) sent 40 requests a second against a 20 a second budget; four day jobs failed with HTTP 429. Anyone running two ingests at once would hit the same thing, and a ban is possible on hosts that block abusers.
- **Decision:** the first request of a process to a host takes an operating-system file lock (`locks/<host>.lock` in the lake; `msvcrt` on Windows, `fcntl` elsewhere); a second process is refused with a message that says why; the lock ends with the process, even on a crash; `BASEBALLPY_RATE_ALLOW_PARALLEL_PROCESSES=1` opts out. Different hosts run side by side as before.
- **Consequences:** the 429 class of failure from two processes cannot happen by accident; a job that needs a busy host fails at once with an actionable message and can be rerun after the other finishes.
- **Alternatives rejected:** a shared token bucket across processes (a file or socket service for every request, far more complex); waiting silently for the other process (a second command would hang for hours without saying why); documentation only (it failed here).

## ADR 73: Two Doors From The Lake To A DataFrame
- **Status:** Accepted (owner asked for one simple query that loads all Statcast into a DataFrame fast, 2026-11-06; change `lake-access-and-compaction`).
- **Context:** measured on the real lake: Polars read all 14,971,703 Statcast pitches by 121 columns in 1.8 seconds, the same rows through the DuckDB view took 549 seconds; DuckDB is good for answers that are small (counts, sums, joins) and slow at handing back every row. A run of nine MLB seasons also took about six hours per season and ran out of memory because every chunk lookup parsed a 4.5 MB manifest again.
- **Decision:** `baseballpy.read` (Parquet to Polars, pandas or Arrow, by season and columns) and `baseballpy.sql` (DuckDB, read-only) are the two documented doors over the one Hive Parquet layout; registered views drop `union_by_name`; manifests are parsed only when their file changed. Compaction and compressed raw files follow in the same change.
- **Consequences:** the bulk path is Polars speed; analysis keeps SQL; both read the same files and cannot disagree (a test compares them); chunk lookups no longer scale with manifest size.
- **Alternatives rejected:** one big DuckDB database file (a second copy of the data, rebuilt after every download); making the view the only door (measured too slow for bulk rows); a custom reader (Polars already does it).

## ADR 74: Compaction In Place, With Chunk Positions In The File Footer
- **Status:** Accepted (owner approved compaction, 2026-11-06; change `lake-access-and-compaction`). Extends ADR 73.
- **Context:** 84,022 chunk files of 1 to 20 KB (and 115,017 zero-row files) made `db sync` take over 15 minutes and queries slow; ingests, the cache checks and per-chunk refreshes all work chunk by chunk, so the chunk files cannot simply be replaced.
- **Decision:** `baseballpy compact` writes `compact-NNNN.parquet` per dataset and season (chunks one after another, row groups of 122,880 rows, a JSON map `manifest key -> [first row, rows]` in the footer), verifies each file against its sources, then points the manifest entries at it (`compacted_into`) and deletes the small files. `ProcessedStore` reads, checks and rewrites compacted chunks (`has_part`, `read_part`, release on rewrite). Zero-row files of empty chunks are deleted. One shared manifest tracker per file replaces building a new one per lookup.
- **Consequences:** 400,000 files became about 4,300; `db sync` 15 minutes to 20 seconds; DuckDB one season 4.6 s to 0.84 s; an MLB season whose chunks are all downloaded finishes in 57 s with no request (it took about 6 hours). Kalshi trades grew 7 percent (random ids).
- **Alternatives rejected:** a second compacted copy beside the chunks (duplicate data and stale copies); sorting rows by key (loses the chunk positions); deleting chunk records (every ingest would download again).

## ADR 75: Gzipped Raw Text Files, Checksum Of The Original
- **Status:** Accepted (owner approved, 2026-11-06; change `lake-access-and-compaction`). Extends ADR 74.
- **Context:** `raw/` held 30.9 GB of json and csv in 242,809 files that are written once and almost never read again; the disk had 51 GB free.
- **Decision:** `RawStore.put` stores text raw files of the configured sources (`raw_compress_sources`, default `mlb_api` and `statcast`) as `<name>.gz` (gzip level 6, no timestamp) and records the sha256 and size of the original bytes with `stored: gzip`. `exists`, `get`, `verify`, `cache check` and the game feed read either form. `baseballpy compress-raw` converts existing files after a checksum match and a read-back check. Sources whose parsers open raw files by path (Retrosheet, Chadwick, Lahman) stay plain; files that arrive compressed are kept as they came.
- **Consequences:** 30.87 GB became 6.10 GB (24.8 GB freed); `cache check` verified all 252,542 raw files against their original checksums. Tests found two readers that looked for a fixed file name (the game feed) or decompressed any `.gz` (Kalshi); both fixed.
- **Alternatives rejected:** NTFS folder compression (Windows only, not portable); one archive per season (changes every reader); zstd (not in the Python standard library here).

## ADR 76: An Offline Layout Check Beside The Provider Audit
- **Status:** Accepted (owner asked for audit checks, 2026-11-06; change `lake-access-and-compaction`). Extends ADR 73 to 75.
- **Context:** the speed won by compaction and gzip is lost silently if a later ingest brings back thousands of small files, a part with other columns, or plain raw text. `catalog audit` compares providers with the registry over the network and is the wrong place for local file checks.
- **Decision:** `baseballpy catalog layout` (module `layout_audit.py`) reports six kinds offline; two (mixed schema, orphan compacted file) fail the exit code, four advise with the command that fixes them.
- **Consequences:** on the real lake it finds no failing kind and nine Retrosheet datasets with small row groups (advice only); a drift is visible in seconds (about 40 s for the whole lake) before it slows a query.
- **Alternatives rejected:** adding the checks to `catalog audit` (mixes a network audit with a local one and makes it fail without a network); automatic repair (a check should never change data).

## ADR 77: Polymarket As A Standard Source, GET Only, Hourly Prices
- **Status:** Accepted (owner asked for Polymarket built like Kalshi, 2026-11-06; change `market-sources`). Extends ADR 70 and 71.
- **Context:** probes showed that the offset events route stops at about 2,100 rows (a keyset route reaches all 11,653 MLB events), price history refuses windows over 15 days, the old trades route is retired (the v2 route returns trader wallet addresses and profile names), and the batch price route is a POST that the shared client does not send.
- **Decision:** a `polymarket` source with `events`, `markets` and `outcomes` (one catalog job, chunked by start month) and an opt-in hourly `prices` dataset (one job per market start date, one request per token and window of at most 14 days, only markets with volume). The sport tag id is read from `/sports`. Schemas come from `scripts/gen_polymarket_schemas.py` (shared `core/infer_types.py`, which now types a number that does not fit 64 bits as text); the raw gzip log is shared with Kalshi (`core/rawlog.py`). Rates are 80 percent of the documented limits: 24, 80 and 16 requests a second. Trades stay unwritten until the owner decides about personal data.
- **Consequences:** real run: 11,653 events, 233,923 markets, 467,846 outcomes (none in `_extras`, none quarantined; 75,657 markets traded), 280 price requests in 5 seconds with no error (p95 1.1 s), prices 0.0005 to 0.9995 with no duplicates.
- **Alternatives rejected:** the offset events route (cannot reach the history); the batch POST route now (20 times fewer requests but a new method in the shared client; a later speed-up); a Polymarket library with its own HTTP stack (bypasses the caps and the audit log).

## ADR 78: Baseball-Reference From Its Published Files Only; FanGraphs Not Downloaded
- **Status:** Accepted (owner asked for FanGraphs and Baseball-Reference without getting banned, 2026-11-06; change `fangraphs-and-bref`).
- **Context:** Sports Reference blocks a session for up to a day above 20 requests a minute, asks that its pages are not spidered and that no tool is built on scraped data; it publishes the WAR tables as two plain files. FanGraphs says it supports no scraping, API use or automatic import (only the one-click export for members), reports that most of its traffic is bots, and answers automated clients with a bot challenge. Getting around a bot challenge is not something this project does.
- **Decision:** a `bref` source (`war_batting`, `war_pitching`) that downloads only the two published files (2 requests, none while a file is under 12 hours old), at 6 requests a minute, one in flight, with no retry after a refusal (`host_max_attempts`) and a stop message after any refusal or web page. FanGraphs gets no downloader and no registered dataset; `docs/sources/fangraphs.md` records the evidence. The shared limiter now accepts rates below one request a second, and the CSV reader takes a source's own NULL word.
- **Consequences:** real run: 126,547 batting and 57,884 pitching rows, keys unique, nothing in `_extras`, nothing quarantined (Aaron Judge 10.90 WAR in 2024); the files are a snapshot of today's WAR, so past seasons change when Baseball-Reference revises them. The daily archive (WAR as of each day) and the FanGraphs data the owner already holds are open decisions.
- **Alternatives rejected:** scraping player pages (the stated rules forbid it and the rate is 20 a minute); a cookie or header trick for FanGraphs (evading bot protection); pybaseball (it scrapes the same pages).

## ADR 79: FanGraphs Files Are Typed From An Inbox, For Private Use, With No Request To FanGraphs
- **Status:** Accepted (owner approved importing the FanGraphs tables already held in the homelab database, 2026-11-06; change `fangraphs-and-bref`). Extends ADR 78.
- **Context:** FanGraphs supports no scraping, API or automatic import and protects the site with a bot challenge; the homelab project collected its tables through the unofficial mobile-app API with the app's user agent and marks them "owner-risk research only". The models want FanGraphs projections, park factors, fielding and splits.
- **Decision:** a `fangraphs` source with ten `on_demand` datasets that reads CSV files from `inbox/fangraphs/` (`LakeConfig.inbox_dir`), keeps the raw bytes, types them with schemas generated from the whole files, and makes no network request (a test enforces it). `scripts/export_homelab_fangraphs.py` copies the homelab tables read only over ssh. The data is private research data: marked so in every dataset description, never shared, never published. The shared CSV loader now reads a whole number written as `157.0` as the integer 157, and the schema generator takes numbers with more than 8 decimals as `float64`.
- **Consequences:** real import: 1,219,323 rows equal to the homelab tables row for row, column totals compared with the homelab, nothing in `_extras`, nothing quarantined after the loader fix (the first run quarantined 1.7 GB of whole numbers written as `157.0`; the files were removed and the loader fixed). The copy is a snapshot until the export is run again.
- **Alternatives rejected:** a FanGraphs downloader of any kind (no supported route); copying the homelab's app-user-agent client into baseballpy (evades bot protection in code others run); leaving the data out (the models lose projections and park factors).

## ADR 80: A Slow, Honest FanGraphs Downloader; Stop At The First Refusal
- **Status:** Accepted (owner asked for code others can use to download FanGraphs data, 2026-11-06; change `fangraphs-and-bref`). Extends ADR 78 and 79 (ADR 78's "no downloader" is replaced for the leaderboards and projections).
- **Context:** FanGraphs supports no scraping or API use, but its own website serves leaderboards, projections and the prospect board as JSON to an ordinary client. One honest request with the project's default client answered HTTP 200, so no disguise is needed. The homelab project reaches the same data by sending the Android app's user agent; baseballpy does not.
- **Decision:** `ingest fangraphs -o download=yes` downloads leaderboard seasons (`/api/leaders/major-league/data`, one request per season) and projection snapshots (`/api/projections`, 16 systems by 2 groups, only changed rows) through the shared client at one request every two seconds, one in flight, with an honest user agent for this host, no retry after a refusal, and a hard stop at HTTP 403, 429 or 503 or at a web page where data should be. Columns are named by the rule the existing files use, and the importer and the downloader write the same chunks (one per season, or per capture date), so a season that arrives both ways is stored once. A generic `--option KEY=VALUE` switch carries the mode. Guts, park factors (web pages), splits (POST) and the prospect board are still typed from files.
- **Consequences:** real run: 3 leaderboard seasons and 32 projection runs, 35 requests, all HTTP 200, 0 new projection rows (the hashes equal the homelab's, so unchanged rows are recognised); the 2024 batting download matched the homelab copy in all 478 columns and 1,454 players, with 17 columns recalculated upstream. FanGraphs can block this at any time; the user carries that risk and the data stays private.
- **Alternatives rejected:** the app user agent or browser headers (evading bot protection); a retry loop or proxy rotation after a block; leaving other users without a downloader (the owner's goal is that others can fetch their own copy).

## ADR 81: Agent Coordination CLI, Automated 100 MB Audit Rotation, and Synergized Multi-Agent Workflow
- **Status:** Accepted (owner requested agent coordination bulletin board, audit log rotation, and OpenCode Chief of Staff delegation, 2026-11-06; change `agent-coordination-and-audit-rotation`).
- **Context:** Parallel AI sessions (Claude Code, Gemini/Antigravity, Cursor, and OpenCode) risk clobbering files and duplicating work without a unified coordination lock. Additionally, continuous large-scale historical extractions (such as Kalshi 447 days) cause the telemetry log `.baseballpy/logs/audit.jsonl` to balloon (reached 1.25 GB), degrading I/O and audit command latency.
- **Decision:**
  1. Add `baseballpy agent` CLI commands (`claim`, `release`, `board`) maintaining both human-readable `docs/agents/AGENT_BOARD.md` and machine-readable `docs/agents/agent_log.jsonl` with 4-hour stale lock detection.
  2. Add `baseballpy audit rotate` command and automatic rotation when `audit.jsonl` reaches 100 MB, compressing older logs into `audit-YYYY-MM-DD.jsonl.gz` using standard `gzip`.
  3. Default `scripts/opencode_delegate.py` to `opencode/deepseek-v4.1-flash-free` for cheap/free task execution under strict Chief of Staff sandboxing (`--allow`).
  4. Formally synergize OpenSpec `tasks.md`, `docs/agents/BACKLOG.md` (`B-xxx`), and `docs/agents/AGENT_BOARD.md` across operating contracts.
- **Consequences:** Zero file collisions across parallel agent sessions; audit log size stays bounded under 100 MB while preserving complete audit history; fast and free task delegation via OpenCode.
- **Alternatives rejected:** External Redis/Postgres locking service (heavy, non-portable for local open-source users); deleting old audit records (violates ADR 6 auditability mandate); allowing unrestricted file edits across parallel sessions.

## ADR 82: One Overview, One Update Command, Manifest-Based Status, Blank And NaN Are Values
- **Status:** Accepted (owner asked for workflows and a CLI that just work, 2026-11-07; change `lake-workflows-and-cli`).
- **Context:** `catalog status` opened every Parquet footer (more than 110 s), no shipped plan existed, season ranges went stale, 26 quarantine files held blank cells and `NaN` text, and a legacy command wrote into the working folder.
- **Decision:** `status` and `update` commands; status reads manifests (`--verify` for the slow check); built-in `daily` and `full` plans with a `current` season keyword; blank cells are NULL and `NaN` text is a float; the `statcast` command writes under `exports/`.
- **Consequences:** a lake overview takes seconds; a rerun of `update` fetches only what is new; quarantine only holds real errors (older quarantine files stay as history); the manifest is trusted for counts, and `--verify` or `catalog layout` is the check.
- **Alternatives rejected:** caching row counts in a second file (the manifest already has them); a `--season-from` flag instead of `current` (stale again each January).

## ADR 83: Verify The Library The Way A New User Meets It; Rebuild A Catalog From A Newer DuckDB
- **Status:** Accepted (owner asked whether a new user would hit problems, 2026-11-07; change `fresh-install-verification`).
- **Context:** the wheel was installed in an empty environment with an empty lake. Downloads, names, views, reads, exports and checks worked, but the developer machine's DuckDB 2.0 catalog could not be opened by the DuckDB 1.5.6 that a plain install resolves.
- **Decision:** the catalog database (views only) is moved aside and rebuilt when it comes from a newer DuckDB; read-only use gets a clear error; small friendliness fixes (`arrow`, pandas message, group hint).
- **Consequences:** one lake works with DuckDB 1.5 and 2.0 alike; the clean-room run is the check to repeat before a release (steps in the change design).
- **Alternatives rejected:** pinning DuckDB below 2 (blocks users who have 2.0 and gives the developer machine a different version from the lock); storing the catalog per DuckDB version (more files, same result).

## ADR 84: Write Down And Test The Naming Rules; Unknown Processed Folders Fail The Layout Check
- **Status:** Accepted (owner asked for a folder and name audit, 2026-11-07; change `folder-and-name-audit`).
- **Context:** the audit found every name consistent, with one deliberate exception (`mlb_` views for the `mlb_api` source), but no test and no documentation of the rules.
- **Decision:** a test enforces snake_case, unique views of the form `<source>_<dataset>` (one declared exception), and a doc file per source; the README states the rules and draws the complete lake; `catalog layout` fails on a `processed/` folder no dataset owns.
- **Consequences:** a misnamed dataset or an orphan folder is caught before it reaches users; nothing was renamed, so no user query breaks.
- **Alternatives rejected:** renaming `mlb_*` views to `mlb_api_*` (breaks queries); checking raw folders the same way (raw-only names are legitimate).

## ADR 85: The Per-Game MLB Download Defaults To The Major Leagues
- **Status:** Accepted (owner chose "major leagues first", 2026-11-07; change `mlb-game-levels`).
- **Context:** the per-game phase took every level of the schedule (about 16,000 games per season, 5 to 6 days for all seasons); the 2026 run died of a `MemoryError` after 7.9 hours. Major leagues are about 2,960 games per season.
- **Decision:** `--option sports=` selects the levels (default `1`; `all` or a list of ids), read from `schedule_hydrated.sport_id`.
- **Consequences:** the first full per-game backfill is about five times smaller. Minor-league games are one option away and nothing is removed from the catalog.
- **Alternatives rejected:** a separate command (the options mechanism already exists); keeping all levels as the default (days of download for data the models do not need first).

## ADR 86: Compacted Files Are Written By Column Name, Not By Position
- **Status:** Accepted (found when every major-league game run failed on 2026-11-07; follows the schema regeneration B-303).
- **Context:** B-303 added typed columns (for example `person_name_slug`) to 142 datasets. Compacted files written earlier lack them, and rewriting such a file (when one of its chunks is downloaded again) failed with a column-name mismatch, so all 19 seasons of the per-game download stopped within 30 seconds.
- **Decision:** `core/compacted.py::align_to_schema` lines a table up with the registered schema by name, with empty cells for new columns; an unknown column is an error.
- **Consequences:** a schema can gain columns while old compacted files exist. Old files keep their old columns until their chunks are rewritten (`catalog layout` still reports them as MIXED_SCHEMA; ADR 87 migrates them).
- **Alternatives rejected:** casting by position (the failure); dropping unknown columns (loses data); deleting compacted files on a schema change (loses the resume points).

## ADR 87: Files Written Under An Older Schema Are Read As-Is And Migrated By `compact`
- **Status:** Accepted (owner asked for the full fix, 2026-11-07; change `lake-schema-evolution`). Extends ADR 73 and 86.
- **Context:** B-303 moved fields from `_extras` to typed columns in 142 datasets. `read` failed on mixed old and new files, strict DuckDB views silently lost the new columns, and the old values stayed in `_extras`.
- **Decision:** `read` scans under the registered schema (missing columns empty, unknown columns refused). `compact` first rewrites each file that differs from the registered schema (`core/evolve.py`): values in `_extras` move to their typed columns with the ingest's own cast and quarantine, moved keys leave `_extras`, compacted chunk maps are kept, and a chunk is re-fingerprinted only when its old fingerprint proves the schema was the only difference. `db sync` and `catalog layout` point to `compact`.
- **Consequences:** a regenerated schema no longer needs a re-download of old data and no longer breaks reads. Views stay strict and fast. A file that cannot be migrated is reported and left alone.
- **Alternatives rejected:** `union_by_name` on all views (slow, hides the mix); tolerating old files forever (old values stay hidden in `_extras`); re-downloading everything (days of requests for data we hold).

## ADR 88: Manifests Are Read And Written As Bytes
- **Status:** Accepted (owner asked for the memory fix before the next long download, 2026-11-07; change `mlb-game-memory`).
- **Context:** a 16,000-game MLB season run ended in `MemoryError` after 7.9 hours, inside the manifest save. Every chunk write rewrote a manifest of tens of thousands of entries with `json.dumps` (a multi-MB string built each time) from 12 threads.
- **Decision:** `ManifestTracker` decodes with `msgspec.json.decode` from bytes and writes `msgspec.json.encode` bytes straight to the atomic part file (`msgspec` is the designated tool for large JSON, `docs/agents/TOOLING.md`). No broad `except` and no fallback to `json`: a manifest that is not valid JSON or UTF-8 is preserved as `*.corrupt-<timestamp>` as before.
- **Consequences:** measured on 50,000 entries (10.5 MB): 0.08 s and about 15 MB extra memory per save. The file is one line instead of one field per line. Per-season manifests (design item 2) were not built; they stay an option if a run grows far beyond 50,000 chunks per dataset.
- **Amended (2026-11-08):** the first unattended runs ended with a Windows access violation (exit 0xC0000005, and exit 139 earlier) whose traceback ends in `msgspec.json.encode` inside `ManifestTracker.save`. The manifest is now written with the standard library (`json.dumps` with compact separators) and read with `json.loads`; the memory bound is unchanged. `msgspec` stays in use elsewhere. The cost per save grows with the manifest (0.13 s at 29,000 entries), so bulk runs defer the saves (ADR 93). The queue also retried only exit code 1: any crash code is now retried.
- **Alternatives rejected:** per-season manifests now (every reader of the dataset manifest would change); keeping `json` with a smaller write buffer (the string is the problem); a silent fallback to `json` on any error (hides failures and brings the spike back).

## ADR 89: One Behavior On Linux, macOS And Windows
- **Status:** Accepted (owner asked for full cross-platform compatibility, 2026-11-08; change `cross-platform-support`).
- **Context:** the code was written and run on Windows. An audit found differences that only show on one OS: `write_text` turned LF into CRLF on Windows, the repository had no `.gitattributes`, the Retrosheet process pool used the platform default start method (`fork` on Linux before Python 3.14, unsafe with HTTP and DuckDB threads), and a Windows console printed table borders as `?`. The lake layout was already portable (ADR 63) and CI already ran the suite on Ubuntu and Windows.
- **Decision:** UTF-8 and LF everywhere (`newline="\n"` on every writer, `* text=auto eol=lf`), `spawn` for every process pool, UTF-8 console streams, and `tests/test_portability.py` reads the source to enforce all of it. No OS-specific scheduler or tool in the project: always-on work is a Python process (B-313).
- **Consequences:** a file written on one OS is byte-identical on another; a new `write_text` without `newline`, an `open` without `encoding` or a pool without `mp_context` fails the gates. `fcntl.flock` may not lock on NFS; documented. macOS is not in the CI matrix yet.
- **Alternatives rejected:** leaving the platform defaults (different bytes by OS); testing only by running on each OS (a difference is easy to miss; the source scan fails on every OS); a Windows-only or Linux-only scheduler (breaks the other OS).

## ADR 90: A Python Supervisor Keeps Downloads Running (`baseballpy run`)
- **Status:** Accepted (owner asked for always-on, automatic, queued downloading in Python only, no OS scheduler, 2026-11-08; change `download-queue`). Builds on ADR 82 (plans) and ADR 89 (no OS tools).
- **Context:** a long download was a hand-written shell loop. Three season runs died with exit 139 and one with a `MemoryError`; nothing restarted them, recorded what failed, or started the next round. Plans, resume, disk checks and the host lock already existed.
- **Decision:** `baseballpy run PLAN [--every 6h]` runs each stage of a plan in its own child process (`sys.executable`), retries a failed stage with exponential backoff and jitter (`tenacity`), goes on to the next stage when one is out of retries, and repeats the plan after `--every`. Exit codes of `backfill` decide: 0 done, 1 retry, 2 (size or disk limit) stop, 130 stop. Progress lives in `<home>/state/queue.json` (`msgspec`, atomic write); a restart resumes the unfinished round. One supervisor per home, using the same OS file lock as the host lock. `baseballpy backfill --stage` runs chosen stages.
- **Consequences:** a crash costs one attempt, not the run. Memory goes back to the OS between stages. `status` shows the queue. Speed is unchanged: the per-host rate limit, the in-flight limit and the one-downloader-per-host lock still apply, so the queue adds reliability, not requests per second.
- **Alternatives rejected:** Task Scheduler, cron or systemd (different on every OS, outside Python); APScheduler, Prefect or Airflow (a heavy dependency or a server for "retry, then repeat in six hours"); running stages in the supervisor's own process (a crash or memory spike would end the supervisor).

## ADR 91: A Games Run Fetches Only The Games, And The Queue Compacts Between Stages
- **Status:** Accepted (owner asked for all per-game history downloaded unattended, 2026-11-08; change `finish-mlb-history`). Extends ADR 85, 87 and 90.
- **Context:** the `games` job also re-ran every season dataset: it repeated hundreds of requests for each season and ended failed (exit 1) on the datasets the provider refuses (HTTP 406, B-30), so a complete season looked failed and the queue would have retried it. The disk (16 GB free) cannot hold the history as small files (about 3 GB per season in tens of thousands of files).
- **Decision:** the `games` job carries `games_only` and the source skips the reference tables and season endpoints except the schedule. `baseballpy run` runs `compact` for the stage's sources after each finished stage. The history is a plan file with one stage per season.
- **Consequences:** a season of games no longer spends its first minutes on season datasets and exits 0 when its games are complete. Disk use is bounded by one season of small files. Speed per game is unchanged.
- **Also (found by the first unattended run, 2026-11-08):** the win probability route answers 404 for games that never had plays (19 cancelled games in 2024, 13 in 2022); `schedule_hydrated` still lists them as final. They failed every games job (exit 1) and would have been retried forever. `game_win_probability` now opts in to `tolerate_missing` (recorded as empty and counted, AGENTS.md section 11.4); the other per-game routes still fail loudly.
- **Alternatives rejected:** compacting only at the end (the disk fills first); excusing exit 1 in the queue (hides real failures); moving the lake to the homelab tonight (no unattended path to it).

## ADR 92: The Download Speed Is Measured, And The Limit Is In Our Own Work
- **Status:** Accepted (owner asked that downloads always run at the best speed and be checked at intervals, 2026-11-08; change `download-throughput`). Confirms ADR 59.
- **Context:** the per-game MLB download ran at about 3 requests per second against a cap of 10. We tested the obvious causes. The host answered 11.3 requests per second to a probe made while the download ran. Raising the in-flight limit from 4 to 12 left the rate at 2.9 and made answers three times slower. One 611-column game chunk took 96 ms to store (55 ms in the Parquet writer) and there are 13 per game; 50 games in one write cost 133 ms.
- **Decision:** `baseballpy speed` and the queue's speed watch measure the rate, the answer time and the in-flight use from the audit log and name the limit. They advise and change nothing: the only knob (in-flight) does not help, and the request rate above the cap is a policy matter. The cure is less local work per game: batched chunk writes, cheaper normalization, and (an owner decision) worker processes sharing the host's rate limit.
- **Consequences:** the default in-flight limit of 4 stays. Speed is checked every 10 minutes in the queue log. Raising the per-game speed needs the tasks of the change, not a setting.
- **Alternatives rejected:** an automatic concurrency tuner (the measurement shows it would raise the limit and slow every answer); raising the rate cap (not the limit today); more threads (the work is serialized by the interpreter lock and by file writes).

## ADR 93: A Bulk Download Must Not Pay For The Size Of The Lake At Every Chunk
- **Status:** Accepted (owner asked that downloads always run at the best speed, 2026-11-08; change `download-throughput`). Follows ADR 92.
- **Context:** measured with real payloads and no network, a game cost 526 ms in an empty lake and 1,114 ms when each processed manifest held 25,000 entries, which is what the real download does by the last seasons. Two costs grew with the lake: the name-clash check at every put copied every manifest entry and tested each one, and every put rewrote the whole manifest (0.13 s at 29,000 entries) 13 times a game; the shared tracker cache (24) was smaller than the manifests in use.
- **Decision:** the clash check uses an index of lower-case file names per season folder, extended with the keys that are new since the last call. `ManifestTracker.deferred()` holds saves back during a bulk run and writes them every 500 entries and at the end (an error included); the MLB extractor uses it for the processed manifest of a dataset and the raw manifest of its season. The tracker cache holds 48 manifests.
- **Consequences:** about twice as fast at lake size (520 to 630 ms per game) and flat as the lake grows. A crash loses at most 500 manifest entries per dataset, whose chunks are fetched again. Other processes see new chunks after each flush. Worker processes for normalization were tried and not kept (630 to 530 ms for about 2.4 GB more committed memory).
- **Alternatives rejected:** per-season manifests (every reader of the dataset manifest changes); normalizing in worker processes (small gain, more memory, and the machine's commit limit is the scarce resource today); batching Parquet writes first (about 110 ms of 520).

## ADR 94: Compaction Runs Beside The Next Download
- **Status:** Accepted (owner asked that data always be downloading, 2026-11-08; change `finish-mlb-history`). Amends ADR 91.
- **Context:** ADR 91 compacted between stages. With the speed-up of ADR 93 a season downloads in about 35 minutes (at the rate limit) but compacting its 38,000 small files took more than 45 minutes, so the download sat idle for longer than it ran. The cost was reading every small part with `pq.read_table`, which takes 50 ms for a 611-column file (24 ms with `ParquetFile.read`).
- **Decision:** the queue starts a finished stage's compaction in a background thread (a child process) and goes on with the next stage; one compaction runs at a time, the next waits for the previous, the queue waits for the last. Compaction reads parts with `ParquetFile.read` and compacts up to `--jobs` datasets at once. The default is 2: four at once, beside a download, ran out of committed memory (a pyarrow `ArrowMemoryError`).
- **Consequences:** the download is idle only while the first stage runs. Compaction and download touch different seasons, and both merge their manifest changes through the file lock, so they do not interfere. Disk is returned a little later than before; the queue still stops at the free-space floor.
- **Alternatives rejected:** compacting only at the end (the disk fills first); more than two compactions at once (memory: each holds a season of one dataset); skipping verification (the read-back is what makes compaction safe).

## ADR 95: Each Download Is Stored Once, In Parquet Segments Shared By Every Dataset Made From It
- **Status:** Accepted (owner decided after an Opus design review, 2026-11-08; change `response-log-segments`). Supersedes the drafts `shared-raw-bytes` and `batched-chunk-writes`; replaces ADR 75 for sources that write segments; reduces ADR 74, 91 and 94 to the sources that still write part files.
- **Context:** raw bytes are kept per dataset, not per download. One MLB game is 5 URLs feeding up to 13 datasets; the live feed is saved 4 times and the boxscore 6 times (about 20 GB of copies). Each game also writes one small Parquet file per dataset, and compacting a season takes longer than downloading it (ADR 94). Measured on 2024 samples: a live feed is 828 KB raw, 128 KB gzip, 90 KB zstd 19; 30 feeds compressed together are 2.29 MB against 4.05 MB as gzip files.
- **Decision:** a source fetches each URL once, parses it once and feeds every dataset the registry maps to it. Responses go to a crash journal (`_open/journal.zst`, one zstd record each, flushed per game), and every 250 games or 10 minutes (to be measured) close as a segment: one raw `seg-NNNN.parquet` per source and season (url, time, status, etag, sha256, zstd body) and one `seg-NNNN.parquet` per dataset, written in row groups of about 50 games. Processed rows carry `_raw_sha256`. One format, Parquet with zstd; no new dependency. A schema change is applied by rebuilding segments from raw. One generic mechanism behind `SinkProtocol`; MLB first, then the other sources.
- **Consequences:** raw for 2008-2026 is guessed at 12-15 GB instead of about 47 GB (to be measured by the converter). A season ends as a few big files per dataset, so the queue's heavy compaction goes for those sources. A crash costs no finished game. Every processed row can be traced to its response. Old files need a one-time converter and rebuild; until task group 7 both layouts are read.
- **Alternatives:** content-addressed blob files per response (the `shared-raw-bytes` draft): not chosen now, because it keeps one file per response and compresses each alone (no cross-game gain); revisit if Parquet bodies prove slow to read one at a time. Batched part files only (the `batched-chunk-writes` draft): not chosen now, because it leaves the raw copies; revisit if the raw side is ever dropped. A new archive format (WARC, tar plus zstd): not chosen now, because DuckDB and pyarrow already read Parquet and nothing new is needed; revisit if raw must be exchanged with web-archive tools.

## ADR 96: A Segment Counts Only When One Line In `segments.json` Says So; Readers Never See Rows Twice
- **Status:** Accepted (owner decision, 2026-11-08; change `response-log-segments`). Follows ADR 95.
- **Context:** a segment is many files (one raw, one per dataset). They cannot be renamed in one step, Windows locks files that readers hold, and views must show new data at once without double counting while a segment is refreshed or a season migrated.
- **Decision:** all files are written in `_open/` with `.part` names, renamed into place with the existing retry, and the last step appends one line to the season's `segments.json` (segment, games, file sha256s, row counts, schema fingerprints). A game is stored only when its line exists; on start, files no line names are deleted and the journal is replayed. Views and `read` list only files directly inside `season=YYYY/` (never `_open/` or `_legacy/`). A refresh renames the new file over the old one of the same name; a migration hides old files in `_legacy/` before the segments appear (a short gap, never a double). One writer per source and season through the existing host lock, for downloads, converter, rebuild and round-trip check alike.
- **Consequences:** a crash at any point leaves either a committed segment or files that are cleaned on start. New data is queryable the moment its line is written. A reader can, for a moment during a migration, see a season with no rows.
- **Alternatives:** a catalog database (DuckLake, SQLite) as the commit record: not chosen now, because one appended line per segment is enough for one writer; revisit before the live feed (ADR 97). New file names for a refresh plus a reader-side filter on `segments.json`: not chosen now, because plain globs in DuckDB views could not apply the filter; revisit if refreshes become frequent.

## ADR 97: Keep All Raw On The Laptop For Now; Own Segment Files, Not A Table Format
- **Status:** Accepted (owner decision, 2026-11-08; change `response-log-segments`).
- **Context:** with ADR 95 the whole lake with all raw is guessed at 40-50 GB, which fits. Raw is our only way to rebuild data after a schema or parser change. Table formats (DuckLake, Iceberg, Delta) offer commits and small-file handling.
- **Decision:** all raw stays on the laptop. Raw may later move off the laptop only per segment, only after a round-trip check (rebuild each response from the processed rows and compare it with the raw response) passes; it is moved, never deleted, and `segments.json` records where it lives. We keep our own segment files and `segments.json`. The `.duckdb` file holds views only (single writer, rebuilt at any time).
- **Consequences:** no new dependency and no catalog to back up; any Parquet reader can read the lake. The round-trip check also shows what the processed rows do not yet type.
- **Alternatives:** DuckLake: not chosen now, because one writer per season does not need a catalog and the live pipeline does not exist yet; revisit before building the live feed (many small in-play updates). Iceberg or Delta: not chosen now, because they need a heavier stack for a single-user lake; revisit if the lake moves to a server shared by several writers. Data inside DuckDB files: not chosen now, because a DuckDB file has one writer and ties data to one DuckDB version (ADR 83); revisit if DuckDB storage becomes stable across versions and writers. Deleting raw after the check: not chosen now, because the owner keeps all raw; revisit if disk runs short and the check passes for every segment.

## ADR 98: `v_season_catalog` Is The Lake Inventory
- **Status:** Accepted (owner asked for a way to see what the lake holds, 2026-11-10; change `lake-inventory-columns`).
- **Context:** every download is already recorded (per-dataset manifests, raw checksums, the audit log) and `v_season_catalog` listed seasons with rows and files, but a person could not tell which view to query, how big a dataset was or when it last changed.
- **Decision:** `v_season_catalog` gains `view_name`, `bytes` and `last_written_at` (newest file time, UTC). No new tracking file and no change to manifests. What should be held stays with `catalog status` and `catalog coverage`.
- **Consequences:** one SQL query answers "what do I have"; older queries on the first five columns keep working. `last_written_at` is the file time, not the provider download time, because compaction rewrites files.
- **Alternatives rejected:** a second inventory view or file (duplicate records to keep in step); download times from every manifest (several MB each, MLB has hundreds, `db sync` would slow down); rows for datasets not yet downloaded (that is `catalog status`).

## ADR 99: One Compaction Per Dataset At A Time
- **Status:** Accepted (owner asked to prevent clobbering, 2026-11-11; change `compact-one-writer`).
- **Context:** two compactions of `mlb_api.game_boxscore_players` season 2019 ran together on 2026-11-08. `compact_dataset` takes the next `compact-NNNN` number from the folder, so both chose the same numbers and the later write replaced the earlier file; the records then pointed at files holding other games (about 46,000 rows missing, 43,000 stored twice) while the queue said "done". `_cleanup` also deletes compact files no record points at yet, which is what a live run's new file looks like.
- **Decision:** `compact_dataset` claims the operating-system lock `compact-<source>-<dataset>` of `core/hostlock.py` (the lock the hosts, the queue and the segment writers already use) before it changes a file and releases it when it ends. A second compaction of the same dataset gets `HostBusyError` and changes nothing; `baseballpy compact` skips it ("busy") and exits non-zero. A dry run takes no lock.
- **Consequences:** no new dependency; a crash frees the lock; other datasets run side by side as before. The lock is per process, so two threads of one process could still compact one dataset (the command never does). Ingest versus compact in one dataset stays "run it when no ingest is running".
- **Alternatives rejected:** exclusive-create file names (does not stop `_cleanup` deleting a live run's file, the record save stays last-writer-wins); a per-season lock (the records are per dataset); a new lock library (`fasteners` and `filelock` are only indirect dependencies); documentation only (the queue starts compactions by itself).

## ADR 100: The Product Is The Workflow Code; Outputs Must Be Reproducible For Every User
- **Status:** Accepted (owner directive, 2026-11-11; change `product-mandate-reproducible-outputs`).
- **Context:** the contract never stated that `baseballpy` is a library for other people, published on PyPI, whose download and ingest workflows must give the same results for every user. In practice a session spent most of its effort repairing data files by hand (MLB 2019 boxscores) while the defect lived in code (two compactions at once, ADR 99) and the queue still marked failed stages done.
- **Decision:** `AGENTS.md` gets section 0 (product mission) and section 15 (reproducible outputs); `CLAUDE.md`, `openspec/project.md` and `README.md` carry the mission. The owner's lake is a test oracle, not the deliverable. A data defect is fixed in the code path that produced it, with a test, and the data is rebuilt by the workflow; hand edits are a last resort, written down and followed by a rebuild. "Same" means same rows, schema, names, counts and compacted-file bytes for pinned inputs. A test keeps the sections in the contract.
- **Consequences:** follow-up tasks are mapped (rebuild check, ingest re-fetch of a chunk its compacted file lacks, the queue never marks a failed stage done, deterministic compaction, a determinism audit per source). Work that only repairs files is no longer an acceptable end state.
- **Alternatives rejected:** a note in `CLAUDE.md` only (agents read `AGENTS.md` and tests enforce it); waiting for the first release (the rule shapes every change now).

## ADR 101: A Stage Whose After-Step Failed Is Not Done
- **Status:** Accepted (follows AGENTS.md section 15 rule 6 and the owner's reproducibility directive, 2026-11-11; change `queue-after-step-failure`).
- **Context:** `baseballpy run` marked a stage done when its download child exited 0. A failed after-step (compaction) was only written into `last_error`: the stage stayed done, the compaction never ran again, the round's failed list stayed empty and the exit code was 0. The real queue showed MLB 2018 to 2021 as done with `after-stage step exited with 1`, and the 2019 tables were damaged without anyone noticing.
- **Decision:** a failed after-step sets the stage to `failed`; the round settles the last after-step before it is judged; the failed stage runs again (download check and after-step) through the existing failed-round continuation. A stage is done only when download and after-step both worked.
- **Consequences:** `status`, the report and the exit code show compaction failures; they are retried. A compaction that always fails keeps the stage retrying every `failed_wait`, the same as a download that always fails. No new state fields.
- **Alternatives rejected:** a separate after-step status and retry counter (a second path for one outcome); only warning (the defect).
