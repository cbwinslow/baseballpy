# Change Proposal: Harden Ingestion Core (correctness, resilience, protocol conformance)

## Context & Motivation
A full-repo review (2026-10-26) found that although tests, `ruff` and `mypy --strict` are green, the
core has correctness and AGENTS.md-compliance defects that silently corrupt, lose or mis-report data.
Each finding has an ID (`H-n`) referenced by `tasks.md`, tests and the spec deltas.

## Findings Fixed by This Change
| ID | Defect | Violated mandate |
|----|--------|------------------|
| H-1 | `CacheConfig.ttl_seconds` is never read. Current-season schedule/standings/rosters are frozen forever; an in-progress boxscore is cached as final; recent Statcast chunks never pick up scoring corrections. | AGENTS §3.3 |
| H-2 | `AsyncLimiter`/semaphore objects are created but unused by MLB API, leaderboard, Retrosheet, Lahman and Chadwick fetch paths. Each request builds a fresh sync `httpx.Client` (no HTTP/2, no pooling, no limit, no retry). | AGENTS §4.1-4.3 |
| H-3 | Silent failures: streamer `except Exception: pass`; `ManifestTracker._load` resets silently on corrupt JSON; Chadwick SHA lookup swallows all errors; Retrosheet downloader treats 404 as success and marks a season COMPLETED with missing files; parsers coerce bad values to NULL with no log. | AGENTS §7.1 |
| H-4 | `QuarantineConfig`, `StreamingConfig`, `PipelineConfig`, `get_config()` and `mlb_api/models.py` are dead code; no dead-letter quarantine exists. | AGENTS §7.1, §10.1 |
| H-5 | `AuditLogger.track` catches `Exception` only, so `CancelledError`/`KeyboardInterrupt` are logged as SUCCESS. Statcast never records `cache_hit`. Sync/async bodies duplicated. | AGENTS §6.1 |
| H-6 | `ManifestTracker` is not thread/process-safe (stale copies, last-writer-wins) despite its docstring. `atomic_write` uses a fixed `.part` suffix so concurrent writers collide; no fsync. | AGENTS §8 |
| H-7 | `DuckDBSink` interpolates `table_name` into SQL; positional appends break on drift; zero-row `replace` is a no-op; `write_stream` reconnects per batch; no idempotent upsert. `ParquetSink` is non-atomic and ignores partitioning. `PolarsSink`/`DltSink` do not satisfy `SinkProtocol`. | AGENTS §3.3, §8.1 |
| H-8 | Module-level singletons (`_default_extractor`, `_default_source`, `default_audit_logger`) are built at import: they create directories and freeze configuration. | AGENTS §10.1 |
| H-9 | No detection of Savant's 25,000-row cap (truncated chunk cached as complete). Retries fire on 4xx, ignore `backoff_factor`, miss `ConnectError`/`RemoteProtocolError`/`PoolTimeout`. | AGENTS §4.1, §4.3 |
| H-10 | Positional CSV mapping in Retrosheet reference parsers (header discarded); Lahman drops unknown columns; MLB normalizer int casts raise instead of quarantining. | AGENTS §3.1, §7.2 |
| H-11 | `safe=False` Arrow casts in the Statcast normalizer silently truncate (1.9 -> 1) and overflow. | AGENTS §7.1 |
| H-12 | Hypothesis is a dev dependency but unused. | AGENTS §9.5 |

## Proposed Changes
1. `baseballpy.core.http.HttpClient` — per-host `AsyncLimiter`, bounded semaphore, HTTP/2 pooling, jittered `tenacity` retry (408/425/429/5xx + transport errors, `Retry-After`, `backoff_factor`), conditional `ETag`, sync facade sharing the same limits. All sources migrate to it.
2. `baseballpy.core.freshness` — `CachePolicy` + `is_fresh()`: completed historical seasons immutable; current-season/reference data by per-dataset TTL.
3. `baseballpy.core.quarantine` — JSONL dead letters under `quarantine/<source>/<date>/`; `checked_cast` helper replaces unsafe casts.
4. `ManifestTracker` — lockfile, merge-on-save, `RLock`, corrupt-file preservation and loud logging.
5. `atomic_write` — unique `.part` names, fsync, stale cleanup.
6. `AuditLogger` — shared sync/async core, `CANCELLED` status, lazy singleton.
7. Sinks — identifier validation, `BY NAME` inserts with drift handling, keyed upsert, atomic partitioned Parquet, protocol-conformant Polars/dlt sinks.
8. Lazy `get_default_*()` factories replace import-time singletons.
9. Statcast — row-cap detection with automatic window bisection, corrected retry policy, zero-row manifest entries.
10. Header-based column mapping with unknown-column preservation.
11. Wire `StreamingConfig`/`QuarantineConfig`/`PipelineConfig`; drop dead `models.py`.
12. Hypothesis property tests.

## Out of Scope
Folder layout (`restructure-data-lake`), new endpoints (`complete-source-coverage`), CLI/Pipeline (`unified-pipeline-and-cli`).

## Impact
`default_audit_logger` becomes a lazy proxy (attribute access unchanged); `DltSink.write` returns `int`. Recorded in ADR 22.
