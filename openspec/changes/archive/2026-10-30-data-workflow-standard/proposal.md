# Proposal: data-workflow-standard

## Why
The owner asked: do all sources download, cache, hash, type and expose their data the same way, and can
users easily get the data into pyarrow, polars, DuckDB, PostgreSQL and files? The audit below
(2026-10-29, from the code and ADRs) says: the storage layout is consistent, the "is my cached copy still
current?" rule is not, the hashes we store are never used, and there is no single documented read/export
path. Fixes to the Chadwick adapter (tasks 5.1, 5.2 of `chadwick-source-review`) depend on these decisions.

## The workflow as it is today (audit)
Same for all five sources: download through `HttpClient` -> `raw/<source>/<dataset>/` (bytes, size, sha256
and `source_ref` in a per-folder manifest, atomic write) -> typed Arrow -> `processed/.../part-*.parquet`
(zstd, footer checked, manifest entry COMPLETED) -> DuckDB views over the Parquet. Everything lives under
`$BASEBALLPY_HOME` (default `~/.baseballpy`; separate overrides exist for raw, processed, quarantine,
HTTP cache and the database file).

Different per source (how "still current" is decided):
| Source | Rule today |
|---|---|
| Chadwick, Lahman, Retrosheet | pinned git commit in `core/sources_lock.json`; cached copy is current if it was fetched at that commit; Chadwick also revalidates a floating ref every 24 h |
| Statcast, MLB API | time-to-live per dataset family (6 h to 24 h and shorter for live data); seasons before this year are never re-fetched |

Gaps found:
1. **Stored hashes are never checked.** `RawStore.verify()` (sha256 of the local file against the manifest) has no callers.
2. **ETag is saved but not used** by any batch extractor (only the live stream sends `If-None-Match`), although `HttpClient` supports it.
3. **No per-file upstream fingerprint.** For GitHub sources we already download the tree listing, which carries each file's blob SHA, but we do not store it, so we cannot tell which single file changed.
4. **`dlt` is not in the flow.** It exists only as an optional destination sink (`DltSink`); its wider role is the open redesign BACKLOG B-43.
5. **Reading and exporting is scattered.** Arrow via `ProcessedStore.read`, Polars via `PolarsSink`, DuckDB views via `db sync`, PostgreSQL only through `DltSink` in Python, no CSV, and the CLI only exposes the DuckDB and Parquet sinks.
6. **The update rules are written nowhere in one place** (ADR 13, 17, 22, 23 each cover a part).

## What changes
After the owner decides (design.md), one shared mechanism and one documented page: every raw file records
an upstream fingerprint, one function `is_current()` replaces the per-source checks, `baseballpy cache
check` verifies hashes and reports stale files, and "How to get your data" documents every way to read
or export it. Sources are moved onto it one at a time inside their source tracks.

## Out of scope
Rewriting working extractors; the dlt redesign itself (B-43, owner brainstorm); new sources.
