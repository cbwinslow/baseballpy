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
