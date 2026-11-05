# Design: Kalshi and Polymarket sources

## What the homelab holds (probed 2026-11-05, read-only)
PostgreSQL on `cbwdellr720`, database `mlb`, schema `raw`. Every column is `text` (loaded as-is); we add the types.

| Table | Rows (estimate) | Size | What it is |
|---|---|---|---|
| kalshi_series / event / market | 192 / 55,202 / 897,132 | 0.7 MB / 47 MB / 3.1 GB | catalog |
| kalshi_candle | 213,026,016 | 40 GB | price candles per market |
| kalshi_snapshot | 5,127,422 | 849 MB | live captures, 2026-08-02 to 2026-11-05 (86 days) |
| polymarket_event / market / outcome | 11,796 / 237,864 / 469,638 | 83 MB / 1.2 GB / 139 MB | catalog (all events carry the MLB sport tag) |
| polymarket_price | 604,314,240 | 110 GB | price history per outcome token |
| polymarket_snapshot | 9,266,530 | 1.5 GB | live captures, 2026-08-02 to 2026-11-05 |
| *_reject (in `mlb_rehearsal`) | n/a | n/a | rows an earlier loader refused |

Kalshi game-winner markets (`KXMLBGAME-*`): 9,394, opened 2025-04-16 to 2026-10-29. Homelab disk: 135 GB free. This PC: about 64 GB free. The live snapshots are the only as-of data that cannot be rebuilt later, so they are the most valuable rows.

## Standards (same as every other source)
- All HTTP through `core/http.py::HttpClient` (rate limit, in-flight cap, retries, one audit event per attempt in `logs/audit.jsonl`); adapters only through `IngestAdapter`; registry-driven datasets, no hard-coded lists.
- Raw bytes kept with sha256 in the manifest; processed Parquet (zstd) with strict Arrow schemas whose types come from probes of real data; unknown columns go to `_extras` with a one-time schema-drift warning; uncastable cells go to quarantine; nothing skipped silently (anything not ingestible stays registered as `unsupported` with probe evidence).
- Audit: ingest jobs and every request are logged; `audit speed` must stay inside the caps for the new hosts too (new `BASEBALLPY_RATE_*` entries, defaults chosen from each host's published limits).
- `dlt`: the project's rule is dlt for destinations (export), our client for downloading. Decision M3 below.

## Decisions for the owner
- **M1 Scope.** DECIDED 2026-11-05 by the owner: all MLB markets (every market type), no other sports.
- **M2 Transfer route.** Export the MLB subset from PostgreSQL to Parquet on the homelab, then copy the files (my pick); or read PostgreSQL live from this PC; or skip the import and re-download everything from the APIs.
- **M3 dlt.** Use our own client for downloads and dlt only for export (my pick), or build the downloaders with dlt's REST source.
- **M4 Live snapshots.** Keep the homelab collector running as is and import its rows, or move the collector into baseballpy later.

## Open questions to probe (task 1.2)
Kalshi: `/historical/cutoff` split, candle window limits (a long window returned HTTP 400), rate limits, whether fees are in the market record. Polymarket: `prices-history` needs explicit `startTs`/`endTs` for closed markets, batch limit of 20 token ids, history before Sept 2024, Gamma paging. For both: terms of use for redistributing data (so others can download it themselves, we ship code, not data).

## Measurement of the homelab export (2026-11-05, DuckDB 1.4.4 postgres extension on the homelab, read-only)
- Connection: `attach 'dbname=mlb host=localhost'` works with the saved login (`~/.pgpass`); the unix socket form fails (DuckDB's libpq looks in `/tmp` and finds no password). No password was read or typed.
- Plain table scan to zstd Parquet, untyped text columns: `kalshi_candle` 3,000,000 rows in 19 s (19.4 MB, 6.5 bytes per row); `polymarket_price` 5,000,000 rows in 12 s (6.9 MB, 1.4 bytes per row). Linear guess for the whole tables: Kalshi candles 213M rows, about 23 minutes and 1.4 GB; Polymarket prices 604M rows, about 25 minutes and 0.9 GB. These come from the first rows of each table, so treat them as rough; typed columns will change the size.
- A filtered export through a `where ... in (subquery)` join on the 604M-row table was slow (51,396 rows in 406 s), so the export should be a plain ordered scan, then filter in Parquet.
- Result: the full raw history fits easily on this PC as Parquet, so the MLB filter is not needed to save space; M1 (all MLB markets) costs little.
