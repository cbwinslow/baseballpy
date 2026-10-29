# Handoff: B-43 must be redesigned (owner said the design was wrong, 2026-10-29)

Read this first in the next session, then brainstorm with the owner before writing any code.

## What the owner said (verbatim intent)
- Keep every tool we use (pyarrow, dlt, polars, duckdb, narwhals, msgspec, httpx, pydantic, tenacity, aiolimiter, rich, click ...); use them *better*, do not remove them. My B-43 proposal (a `dlt` module that replaces the extractor, normalizer and flatten code) was wrong.
- The goal is simple: uniform, reusable, polymorphic ingestors that download from the endpoints (threaded) into typed data written to files and folders the user chooses, and that make it easy to send the same data to Parquet, CSV, PostgreSQL, Polars, DuckDB and so on.
- Flexible abstraction and uniform code over per-endpoint patches; follow `AGENTS.md`; every change goes through OpenSpec; delegate simple, well-specified code to `agy` (and review every diff).

## What already exists (verified 2026-10-29)
- Interchange type: PyArrow tables. `SinkProtocol` (`core/protocols.py`): `write(table, destination, **kw)` and `write_stream(reader, destination, **kw)`.
- Sinks in `src/baseballpy/sinks/`: `parquet.py`, `duckdb.py`, `polars.py`, `dlt.py` (dlt: duckdb, postgres, snowflake, bigquery, motherduck). **No CSV sink exists** (a gap).
- `narwhals` (ADR 11) is the dataframe-agnostic layer (`frames.py`, Chadwick register); `dlt` (ADR 4) is the bridge to databases and warehouses.
- Sources are declarative: 364 MLB endpoints in `sources/mlb_api/endpoints.py`, one generic extractor/normalizer/flattener, strict generated Arrow schemas for 366 MLB datasets, a threaded runner (`ingest/runner.py`, `concurrency`), lake location from `BASEBALLPY_HOME`.

## Questions to settle in the brainstorm
1. Where exactly does `dlt` belong: as the sink layer for every destination (extend `SinkProtocol` implementations: CSV, Postgres, Polars, ... all fed Arrow), as the normalize step, or both? The owner's wording points at "typed Arrow in the middle, many destinations out".
2. How do the existing sinks become one uniform, user-selectable output (`--format parquet|csv|postgres|polars|duckdb --out PATH`) driven by a registry, not per-format code?
3. Which of the flatten / `_extras` / drift code is really a problem, and which just needs better use of existing tools? (The spike showed `dlt` matches our columns but loses parent context and cannot merge on Parquet.)
4. The reference docs (`docs/references/`, B-45) should settle endpoint routes and column types before the design is fixed.

## State
- `dlt-pipeline-core` (ADR 42) is UNDER REVIEW: its tasks 3.1 and 3.2 (B-43, B-44) are not valid as written. The spike (`scripts/dlt_spike.py`, tasks 1.x) stands as evidence only.
- Not pushed since 692b1c7 (a few local commits). League-wide MLB `v1/stats` still answers 406 (B-30).
