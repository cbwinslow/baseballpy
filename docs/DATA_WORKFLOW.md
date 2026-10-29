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
| Parquet files elsewhere | `ParquetSink` |
| A DuckDB file | `DuckDBSink` |
| PostgreSQL or a warehouse | `DltSink` in Python today; a single `baseballpy export` command is planned (ADR 44) |
| CSV | `pyarrow.csv.write_csv(table, "out.csv")`; there is no project command yet |

Checked on the Chadwick datasets: Parquet, DuckDB and Polars give back exactly the same rows, columns
and types.
