# baseballpy

Typed baseball data in one local lake. `baseballpy` ingests **Statcast (Baseball Savant)**, the **MLB Stats API**, **Lahman**, the **Chadwick Register** and **Retrosheet** into strict Arrow schemas, stores them as Parquet, and exposes them as DuckDB views you can query with SQL, Polars or PyArrow.

## What it guarantees

- **Nothing is left behind.** Every field, endpoint, group, level and file a provider offers is captured, either as a typed column or in an `_extras` JSON column. What cannot be ingested stays registered as `unsupported` with the evidence of what was tried.
- **Types come from data.** Schemas are generated from live responses, never guessed from column names; cells that cannot be cast go to a quarantine directory instead of being truncated.
- **Resumable and polite.** Writes are atomic (`.part` then rename), every chunk is recorded in a manifest, and all HTTP goes through one rate-limited client.
- **Decoupled.** Sources meet the rest of the code only through the `IngestAdapter` boundary; behavior comes from the dataset registry, not from hard-coded names.

## First steps

```bash
pip install baseballpy
baseballpy ingest lahman chadwick          # season-less sources
baseballpy ingest statcast --seasons 2023 --datasets pitches
baseballpy db sync
baseballpy db query "select count(*) from statcast_pitches"
baseballpy catalog status --gaps           # what the default ingest should have filled
```

Continue with the [Quickstart](QUICKSTART.md), the generated [command-line reference](CLI.md), the [architecture](ARCHITECTURE.md) and one page per [source](sources/statcast.md).

## Licence

GPL-3.0-or-later. Upstream data keeps its own terms: see [Data licenses](DATA_LICENSES.md).
