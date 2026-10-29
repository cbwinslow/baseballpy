# Architecture

## Layers

`sources/<source>/` (extract and normalize) produces strict Arrow schemas, which `ProcessedStore` and `RawStore` (`core/stores.py`) write into the lake, and `database.py` exposes the result as DuckDB views. All HTTP goes through `core/http.py::HttpClient` (per-host rate limit, HTTP/2, retries); exceptions are never swallowed, and cells that cannot be cast go to `core/quarantine.py`.

```text
provider  ->  source extractor + normalizer  ->  Arrow table (strict schema)
          ->  RawStore (immutable bytes + sha256)  /  ProcessedStore (zstd Parquet)
          ->  DuckDB views (views only; data stays in Parquet)
```

## Lake layout (v2)

Everything lives under `$BASEBALLPY_HOME` (default `~/.baseballpy`):

| Path | Content |
|---|---|
| `raw/<source>/<dataset>/[season=YYYY/]` | immutable upstream bytes, with a sha256 in a per-directory manifest |
| `processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet` | typed Parquet, one dataset per directory |
| `quarantine/` | dead-letter files for cells that failed coercion |
| `cache/http/` | HTTP validators and cached listings |
| `databases/baseball.duckdb` | views only |
| `logs/audit.jsonl` | one structured event per operation |

`LakeConfig` path helpers never create directories; writers do.

## The dataset registry

`core/datasets.py` and `sources/catalog.py::register_all()` register every `DatasetSpec` (schema, partition, keys, view name, documentation anchor, and how `ingest` reaches it: `default`, `opt_in`, `on_demand` or `api_only`). Views, docs generation and tests iterate the registry; nothing else hard-codes a dataset name. Column dictionaries in `docs/sources/<source>.md` are generated between `<!-- BEGIN GENERATED:... -->` markers.

## The ingest boundary

Sources meet the runner and the CLI only through `baseballpy.ingest.IngestAdapter` (`source`, `all_seasons`, `plan`, `run`); sinks meet the rest through `SinkProtocol`. `tests/test_architecture.py` and `tests/test_ingest_contract.py` enforce the import boundaries. `plan_jobs` turns a selection into jobs, `run_jobs` runs them with bounded concurrency, records one audit event per job and handles Ctrl-C (sequential runs interrupt promptly; pool runs start no new job).

## Generated schemas

Never edit these by hand: `sources/lahman|chadwick|retrosheet/tables.py`, `sources/statcast/lb_tables.py`, `sources/mlb_api/mlb_tables.py` and `stat_combos.py`. Their generators in `scripts/` probe the live provider, widen types over samples, verify keys and write `docs/*_probe.json`; unknown columns land in `_extras` with a one-time `schema_drift` warning.

## Data workflow

How files are downloaded, cached, fingerprinted and checked, and how to read or export the data: [Data workflow](DATA_WORKFLOW.md).

## Decisions

The reasoning behind each choice is recorded as an ADR in [Design decisions](DECISIONS.md); behavior requirements live in `openspec/specs/`.
