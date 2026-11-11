# baseballpy — Agent Contract & Engineering Mandates

Read sections 0 and 15 (what the product is and the reproducible-outputs rules), `openspec/project.md` and `docs/DECISIONS.md` before making architectural or implementation changes.

---

## 0. Product Mission (read this before anything else)

`baseballpy` is a **reusable Python library and command-line tool, distributed on PyPI**, that downloads, ingests and maintains MLB baseball data for other people: **historical** data in bulk (resumable, polite to the providers) and **real-time** data during the seasons. Its users model and analyse the data with **DuckDB, PyArrow, Polars, pandas, Parquet files, CSV and PostgreSQL** (and other warehouses through `dlt`), so the on-disk layout, the table names and the column types are a public contract.

1. **The product is the code and its workflows, not the data on one machine.** The lake on the owner's computer is a *test oracle*: it shows what the workflows produced and lets us check that a fresh run gives the same output. It is never the deliverable. Data can be downloaded again; the workflows are what every user depends on.
2. **Every user who runs the same workflow gets the same results** (section 15). A feature that works only on the owner's lake, or only after hand-edited files, is not done.
3. **Effort goes to the download, ingest, compaction and read workflows first.** Use the existing data to confirm that the workflows would produce it again; do not spend a session massaging files.
4. Every change is judged by one question: *if a stranger installs this from PyPI and runs the workflow, do they get what the documentation promises, every time?*

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

1. **Protocol Boundaries (ADR 39):**
   - The enforced contracts are those other code consumes: `SinkProtocol`, `StreamExtractorProtocol`, `LiveEventConsumerProtocol` and `baseballpy.ingest.IngestAdapter` (every registered source has an adapter; the runner and CLI never import a concrete source; `tests/test_ingest_contract.py`).
   - `ExtractorProtocol` / `NormalizerProtocol` are optional shape guides for single-dataset sources; multi-dataset sources (Lahman, MLB endpoints, Statcast leaderboards) need not implement them.
   - Sinks MUST NOT import or depend on network libraries (`httpx`, `urllib`).
   - Extractors MUST NOT import or depend on database drivers (`duckdb`, `psycopg2`).
   - Normalizers are pure mathematical/coercion functions taking raw payloads and emitting Arrow/Narwhals structures.
2. **No Monolithic Classes:**
   - Avoid monolithic manager classes that bundle fetching, parsing, and saving into single mega-methods.
   - Compose workflows through the ingest layer: adapters plan jobs, `run_jobs` executes them (`baseballpy.ingest`).

---

## 3. Full Data Preservation & Cross-Endpoint Completeness Mandate

1. **No Arbitrary Field Truncation:**
   - Every extractor and normalizer MUST capture, parse, and ingest **ALL** data attributes, columns, and metadata made available by an upstream endpoint.
   - Never omit, drop, or cherry-pick fields under the assumption that "the user won't need this" or "this field is redundant."
2. **Endpoint Completeness Regardless of Duplication:**
   - If an endpoint provides data that is also available from another source (for example, exit velocity available from both Statcast search and MLB Gameday live feeds, or player names available in both Chadwick and Statcast), the pipeline MUST still capture and preserve that data within each respective source's schema.
   - Downstream models, analysts, and auditing workflows rely on raw source fidelity. Do not drop fields to deduplicate across sources.

---

## 3A. Domain Mastery & Baseball Invariants

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
   - All concurrent downloads MUST be bounded by an explicit in-flight limit **per host** (`asyncio.Semaphore(max_concurrency)` for each host, default 4; `host_concurrency` overrides single hosts) on top of the host's token bucket, so a slow host never holds another host's slots (ADR 57). Fan-out inside a source (the requests of one endpoint, the windows of a season) uses a pool of at most `max_concurrency` workers behind those same gates.
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
   - Every public command and pipeline execution MUST emit an audit event to `$BASEBALLPY_HOME/logs/audit.jsonl` (default `~/.baseballpy`).
   - Recorded fields: `timestamp_utc`, `operation`, `source`, `status`, `records_count`, `duration_seconds`, `throughput_rps`, `cache_hit`, `endpoint`, `destination`, and `error`.
2. **CLI Reviewer:**
   - Provide user-facing audit inspection tools (`baseballpy audit summary`, `baseballpy audit tail`, `baseballpy audit stats`) formatted cleanly with `rich` tables.

---

## 7. Error Handling, Data Quality & Dead-Letter Quarantine

1. **No Silent Failures:**
   - Never use bare `except:` or `except Exception: pass`.
   - If a row fails schema coercion, log a structured warning and route the unparseable payload to a dead-letter quarantine (`$BASEBALLPY_HOME/quarantine/`).
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
   - Partitioned datasets (Statcast date chunks, Retrosheet seasons) must maintain a `_manifest.json` checkpoint recording chunk completion status, record counts, and ETags.
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

---

## 11. Coverage Sweep, Generated Schemas & Bounded Downloads

1. **Enumerate, never hand-pick:** when a provider lists its own options (stat types and groups, sports/levels, standings and roster types, files in a git tree), ingest every one. Anything that cannot be ingested stays registered `unsupported` with probe evidence (`docs/*_probe.json`), or its raw bytes are kept; it is never silently skipped. Hand-written datasets that select fields get a complete-field twin.
2. **Generated schema modules are never edited by hand** (`tables.py`, `lb_tables.py`, `mlb_tables.py`, `stat_combos.py`): change the generator in `scripts/` or the catalog and regenerate; commit the fixtures and probe JSON it writes. Types come from data, never from column names.
3. **`unsupported` needs real evidence:** before declaring an endpoint or dataset unreachable, try the provider's own UI requests, documented parameters and well-known open-source clients (and web search); record what was tried. A wrong `unsupported` is data left behind (minor-league Statcast was declared unreachable until `minors=true` was found).
4. **Bounded downloads:** requests that announce huge results (all-time pools, > 20,000 rows) are refused unless explicitly allowed; a per-request 404 is tolerated only for endpoints that opt in and is recorded and counted.

## 12. OpenSpec Hygiene

1. Tick `tasks.md` as work lands; when a change is finished merge its spec deltas into `openspec/specs/*` and move it to `openspec/changes/archive/<date>-<name>/`.
2. Every deviation from a change's design is written into that change's `proposal.md`/`design.md` ("As built") and, if it is a decision, an ADR in `docs/DECISIONS.md`.
3. Hand-typed counts and numbers do not belong in docs: use generated dictionaries and the probe JSON.
4. Autonomous runs follow `docs/agents/GOAL_SEEK_PROMPT.md`; keep it aligned with this file.

## 13. Design Philosophy, Research and Delegation

1. Stay decoupled, reusable and dynamic: registry- and generator-driven behavior, `Protocol` boundaries, no scattered per-source special cases; prefer a declarative table plus one generic function.
2. Search the web for existing solutions (other libraries, the provider's repositories, issues) before writing any workaround, and record the findings in the change's design.
3. Bulk code that Claude has already designed may be delegated to `agy` or `opencode` (DeepSeek models via `scripts/opencode_delegate.py`); every delegated diff is reviewed in full and gated (`docs/agents/AGY_DELEGATION.md`). Claude `Agent`/workflow subagents remain off unless the owner asks.


## 14. AI Agent Operating Rules (binding for every agent and every task)

These rules apply to Claude, `agy`, `opencode` and any other agent. They are short on purpose; the reasons are in
sections 1-13 and `docs/DECISIONS.md`. `tests/test_agent_rails.py` enforces what a machine can check.

### 14.1 Preflight (before the first edit of a task)

0. **Check the coordination board:** read `docs/agents/AGENT_BOARD.md` for active checkouts before
   editing. If a task or files are locked by another agent, do not touch them; pick an unassigned
   backlog row instead. If there is no task in `docs/agents/BACKLOG.md` or on the board to check out,
   you MUST create the task/OpenSpec change first, add its row to `BACKLOG.md`, and claim it.
   Claim your task with `baseballpy agent claim <task_id> [--agent <name>] [--files <paths>]`
   (which enforces 4-hour stale lock checks, updates `AGENT_BOARD.md`, and logs a `TASK_CLAIMED` record to `docs/agents/agent_log.jsonl`).
1. Find the task: a row in `docs/agents/BACKLOG.md` and, for source work, its card in
   `docs/agents/tracks/`. No row, no card: open an OpenSpec change, add the row to `BACKLOG.md`,
   and claim it on the Agent Board before writing any code.
2. Read the OpenSpec change (`proposal.md`, `design.md`, `tasks.md`, spec deltas) and the spec in
   `openspec/specs/` for the area. Code or docs edited without a covering change are a defect.
3. Do the **reuse check** of `docs/agents/TOOLING.md`: name the designated tool that covers what you
   are about to write, search the repository for an existing helper (`Grep`), and write the answers in
   the commit body. Custom code needs one sentence of evidence for what the tool cannot do.
4. Read the files the card lists, then only what you need beyond them.

### 14.2 Hard rules

1. **OpenSpec always.** Behavior change = spec delta with a `Verified by` test; decision = ADR; deviation
   from a design = "As built" note; finished change = merged deltas and archive.
2. **Tools before code.** Use the tool in `docs/agents/TOOLING.md` first. Do not hand-write what
   `pyarrow`, `polars`, `duckdb`, `narwhals`, `msgspec`, `httpx`/`tenacity`/`aiolimiter`, `dlt`,
   `pydantic-settings`, `click`/`rich` or `hypothesis` already do.
3. **Registry and data, not names.** No dataset, endpoint, stat type, league or season is named in code
   that should read it from the registry, a generator or a catalog. Prefer one declarative table and one
   generic function over parallel hand-written functions; if a fix needs a special case, find the
   mechanism that removes it.
4. **Reusable and flexible.** New behavior goes behind an existing `Protocol` (`IngestAdapter`,
   `SinkProtocol`, ...) or a new one with an ADR. A helper used twice moves to `core/`. No module reaches
   across the boundaries enforced by `tests/test_architecture.py`.
5. **No data left behind, no silent failure.** Sections 3, 7 and 11 apply to every slice.
6. **Small slices.** One card, one concern, the listed files only. Work found on the way becomes a new
   card or change, never a drive-by edit.
7. **Evidence or it is not done.** Paste command output for every gate and live check; say "not
   verified" plainly. Two failures of one gate need a written root-cause note before the next try.
8. **Search before a workaround** (section 13.2) and record what others do.
9. **Owner rules:** no Claude `Agent`/workflow subagents; delegation only to `agy` or `opencode` with a brief and a
   full diff review; Lahman only from `cbwinslow/lahman-database-csv` or user-supplied data; commit after
   every green slice, never push unless the owner says so; heavy runs go to the homelab; stop only
   background jobs you started.
10. **Product mission and reproducible outputs** (sections 0 and 15) come first: fix the workflow code with a test and rebuild the data with it; never settle for repairing files by hand.

### 14.3 Banned patterns (reviewers reject these)

- `import requests`, `aiohttp`, `urllib.request`, or `httpx` outside `core/http.py`; manual `sleep`/retry loops.
- Row-by-row Python loops over bulk data where Arrow, Polars or DuckDB can do it; pandas in `src/` outside the optional extra.
- Passing `dict` rows or untyped frames between layers; untyped VARCHAR columns; `safe=False` casts.
- Editing generated files (`tables.py`, `lb_tables.py`, `mlb_tables.py`, `stat_combos.py`, column dictionaries).
- Hard-coded counts, dataset lists or endpoint lists in docs or code; `# type: ignore` or `noqa` without a reason.
- Reading `os.environ` outside `core/config.py`; writing straight to a final filename instead of `.part` plus `os.replace`.
- New runtime dependencies without a change, an ADR, a `TOOLING.md` row and a reference excerpt.

### 14.4 Definition of done for a slice

Task ticked in `tasks.md`; evidence in the change's `design.md`; `BACKLOG.md` status updated and
`uv run python scripts/project_map.py` regenerated; checkout released with `baseballpy agent release <task_id> "<summary>"`
(updating `docs/agents/AGENT_BOARD.md` and `docs/agents/agent_log.jsonl`); gates green (`pytest`, `ruff
check`, `ruff format --check`, `mypy --strict src`, `docs generate --check`, `openspec validate --specs`);
one conventional commit whose body lists the reuse-check answers, the evidence and what is not verified.

### 14.5 When blocked

Stop, record the block (what was tried, dates, commands) in the change, mark the backlog row
OWNER/EXTERNAL, ask the owner once in one short list, and move to the next ready card. Never build a
workaround for a block you did not research (section 13.2).

---

## 15. Reproducible Outputs (binding for every change)

The same inputs MUST give the same outputs for every user, machine and run. This is how the library stays trustworthy as a PyPI package.

1. **Same means:** the same rows, schema (names, order, types), record counts, chunk and file names, partition layout and, for compacted files, the same bytes. Only values that are explicitly lineage or time-of-download (`fetched_at`, audit timestamps) may differ, and they live in manifests and logs, not in data columns unless documented.
2. **Inputs are pinned or kept.** Git-hosted sources are pinned to a SHA (`core/sources_lock.json`). Closed seasons and fixed date windows are repeatable. Live inputs (Statcast, the MLB API) cannot be pinned, so every response is kept (raw) and processing is deterministic: a rebuild from raw is identical.
3. **Deterministic processing.** Sort order, chunk grouping, file numbering and batching depend only on the data and the registry, never on thread timing, directory listing order, the clock, the machine or the number of workers. No machine-specific paths or values in outputs.
4. **Fix the code, not the files.** A data defect is repaired in this order: find the code path that produced it; write a test that fails; fix the code; rebuild the data with the workflow and compare with the old output; only then replace files. Hand edits of data files are a **last resort**: write them down in the change, keep a backup, and follow them with a rebuild by the workflow. If the workflow cannot rebuild the data, that is the bug.
5. **Prove sameness.** For each source there is a rebuild check: run the workflow for a small window into a scratch `BASEBALLPY_HOME` and compare it with the lake (row counts, schema digest, chunk content). A change to a workflow is not done until its output is shown to match what the previous code produced, or the difference is explained in the change.
6. **Jobs that fail are failures.** A stage, job or after-step that failed is never reported as done; the next run retries it.
7. **One layout for every user.** Readers (`baseballpy.read`, `baseballpy.sql`, the DuckDB views, `export`) see the same tables whether the data came from history or from the live stream, and whether files are parts, compacted files or segments.
8. **Real-time and history agree.** The live path and the bulk path write the same typed tables; a game fetched live and later rebuilt from history gives the same rows.
