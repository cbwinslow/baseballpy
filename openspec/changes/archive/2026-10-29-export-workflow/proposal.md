# Proposal: export-workflow

## Why
ADR 44 (owner, 2026-10-29): downloading, raw storage and strict typing stay ours; `dlt` is the
"send it anywhere" layer over the cached typed data. The owner now wants that built properly with
Chadwick as the model: everything strongly typed, Parquet, CSV, PostgreSQL (and DuckDB) all working
through one workflow, with the file paths settled and a rule set the other four sources can copy
with a short list of exceptions. Today: `ParquetSink`, `DuckDBSink`, `PolarsSink` and a `DltSink`
exist, but there is no CSV sink, no Postgres path from the CLI, no export folder or naming rule, the
`DltSink` lets `dlt` infer types, and nothing verifies an export.

## What changes
- One generic `export` function and `baseballpy export <source>[:<dataset>] --to parquet|csv|duckdb|postgres`, driven only by the dataset registry (schema, keys, partitioning, view name). No per-source code.
- A CSV sink (typed by a `.schema.json` sidecar), file paths under an `exports/` tier, and a `DltSink` that passes our Arrow schema to `dlt` as explicit column types and the registry key as primary key.
- Every export is verified (rows and schema read back) and audited.
- The rules in design.md become the standard other sources follow, with the exceptions listed.

## Out of scope
New sources; changing how data is downloaded or typed; warehouses other than Postgres and DuckDB (they work through the same `dlt` sink but are not tested here).

## Supersedes
`dlt-pipeline-core` tasks 3.1 and 3.2 (the rejected `DltAdapter` design) and BACKLOG B-43/B-44.
