# How the data flows: download, cache, check, use

This page explains what happens to data from the moment `baseballpy` asks a provider for it until you
use it, and how it knows a saved copy is still good. The decisions behind it are
[ADR 43](DECISIONS.md) (how changes are noticed) and [ADR 44](DECISIONS.md) (how data is sent elsewhere).

## The five steps (the same for every source)

1. **Check.** Is the saved copy still current? If yes, nothing is downloaded.
2. **Download.** One shared client (`HttpClient`) fetches the file politely (rate limits, retries) and
   writes it to `raw/` exactly as the provider sent it. The file's sha256 and the provider's own
   fingerprint of that version are written to a small `manifest.json` next to it.
3. **Type.** The raw bytes become an Arrow table with a strict schema. Cells that cannot be converted go
   to `quarantine/`, never silently to nulls.
4. **Store.** The table is saved as compressed Parquet in `processed/`, written to a temporary file
   first and renamed only when its footer checks out.
5. **Use.** Read it from Python, query it with SQL, or send it somewhere else (see below).

Because `raw/` is kept, the typed Parquet can be rebuilt offline if a parser changes.

## Where the files live

Everything is under one folder, `$BASEBALLPY_HOME` (default `~/.baseballpy`):

| Folder | What is in it |
|---|---|
| `raw/<source>/<dataset>/[season=YYYY/]` | the provider's files unchanged, plus `manifest.json` (sha256, size, fingerprint) |
| `processed/<source>/<dataset>/[season=YYYY/]part-*.parquet` | typed Parquet, one folder per dataset |
| `quarantine/` | cells that failed conversion |
| `cache/http/` | saved listings and validators |
| `databases/baseball.duckdb` | views over the Parquet, no copies |
| `logs/audit.jsonl` | one line per operation (rows, seconds, cache hit) |

Move or split the lake with environment variables: `BASEBALLPY_HOME` moves everything;
`BASEBALLPY_RAW_ROOT_OVERRIDE`, `BASEBALLPY_PROCESSED_ROOT_OVERRIDE`, `BASEBALLPY_QUARANTINE_ROOT_OVERRIDE`,
`BASEBALLPY_HTTP_CACHE_ROOT_OVERRIDE` and `BASEBALLPY_DATABASE_PATH_OVERRIDE` move one part.

## How "is my copy still current?" is decided

One function, `baseballpy.core.upstream.is_current`, makes the decision. In order:

1. `--refresh`, or nothing saved, or the last download did not finish: not current.
2. If the caller knows which upstream version it wants (a pinned git commit, a file's git fingerprint):
   current exactly when the saved fingerprint equals it. No timer.
3. Otherwise trust the copy while its time-to-live has not run out (past seasons never expire).
4. After that, ask the provider once (for example "what is the latest commit?") and compare. If the
   provider cannot be reached, the saved copy is served and a warning says so.

A *fingerprint* is whatever the provider offers to say a file changed: a git blob or commit SHA, an
ETag or Last-Modified header, or the hash of the downloaded bytes.

Status by source: Chadwick uses the shared function and stores a git fingerprint for each file. The other
four sources still use their older rules (Lahman and Retrosheet a pinned git commit; Statcast and the
MLB API a time-to-live) and move over inside their own source reviews.

## Checking the cache

```bash
baseballpy cache check              # offline: every raw file against its recorded sha256
baseballpy cache check --upstream   # also: have git files changed upstream? (2 GitHub requests per repo)
```

Exit code 1 means a file is missing or damaged. A file that changed upstream is only reported; refresh
it with `baseballpy ingest <source> --refresh`.

## Using the data

| You want | Use |
|---|---|
| An Arrow table in Python | `ProcessedStore().read(get_dataset("chadwick", "register"))`, or the source function (`bp.statcast(...)`, `bp.chadwick.get_register()`) |
| Polars | `bp.to_polars(table)` or `pl.scan_parquet(...)` on the Parquet files |
| SQL | `baseballpy db sync`, then `bp.connect_db()` or `baseballpy db query` |
| Files, DuckDB or PostgreSQL | `baseballpy export` (next section) |

## Exporting: Parquet, CSV, DuckDB, PostgreSQL

```bash
baseballpy export chadwick --to parquet                 # all four Chadwick datasets
baseballpy export chadwick:register_links --to csv      # one dataset
baseballpy export statcast:pitches --to parquet --seasons 2023-2024
baseballpy export chadwick --to duckdb --out my.duckdb
BASEBALLPY_POSTGRES_URL=postgresql://user:pw@host:5432/db baseballpy export chadwick --to postgres
```

The same function (`baseballpy.export.export_dataset`) serves every source; it takes names, types, keys and season layout from the dataset registry and reads only the cached typed Parquet (run `baseballpy ingest` first; a source-wide export skips datasets with nothing cached, a named dataset with nothing cached is an error).

| Target | What you get | Tool | Modes |
|---|---|---|---|
| `parquet` | `exports/<source>/<dataset>/<dataset>.parquet` (zstd) | pyarrow | replace |
| `csv` | `<dataset>.csv` (UTF-8, header, empty cell = NULL) plus `<dataset>.schema.json` holding every column's Arrow type | pyarrow | replace |
| `duckdb` | tables named by the registry view name (`chadwick_register`) in `exports/baseballpy.duckdb` (or `--out file.duckdb`) | native DuckDB sink | replace, append, merge |
| `postgres` | tables named by the registry view name in schema `baseballpy` (`--schema`), created and typed by `dlt` | `dlt` | replace, append, merge |

- **Where:** files go to `$BASEBALLPY_HOME/exports/` (`BASEBALLPY_EXPORTS_ROOT_OVERRIDE` or `--out` moves them); season-partitioned datasets get `season=YYYY/` folders like `processed/`. The PostgreSQL URL comes from `--url` or `BASEBALLPY_POSTGRES_URL`, never from a file.
- **Typed:** Parquet, DuckDB and PostgreSQL keep the schema (through `dlt`, PostgreSQL stores a `float` column as `double precision` and `int8` as `smallint`; nothing is lost). CSV cannot hold types, so read it back with `baseballpy.sinks.csv.read_csv_typed(path)`, which uses the sidecar. Nested columns (a list column) cannot go to CSV; use Parquet.
- **Modes:** `replace` (default) rewrites the target, `append` adds the rows, `merge` updates rows with the same registry key and never duplicates. Merge is refused for a dataset whose key column has empty values (for example `chadwick.register_names`): use replace or append there. Files are always replaced.
- **Checked:** every export is read back (rows, types, and for files the full data) unless `--no-verify`, and written to `logs/audit.jsonl` as an `export` event. A difference fails the command.

Measured on the Chadwick datasets (555,829 rows, this PC, whole command including start-up): Parquet 6.9 s (24 MB), CSV 6.8 s (75 MB), DuckDB 10.7 s (65 MB), PostgreSQL 39 s.

## Onboarding a source (the checklist other sources follow)

A source needs no export code. It is exportable when:
1. each of its datasets is in the registry with a schema, a `view` name, a `keys` tuple and its season partitioning (`partition`), and ingest stores the typed Parquet under `processed/`;
2. `baseballpy export <source> --to parquet` and `--to csv` succeed and verify (a dataset with a nested column is the only expected CSV exception);
3. `--to duckdb` and `--to postgres` verify, and `--mode merge` either works or is refused for a stated reason (the key has empty values);
4. its source page lists the exceptions below that apply, and `cache check` shows its raw files with fingerprints.

Exceptions to expect:
- **Season-partitioned datasets** (Statcast, Retrosheet, MLB per season): files get `season=` folders; databases get the seasons one after another (replace wipes once, then appends); a season subset with `replace` leaves only those seasons in the table.
- **Very large datasets:** each season is held in memory once; datasets larger than memory per season need batch streaming (`write_stream`) before they can be exported.
- **Keys with empty values or non-unique keys** (some MLB endpoints): `replace` or `append` only.
- **Nested columns** (`retrosheet.box_records`): Parquet, DuckDB and PostgreSQL only.
