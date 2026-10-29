# Design: data-workflow-standard

## The standard workflow (proposed; same for every source)
1. **Check**: ask the shared `is_current(entry, upstream_fingerprint)`; if current, serve the cached Parquet.
2. **Download** through `HttpClient` (rate limit, retries, User-Agent) into `raw/` with an atomic write; record sha256, size, `source_ref` and the upstream fingerprint in the manifest.
3. **Type** into Arrow with the strict generated schema; bad cells go to quarantine.
4. **Store** typed Parquet in `processed/` (atomic, footer checked), manifest entry COMPLETED.
5. **Use**: read as Arrow, Polars or DuckDB view; export through sinks.
Re-typing from `raw/` without the network already exists (`reprocess`).

## Decision A: how do we notice an upstream change?
- **A1 Pin plus time-to-live (today).** Pros: simple, reproducible. Cons: stored hashes unused; a git source only changes when someone moves the pin; no per-file view.
- **A2 Per-file fingerprint (git blob SHA from the tree listing, ETag or Last-Modified for plain HTTP, content sha256 for APIs), one shared function.** Pros: one cheap check says exactly which files changed, so only those are downloaded and re-typed; uses the hashes we already store; same rule everywhere. Cons: moderate new code in the shared layer; API sources (Statcast, MLB) still have to download to learn anything, so they keep a time-to-live for how often to ask.
- **A3 Always re-download and compare sha256.** Pros: simplest, always right. Cons: wasteful and rate-limit-heavy for Statcast and MLB.
- **Recommendation: A2.** Git sources get exact per-file checks for one API call; HTTP sources use validators when the server sends them; API sources keep the time-to-live but skip re-typing when the downloaded bytes hash the same.

## Decision B: what is `dlt`'s job?
- **B1 Optional destination only (today).** Pros: nothing to rebuild; Postgres and warehouses work. Cons: no uniform user-facing export, no CSV.
- **B2 The "send it anywhere" layer reading our cached Parquet** (extract and typing stay ours; a registry-driven `baseballpy export --format parquet|csv|duckdb|polars|postgres --out ...`). Pros: matches the owner's goal (typed Arrow in the middle, many destinations out); keeps every existing tool; no per-endpoint code. Cons: needs a CSV sink and a small export command; Postgres needs an extra install.
- **B3 `dlt` also does extract and typing (the rejected B-43 design).** Pros: less custom flatten code. Cons: the spike showed it loses parent context and cannot merge on Parquet; the owner rejected it.
- **Recommendation: B2.** It is decided in the B-43 brainstorm; this change only needs B1/B2 to be compatible.

## Decision C: read path (documented, no new code except export)
Arrow: `ProcessedStore.read(spec)`; Polars: `PolarsSink` or `pl.scan_parquet` on the files; DuckDB: `baseballpy db sync` views; PostgreSQL and warehouses: `DltSink`; files: Parquet today, CSV with the export command.

## Effect on `chadwick-source-review`
Tasks 5.1 and 5.2 (split ingest from the lookup index; per-dataset jobs) are compatible with every
option and can go ahead. Task 5.6 (store the upstream README) should record the git blob SHA too once 2.1
of this change lands. The lookup index (5.4) reads the cached Parquet; it never re-downloads.

## As built (2026-10-29): tasks 2.1 to 2.4 and 3.1
- `core/upstream.py`: `Fingerprint(kind, value, origin)` and `is_current(entry, refresh, expected, probe, on_confirmed, ttl_seconds, season, today, now)`. It generalises what Chadwick did by hand: pinned commit (an `expected` fingerprint decides alone), time-to-live, then one upstream probe. `stored_fingerprint` reads the new `upstream` field and falls back to the old `sha` / `etag` fields, so lakes written before this change keep working.
- `RawStore.put(upstream=...)` records the fingerprint next to the sha256 (a plain `etag` becomes an ETag fingerprint).
- Chadwick: `is_cache_current` is now a call to `is_current` (same behavior: tests in `test_sources_hardening.py` pass unchanged); every downloaded file and the README record their git blob SHA and origin, the commit chunk records the commit.
- `baseballpy cache check [--source S] [--upstream] [--json]` (`cache_check.py`, `cli_cache.py`): sha256 of every raw file against its manifest (exit 1 when missing or corrupt), and with `--upstream` the git fingerprints against the latest tree of each repository (the latest-commit lookup and one cached tree listing per repository). Run on a real Chadwick lake: 20 of 20 files OK, `--upstream` shows 0 changed; tampering with one shard and deleting another were reported as corrupt and missing.
- `JobResult.cache_hit` (default false): the runner sets the audit `cache_hit`; Chadwick reports true when nothing had to be typed. Real rerun: audit shows `cache_hit=True`, 0.04 s.
- `docs/DATA_WORKFLOW.md` written (corrects the loose description the owner pasted: real folder layout, no "2 ms" claim, current rule per source) and added to the site nav.
- Not yet: Lahman, Retrosheet, Statcast and MLB API still use their older rules and store no fingerprints (tasks 2.5 to 2.8, inside their own source reviews); `cache check --upstream` reports their files as "no fingerprint".
