# Design: Harden Ingestion Core

## 1. HttpClient (H-2, H-9)
```
HttpClient(rate: RateLimitConfig)
  .get(url, *, params, headers, etag) -> HttpResult        (async)
  .get_sync(url, ...) -> HttpResult                         (sync facade)
HttpResult: status, content, etag, not_modified, url, elapsed_seconds
```
- One `httpx.AsyncClient(http2=True, limits=Limits(max_connections=20, max_keepalive_connections=10))`, reused.
- Limiter chosen by `urlparse(url).hostname` from `RateLimitConfig.host_rates` (fallback `default_requests_per_second`).
- Global `asyncio.Semaphore(max_concurrency)`; order: semaphore, limiter, request.
- Retry: `tenacity.AsyncRetrying` on `httpx.TransportError` and statuses 408/425/429/500/502/503/504. Wait = `wait_exponential_jitter(initial=backoff_factor, max=60)`; `Retry-After` overrides. Other 4xx are never retried. `stop_after_attempt(max_retries)`.
- Sync facade: a daemon thread owns one event loop (`run_coroutine_threadsafe`), so sync and async callers share the same limiter/semaphore/pool and the facade is safe in Jupyter.
- 304 returns `not_modified=True` with empty content.
- Plain `httpx` underneath, so `respx` mocks work.

## 2. Freshness (H-1)
Manifest entries gain `fetched_at`, `season`. Rules:
- Season-partitioned dataset with `season < current_year` -> immutable.
- Current season / reference data -> fresh iff `now - fetched_at < ttl(dataset)`.
- Default TTLs (seconds): schedule 900, standings 900, boxscore 60 until final (then immutable), roster 21600, transactions 3600, statcast current-season 21600 (trailing 3 days always revalidated), leaderboards 86400, people/teams/venues 86400, chadwick revalidated against remote SHA (24 h), lahman/retrosheet immutable once downloaded unless `refresh`.
- Override: `BASEBALLPY_CACHE_TTL_SECONDS` (global default) and per-dataset `CacheConfig.ttl_overrides`.
- `CacheConfig.today` injectable for tests.

## 3. Quarantine (H-3, H-4, H-10, H-11)
`Quarantine.write(source, dataset, records, reason, context=None) -> Path`
- `quarantine/<source>/<YYYY-MM-DD>/<dataset>-<uuid8>.jsonl`, one JSON per line: `{ts, source, dataset, reason, context, payload}`; bytes are base64.
- Emits `logging.warning` and an audit event `quarantine_write`.
- `checked_cast(array, type, *, quarantine, source, dataset, column)`: safe Arrow cast; on `ArrowInvalid`/`ArrowNotImplementedError` falls back to per-value casting, nulls only failing cells and quarantines them. `safe=False` is banned.

## 4. Manifest (H-6)
- `save()` acquires `<manifest>.lock` (`os.open(O_CREAT|O_EXCL)`, PID inside, 10 s timeout, stale after 60 s), re-reads disk, merges chunk dicts (later timestamp wins), writes atomically, releases.
- Corrupt/non-dict JSON: rename to `.corrupt-<ts>`, `logging.error`, start empty.
- All public methods guarded by an `RLock`.

## 5. Atomic writes (H-6)
`.part` name `<name>.<pid>.<uuid8>.part`; `flush`+`fsync` for bytes writes; `cleanup_stale_parts(dir, older_than=1h)` helper used at extractor start.

## 6. Audit (H-5, H-8)
One `_TrackState` and one `_finalize()` function used by both `track` and `async_track`. Status: success -> SUCCESS; `CancelledError`/`KeyboardInterrupt` -> CANCELLED; other -> FAILURE. `get_audit_logger()` is `lru_cache`d; `default_audit_logger` is a proxy. `read_events` logs a warning with the number of skipped corrupt lines.

## 7. Sinks (H-7)
- `quote_ident()` validates `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$` and double-quotes each part.
- `append`: if table exists, `ALTER TABLE ADD COLUMN` for new source columns (logged drift), then `INSERT INTO t BY NAME SELECT * FROM src`.
- `upsert(key_columns)`: first write creates the table and a unique index on the keys; later writes use `INSERT OR REPLACE ... BY NAME`.
- `replace` with zero rows creates/overwrites an empty typed table.
- `write_stream` uses a single connection and one audit event.
- `ParquetSink`: `atomic_write_parquet`; `partition_by` writes a dataset into a temp dir then renames files into place.
- `PolarsSink`/`DltSink`: `write`/`write_stream` return `int`; `DltSink` accepts `destination` (`duckdb|postgres|snowflake|bigquery|motherduck`), `primary_key`, `write_disposition` (`append|replace|merge`).

## 8. Statcast truncation (H-9)
`_fetch_window(start,end)`: if `rows >= 25_000` and `start < end`, bisect and recurse; a capped single day raises `TruncatedResultError` and is never cached. An audit event with `error="row_cap_bisect"` is logged per bisection. Zero-row windows get a manifest entry (`records_count=0`) so they are not refetched.

## 9. Header-based parsing (H-10)
`map_by_header(header, schema)` returns column positions by normalized name; unknown columns are preserved as `string` columns (logged once per file); missing columns are NULL-filled.

## Test strategy
Unit (respx for HTTP, `tmp_path` for FS), property-based (Hypothesis), concurrency (threads writing one manifest/target), cancellation (`asyncio.wait_for` + `track`), plus the manual live checklist in `tasks.md` §9.
