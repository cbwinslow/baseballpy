# Proposal: lake-schema-evolution

## Why
B-303 gave 142 MLB datasets typed columns (`name_slug` and others) that used to sit in the `_extras` JSON column. Files already in the lake lack those columns. `baseballpy.read` failed on any dataset that mixed old and new files (`SchemaError: extra column in file outside of expected schema`), and the strict DuckDB views took their columns from the first file, so SQL quietly could not see the new columns. ADR 86 fixed only the rewrite of compacted files. Without this change every future schema regeneration repeats the problem.

## What changes
- `read` and `scan_dataset` scan under the registered schema: a column an older file lacks comes back empty, an unknown column is still refused.
- `core/evolve.py`: `promote_extras` moves values from `_extras` into the new typed columns (same cast and quarantine rules as an ingest) and removes the moved keys; `migrate_dataset` rewrites every file whose columns differ from the registered schema (verify, atomic swap, compacted chunk maps kept) and marks a chunk as matching the schema only when its old fingerprint proves the schema was the only difference.
- `baseballpy compact` runs the migration first; `catalog layout` names `compact` as the fix; `db sync` warns when a strict view would hide columns.

## Impact
Specs: `lake-access`. ADR 87 (extends ADR 73 and 86). Code: `frames.py`, `access.py`, `database.py`, `layout_audit.py`, `cli_compact.py`, `core/compact.py`, `core/evolve.py`. Tests: `tests/test_schema_evolution.py`.
