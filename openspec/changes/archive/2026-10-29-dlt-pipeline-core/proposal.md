# Proposal: dlt as the extract-normalize-load core

## Why
The owner's design intent (ADR 4) is that `dlt` is the bridge from source data to any format or destination. What was built instead is our own normalize/flatten/`_extras`/resume code with `dlt` as one optional sink (`sinks/dlt.py`, 1 file of 100+). Much of the friction of the last two days (schema drift needing generator reruns, `_extras`, flattening, resume manifests, one sink per destination) is what `dlt` does natively. Rule: use the installed tools first; write our own code only for what they cannot do.

## What dlt gives us (verified present in dlt 1.31.0 on 2026-10-29)
- Extract, normalize, load as separate steps; Arrow, Polars and JSON all load natively.
- Schema inference with evolution, and schema contracts per `tables`/`columns`/`data_type` (`evolve`, `freeze`, `discard_row`, `discard_value`); a type conflict becomes a variant column instead of an error.
- Nested JSON unnested into child tables with parent keys; replaces `flatten.py` and `_extras`.
- Incremental cursors and pipeline state (resumable runs), write dispositions `append`, `replace`, `merge` (primary keys, SCD2).
- `dlt.sources.rest_api`: declarative REST sources with paginators and parent-child resources (our fan-out scopes).
- Destinations including DuckDB, filesystem (Parquet, Delta, Iceberg), Postgres, BigQuery, Snowflake, ClickHouse, MotherDuck; `_dlt_load_id` lineage.

## What dlt does not do for us
MLB blocking and the 406, polite rate limiting (our `HttpClient`, passed to dlt as its session), Statcast's 5-day window grid and 25,000-row bisect, Retrosheet and Chadwick parsing, immutable raw bytes with sha256, quarantine of uncastable cells, our strict-schema guarantee (kept as column hints plus contracts).

## What
A bounded spike (three endpoints, about 20 requests) comparing the dlt path with the current path; an ADR that adopts or rejects it with that evidence; then, only if adopted, a `DltAdapter` behind `IngestAdapter` whose resources are generated from the dataset registry. No rewrite before the evidence.

## Out of scope
League-wide `v1/stats` (blocked, B-30); Statcast and Retrosheet migration (a later change if the spike wins).
