# Design: export-workflow

## Evidence (2026-10-29, real Chadwick data, this PC, scratch lake)
| Test | Result |
|---|---|
| `dlt` filesystem destination, Parquet, 526,894 rows | schema identical to ours, 1.7 s |
| `dlt` filesystem destination, CSV | 2.6 s; default file names are timestamps and gzip, fixed with `layout="{table_name}.{ext}"` and `DATA_WRITER__DISABLE_COMPRESSION`; strings all quoted, nulls empty; no types in the file; `dlt` leaves `_dlt_loads`, `_dlt_pipeline_state`, `_dlt_version` and `init` bookkeeping inside the output folder |
| `dlt` to DuckDB | types exact (int32 INTEGER, int16 SMALLINT), 5.9 s |
| `dlt` to PostgreSQL 16 (embedded `pgserver`, no credentials) | 526,894 rows in 31 s; types exact (smallint, integer, varchar); merge of 1,000 rows on the registry key `key_person` kept the count at 526,894 (1.0 s) |
| `dlt` warning | "several column hints were different" when our Arrow schema met `dlt`'s inferred one: types must be passed explicitly |
| Servers | a PostgreSQL server listens on the homelab (port 5432); no credentials were used or needed; `pgserver` gives a disposable local Postgres for tests |

## The rules (apply to every source)
1. **Input is the cached typed Parquet** (`processed/`). Export never downloads and never re-types; a missing dataset says "run ingest first".
2. **The registry is the only source of names, schemas, keys and partitions.** `export` iterates `datasets_for(source)`; there is no per-source export code.
3. **Our Arrow schema is the contract.** Targets must return the same column names and types (Parquet, DuckDB, Postgres: exact; CSV: described by a `<dataset>.schema.json` sidecar listing each column's Arrow type and nullability, because CSV cannot carry types). Empty CSV cell = NULL, the same rule the project uses on import.
4. **Tool per kind of target.** Files (Parquet, CSV) are written by `pyarrow` through our sinks: exact types, clean names, atomic `.part` then rename. Databases (PostgreSQL, DuckDB, warehouses) go through `dlt`: it creates tables, maps types, and merges; we pass explicit column types and the registry key. In-memory targets (Arrow, Polars) need no export.
5. **Write modes.** `replace` (default for a whole dataset), `append`, `merge` (primary key = the registry `keys`, so re-running an export never duplicates rows). A season-partitioned dataset replaces or merges per season.
6. **Verify and audit.** After each export, rows and schema are read back and compared; the result and timings go to `audit.jsonl` (operation `export`, destination, rows).
7. **Credentials never touch files or commits.** Postgres comes from `--url` or the `BASEBALLPY_POSTGRES_URL` environment variable.
8. **Tests.** Parquet, CSV, DuckDB and Postgres round trips run in the normal suite; Postgres uses a disposable embedded server (dev-only dependency `pgserver`) and skips when it is not installed.

## File paths
- Exports root: `$BASEBALLPY_HOME/exports/` (new tier, overridable by `BASEBALLPY_EXPORTS_ROOT_OVERRIDE` and `--out`).
- Files: `<root>/<source>/<dataset>/<dataset>.parquet` or `.csv` (+ `<dataset>.schema.json`); season-partitioned datasets: `<root>/<source>/<dataset>/season=YYYY/<dataset>.parquet` (the same Hive-style layout as `processed/`).
- Databases: table name = the registry `view` name (`chadwick_register`), the same name the DuckDB views use, in a schema/dataset named `baseballpy` (configurable).
- DuckDB file: `<root>/baseballpy.duckdb` unless `--out` names one.

## Decisions for the owner (pros, cons, recommendation in the reply to the owner)
A. One tool for all targets (`dlt` for files too) or the hybrid above. Recommendation: hybrid.
B. Database table names: flat registry names in one schema (recommended) or schema per source.
C. Default export folder `exports/` inside the lake (recommended) or always require `--out`.
D. `pgserver` as a dev-only test dependency (recommended) or tests against the homelab Postgres.

## Exceptions other sources will need (decided per source in their reviews)
- Season-partitioned datasets (Statcast, Retrosheet events, MLB per-season): per-season replace/merge.
- Very large datasets (Statcast pitches, MLB all-time pools): stream batches (`RecordBatchReader`) instead of one table.
- Datasets whose registry key is not unique per request (some MLB endpoints): `append` or `replace` only until a unique key exists.
