# Market sources: Kalshi and Polymarket (MLB)

## Why
The prediction system needs market prices to compare against (see `modelling-data-needs`). The owner already collects them on the homelab PostgreSQL (database `mlb`, schema `raw`) and wants Kalshi and Polymarket handled exactly like the other sources: typed Parquet, DuckDB views, audit log, specs, tests, so other people can download the data themselves.

## What changes
Two new sources, `kalshi` and `polymarket`, each behind `IngestAdapter`, using the shared HTTP client (rate limit, retries, audit log), raw bytes kept with checksums, typed columns plus `_extras`, quarantine for bad cells. A one-time import brings the MLB part of the homelab tables in as the first history; the new downloaders then close the gap up to today and keep it current. Scope is MLB first (all MLB market types, so totals, props and season markets need no second download). No order placement, ever.
