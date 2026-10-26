# baseballpy — Agent Contract & Engineering Mandates

Read `openspec/project.md` and `docs/DECISIONS.md` before making architectural or implementation changes.

---

## 1. OpenSpec Change Protocol & Documentation Mandate

1. **Spec-Driven Development:**
   - Every architectural change, new data source, schema revision, or significant feature MUST begin with an OpenSpec change proposal in `openspec/changes/<change-name>/` containing `proposal.md`, `design.md`, and `tasks.md`.
   - Update or author system specifications in `openspec/specs/<component>/spec.md` as the living source of truth.
2. **Immutable ADR Logging:**
   - Record all architectural tradeoffs, dependency introductions, format choices, and domain-specific workarounds in `docs/DECISIONS.md` as Architecture Decision Records (ADRs).
3. **Documentation Sync:**
   - Keep `README.md`, `CLAUDE.md`, and API docstrings in lockstep with code implementations. Never leave undocumented public interfaces.
4. **Exhaustive Endpoint & Schema Documentation Mandate:**
   - Every integrated data source MUST have a dedicated, detailed specification document in `docs/sources/<source>.md`.
   - The documentation MUST exhaustively record:
     - All remote URLs, endpoints, query parameters, headers, and HTTP methods.
     - Upstream rate limits, timeout behavior, and server-side row caps.
     - An exhaustive column dictionary cataloging **every single table attribute**, its upstream raw string format, its coerced PyArrow physical storage type, nullability, and domain definition.
     - Known upstream anomalies, sentinel values, and era-specific quirks.

---

## 2. Decoupled Architecture & Minimal Splash Damage Mandate

Components in `baseballpy` MUST be strictly modular, decoupled, and isolated to ensure that updating or refactoring any one section of the codebase creates **zero splash damage** to unrelated modules:

```text
┌────────────────────────────────┐
│   baseballpy.sources (Extract) │  <-- Async HTTP, caching, rate limits, pagination
└───────────────┬────────────────┘
                │ Raw bytes / dict / JSON stream
                ▼
┌────────────────────────────────┐
│   baseballpy.schemas (Parse)   │  <-- Pure transforms, PyArrow schemas, type coercion
└───────────────┬────────────────┘
                │ pyarrow.Table / RecordBatchReader (zero-copy)
                ▼
┌────────────────────────────────┐
│   baseballpy.sinks (Storage)   │  <-- DuckDB, Parquet, Polars, dlt (Postgres/Cloud)
└────────────────────────────────┘
```

1. **Protocol Boundaries:**
   - Extractor, Normalizer, and Sink interact exclusively via strict `typing.Protocol` interfaces (`ExtractorProtocol`, `NormalizerProtocol`, `SinkProtocol`, `StreamExtractorProtocol`, `LiveEventConsumerProtocol`).
   - Sinks MUST NOT import or depend on network libraries (`httpx`, `urllib`).
   - Extractors MUST NOT import or depend on database drivers (`duckdb`, `psycopg2`).
   - Normalizers are pure mathematical/coercion functions taking raw payloads and emitting Arrow/Narwhals structures.
2. **No Monolithic Classes:**
   - Avoid monolithic manager classes that bundle fetching, parsing, and saving into single mega-methods.
   - Compose workflows through functional pipelines: `Pipeline.run(extractor, normalizer, sink)`.

---

## 3. Full Data Preservation & Cross-Endpoint Completeness Mandate

1. **No Arbitrary Field Truncation:**
   - Every extractor and normalizer MUST capture, parse, and ingest **ALL** data attributes, columns, and metadata made available by an upstream endpoint.
   - Never omit, drop, or cherry-pick fields under the assumption that "the user won't need this" or "this field is redundant."
2. **Endpoint Completeness Regardless of Duplication:**
   - If an endpoint provides data that is also available from another source (for example, exit velocity available from both Statcast search and MLB Gameday live feeds, or player names available in both Chadwick and Statcast), the pipeline MUST still capture and preserve that data within each respective source's schema.
   - Downstream models, analysts, and auditing workflows rely on raw source fidelity. Do not drop fields to deduplicate across sources.

---

## 3. Domain Mastery & Baseball Invariants

1. **Unique Identifiers & Keys:**
   - **`game_pk` (MLBAM Game ID):** Primary numeric key across MLB Stats API and Statcast. Uniquely identifies a single game contest, including games of a doubleheader. Never assume `(date, home_team, away_team)` is unique without `game_type` and game number.
   - **Player ID Systems:** A single human player has different IDs across systems (MLBAM ID, Retrosheet ID, Baseball-Reference slug, FanGraphs ID, Lahman ID). All player resolution MUST route through the Chadwick Register crosswalk (`baseballpy.sources.chadwick`).
   - **Pitch & Play IDs:** In Statcast, a pitch is uniquely identified by `(game_pk, at_bat_number, pitch_number)` or Statcast UUID. In MLB Gameday, plays are identified by `atBatIndex` and `playEvents` array indices.
2. **Game State & Rule Evolution:**
   - Extra inning rules, 7-inning doubleheader games (2020–2021), pitch clocks (2023+), and shift restrictions change over time. Schemas must never hardcode assumptions that break across eras.
3. **Official Scoring Revisions & Retroactive Corrections:**
   - Real-time ingestion pipelines MUST support **idempotent upserts** keyed by `(game_pk, at_bat_number, pitch_number)` rather than naive append-only operations.
4. **Game Status Lifecycle:**
   - Streaming extractors must handle mid-game rain delays, suspended games resumed months later, and scheduled doubleheaders gracefully.

---

## 4. Concurrency, Async & Rate-Limiting Contracts

1. **Host-Specific Rate Limiting (Token Bucket):**
   - Every network extractor MUST route outbound requests through an instance of `AsyncRateLimiter` (`aiolimiter`) tied to the target host.
   - **Baseball Savant (`baseballsavant.mlb.com`):** Max 2–3 requests/sec; single queries must not span more than 5–7 days to prevent server-side query timeouts (504 Gateway Timeout) and silent truncation (25,000 row cap).
   - **MLB Stats API (`statsapi.mlb.com`):** Max 8–10 requests/sec; HTTP/2 connection pooling with persistent keep-alive (`httpx.AsyncClient(http2=True)`); use conditional headers (`If-None-Match` / `ETag`) when polling live games.
   - **Retrosheet Mirror (`chadwickbureau/retrosheet` via GitHub CDN):** Static content; max 15 requests/sec. Never hit `retrosheet.org` for bulk historical extraction.
2. **Structured Concurrency (No Unbounded Fan-Out):**
   - NEVER spawn unbounded `asyncio.gather()` or thread pools over full seasons.
   - All concurrent downloads MUST be bounded by an explicit semaphore (`asyncio.Semaphore(max_concurrency)` defaulting to 4 workers).
3. **Jittered Exponential Backoff:**
   - Wrap transient failures (HTTP 429, 500, 502, 503, 504, `httpx.ConnectTimeout`) in retry policies with exponential backoff and randomized jitter (via `tenacity`).

---

## 5. Real-Time Streaming & Model Ingestion Mandates

1. **Low-Latency Event Streaming:**
   - The streaming engine (`baseballpy.sources.mlb_api.stream`) polls or subscribes to active games and emits discrete, immutable event objects (pitches, pickoffs, stolen bases, substitutions, end of half-innings).
2. **State Diffing & Monotonic Sequence Tracking:**
   - Do NOT emit redundant play events. Maintain an in-memory watermark of `(atBatIndex, eventIndex)`.
   - Track `metaData.timeStamp` to verify whether the upstream API payload has changed before triggering JSON parsing and deserialization.
3. **Downstream Model Interoperability:**
   - Real-time streams must yield events in lightweight zero-copy structures: Arrow `RecordBatch`, Polars row tuples, or Python dataclasses/dicts with microsecond UTC timestamps, ready for immediate inference by live run expectancy, win probability, or pitch-classification models.

---

## 6. Audit Logging, Telemetry & Benchmarking Mandates

1. **Structured Telemetry (JSONL):**
   - Every public command and pipeline execution MUST emit an audit event to `~/.baseballpy/logs/audit.jsonl`.
   - Recorded fields: `timestamp_utc`, `operation`, `source`, `status`, `records_count`, `duration_seconds`, `throughput_rps`, `cache_hit`, `endpoint`, `destination`, and `error`.
2. **CLI Reviewer:**
   - Provide user-facing audit inspection tools (`baseballpy audit summary`, `baseballpy audit tail`, `baseballpy audit stats`) formatted cleanly with `rich` tables.

---

## 7. Error Handling, Data Quality & Dead-Letter Quarantine

1. **No Silent Failures:**
   - Never use bare `except:` or `except Exception: pass`.
   - If a row fails schema coercion, log a structured warning and route the unparseable payload to a dead-letter quarantine (`~/.baseballpy/quarantine/`).
2. **Schema Drift Resilience:**
   - Schema normalizers must handle evolutionary schema drift: accept optional new fields gracefully without crashing historical pipelines, and log unknown column discoveries.

---

## 8. Atomic Download Gate, Manifest Checkpointing & Pause/Resume Mandate

1. **Two-Phase Atomic Commit:**
   - Network downloads MUST NEVER write directly to their final cache filenames.
   - All network streams must write to a temporary file (e.g. `{filename}.part`).
   - Only after checksum, footer validation (for Parquet), or record boundary validation passes may the file be atomically renamed (`os.replace()`) to its final destination.
   - Interrupted downloads leave only `.part` artifacts, which must be safely discarded on retry, preventing corrupted partial files.
2. **Pause / Resume via Manifest Checkpointing:**
   - Partitioned datasets (Statcast date chunks, Retrosheet seasons) must maintain a `manifest.json` checkpoint recording chunk completion status, record counts, and ETags.
   - Re-running an interrupted extraction MUST inspect the manifest and resume from the first uncompleted chunk without re-downloading completed partitions.
3. **Two-Tier Raw/Processed Partitioning:**
   - Sources with raw archive files (e.g. Retrosheet `.EVA`/`.EVN` event files and Lahman zip archives) must enforce clean two-tier folder separation:
     - `raw/`: Unmodified upstream text/archive files.
     - `processed/`: Clean, strongly-typed PyArrow Parquet files.
   - Parsing engines (such as `chadwickpy`) must operate purely as in-memory transformations from `raw/` to `processed/` with zero unintended file collisions across seasons.

---

## 9. Testing, Verification & Tooling Mandates

1. **Package Manager:** Use `uv` exclusively for dependency resolution, virtual environments, and command execution.
2. **Code Quality Policy:** Zero warnings policy on `uvx ruff check .` and `uvx ruff format --check .`.
3. **Type Safety:** 100% strict type checking with `uvx mypy --strict src`.
4. **Mocked Network Tests:** Unit tests MUST never make real external HTTP requests. Use `respx` to mock `httpx` responses or load recorded fixture payloads from `tests/fixtures/`.
5. **Property-Based Testing:** Use `hypothesis` to test schema normalization against arbitrary string permutations, NaN/null representations, and out-of-bounds timestamps.


---

## 10. Dynamic Configuration & Production Smoke Testing Mandates

1. **Pydantic V2 BaseSettings Configuration:**
   - All runtime configuration (`CacheConfig`, `AuditConfig`, `RateLimitConfig`, `StreamingConfig`, `QuarantineConfig`, `PipelineConfig`) MUST inherit from `pydantic_settings.BaseSettings`.
   - All paths, timeouts, and rate limits MUST be overridable via environment variables prefixed with `BASEBALLPY_` (e.g. `BASEBALLPY_HOME`, `BASEBALLPY_CACHE_DIR`, `BASEBALLPY_RATE_MAX_CONCURRENCY`).
2. **Production Smoke Testing:**
   - Maintain end-to-end multi-season smoke tests (`tests/test_smoke.py`) verifying chunking, manifest checkpointing, zero-loss idempotency, atomic rollbacks on network interruptions, and cross-source sink pipelines.
