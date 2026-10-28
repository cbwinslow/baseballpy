# Command-line reference

Generated from the click help of `baseballpy` by `baseballpy docs generate`; do not edit by hand.
Every command and its options are listed below, one section per command.

## `baseballpy`

```text
Usage: baseballpy [OPTIONS] COMMAND [ARGS]...

  baseballpy: Fast, modular, and strongly-typed baseball data ingestion layer.

Options:
  --version   Show the version and exit.
  --licenses  Show the license/attribution terms of the upstream data sources and exit.
  --help      Show this message and exit.

Commands:
  audit           Inspect and analyze pipeline execution logs, benchmarks, and audit telemetry.
  backfill        Run a TOML plan of ingest stages (sources, seasons, datasets) into the lake.
  catalog         Inspect and audit what the registry covers.
  db              Manage the DuckDB catalog (views over processed/ Parquet).
  docs            Generate the per-dataset column dictionaries in docs/sources/*.md.
  doctor          Diagnose data lake layout, disk usage, package versions, and orphan files.
  ingest          Execute ingestion jobs across registered adapters with planning and concurrency.
  migrate-layout  Migrate a v1 data lake (cache/<source>/...) to layout v2 (raw/ + processed/).
  quarantine      Inspect and display dead-letter quarantine files and unparseable records.
  refs            Show or update the pinned upstream commit SHAs (reproducible GitHub sources).
  statcast        Download Statcast pitch-level tracking data with chunking and rate limits.
  stream          Stream live pitch and play events for a game in real time or replay mode.
```

## `baseballpy audit`

```text
Usage: baseballpy audit [OPTIONS] COMMAND [ARGS]...

  Inspect and analyze pipeline execution logs, benchmarks, and audit telemetry.

Options:
  --help  Show this message and exit.

Commands:
  stats    Compute and display aggregate throughput, success rate, and cache hit metrics.
  summary  Display a formatted summary table of recent operations.
  tail     Print detailed telemetry records for the most recent operations.
```

## `baseballpy audit stats`

```text
Usage: baseballpy audit stats [OPTIONS]

  Compute and display aggregate throughput, success rate, and cache hit metrics.

Options:
  --help  Show this message and exit.
```

## `baseballpy audit summary`

```text
Usage: baseballpy audit summary [OPTIONS]

  Display a formatted summary table of recent operations.

Options:
  -n, --limit INTEGER  Number of recent events to display
  --source TEXT        Only events of this source.
  --status TEXT        Only events with this status (e.g. FAILURE).
  --since TEXT         Only events at or after this ISO date/time.
  --help               Show this message and exit.
```

## `baseballpy audit tail`

```text
Usage: baseballpy audit tail [OPTIONS]

  Print detailed telemetry records for the most recent operations.

Options:
  -n, --limit INTEGER  Number of recent events to inspect in detail
  --source TEXT        Only events of this source.
  --status TEXT        Only events with this status (e.g. FAILURE).
  --since TEXT         Only events at or after this ISO date/time.
  --help               Show this message and exit.
```

## `baseballpy backfill`

```text
Usage: baseballpy backfill [OPTIONS] PLAN_FILE

  Run a TOML plan of ingest stages (sources, seasons, datasets) into the lake.

  Re-running the same plan resumes: the adapters skip every chunk that is already complete.

Options:
  --max-gb FLOAT RANGE            Stop when the lake has grown by this many GB (measured as the drop
                                  in free space).  [x>0]
  --min-free-gb FLOAT RANGE       Refuse to start, and stop, when less than this much space would
                                  stay free.  [default: 5.0; x>=0]
  --refresh                       Bypass local cache and force fresh download.
  --dry-run                       Plan the jobs and the disk check; run nothing.
  -c, --concurrency INTEGER RANGE
                                  Max concurrent worker threads (minimum 1).  [x>=1]
  --json                          Print one JSON object per stage.
  --help                          Show this message and exit.
```

## `baseballpy catalog`

```text
Usage: baseballpy catalog [OPTIONS] COMMAND [ARGS]...

  Inspect and audit what the registry covers.

Options:
  --help  Show this message and exit.

Commands:
  audit   Compare provider-listed items with the registry (exit 1 on MISSING/REVIVED/ERROR).
  list    List registered datasets with schema, partition, and primary key metadata.
  show    Show detailed metadata, schema columns, and lake status for a registered dataset.
  status  Inspect local lake processed Parquet datasets and reporting status.
```

## `baseballpy catalog audit`

```text
Usage: baseballpy catalog audit [OPTIONS]

  Compare provider-listed items with the registry (exit 1 on MISSING/REVIVED/ERROR).

Options:
  --source [mlb_api|statcast]  Limit the audit to one source (repeatable). Default: all audited
                               sources.
  --json                       Print the findings as JSON.
  --help                       Show this message and exit.
```

## `baseballpy catalog list`

```text
Usage: baseballpy catalog list [OPTIONS]

  List registered datasets with schema, partition, and primary key metadata.

Options:
  --source TEXT  Filter by source (repeatable).
  --json         Output datasets as newline-delimited JSON objects.
  --help         Show this message and exit.
```

## `baseballpy catalog show`

```text
Usage: baseballpy catalog show [OPTIONS] SPEC

  Show detailed metadata, schema columns, and lake status for a registered dataset.

Options:
  --json  Output dataset details as a single JSON object.
  --help  Show this message and exit.
```

## `baseballpy catalog status`

```text
Usage: baseballpy catalog status [OPTIONS]

  Inspect local lake processed Parquet datasets and reporting status.

  The Ingest column says why a dataset is not in the lake: opt_in and on_demand datasets need an
  option or an input, api_only ones are filled by the Python API, and a default dataset can be empty
  for a season the provider does not publish (its note says which).

Options:
  --source TEXT  Filter by source (repeatable).
  --missing      Show only MISSING datasets.
  --gaps         Show only MISSING datasets that the default ingest selection should have filled.
  --json         Print status as JSON lines (one object per dataset).
  --help         Show this message and exit.
```

## `baseballpy db`

```text
Usage: baseballpy db [OPTIONS] COMMAND [ARGS]...

  Manage the DuckDB catalog (views over processed/ Parquet).

Options:
  --help  Show this message and exit.

Commands:
  query  Run one SQL query read-only against the DuckDB database and print the results.
  shell  Open an interactive DuckDB CLI session connected to the catalog database.
  sync   Create or refresh a DuckDB view for every dataset that has processed data.
  views  List registered views in the DuckDB database along with their row counts.
```

## `baseballpy db query`

```text
Usage: baseballpy db query [OPTIONS] SQL

  Run one SQL query read-only against the DuckDB database and print the results.

Options:
  -l, --limit INTEGER RANGE  Maximum rows to display (0 = unlimited, default 100).  [x>=0]
  --json                     Output rows as newline-delimited JSON objects.
  --csv                      Output rows as CSV.
  --help                     Show this message and exit.
```

## `baseballpy db shell`

```text
Usage: baseballpy db shell [OPTIONS]

  Open an interactive DuckDB CLI session connected to the catalog database.

Options:
  --help  Show this message and exit.
```

## `baseballpy db sync`

```text
Usage: baseballpy db sync [OPTIONS]

  Create or refresh a DuckDB view for every dataset that has processed data.

Options:
  --help  Show this message and exit.
```

## `baseballpy db views`

```text
Usage: baseballpy db views [OPTIONS]

  List registered views in the DuckDB database along with their row counts.

Options:
  --json  Output views as newline-delimited JSON objects.
  --help  Show this message and exit.
```

## `baseballpy docs`

```text
Usage: baseballpy docs [OPTIONS] COMMAND [ARGS]...

  Generate the per-dataset column dictionaries in docs/sources/*.md.

Options:
  --help  Show this message and exit.

Commands:
  coverage  Show how many columns of each source have a cited description.
  generate  Render a column dictionary for every registered dataset between GENERATED markers.
```

## `baseballpy docs coverage`

```text
Usage: baseballpy docs coverage [OPTIONS]

  Show how many columns of each source have a cited description.

Options:
  --docs-dir DIRECTORY
  --write-baseline      Raise docs/columns/coverage_baseline.json to the current counts (never
                        lowers it).
  --help                Show this message and exit.
```

## `baseballpy docs generate`

```text
Usage: baseballpy docs generate [OPTIONS]

  Render a column dictionary for every registered dataset between GENERATED markers.

Options:
  --docs-dir DIRECTORY
  --check               Fail (exit 1) if any page is stale instead of writing.
  --help                Show this message and exit.
```

## `baseballpy doctor`

```text
Usage: baseballpy doctor [OPTIONS]

  Diagnose data lake layout, disk usage, package versions, and orphan files.

Options:
  --clean  Delete orphan .part files under raw and processed tiers.
  --json   Print system and lake diagnosis as a JSON object.
  --help   Show this message and exit.
```

## `baseballpy ingest`

```text
Usage: baseballpy ingest [OPTIONS] [SOURCES]...

  Execute ingestion jobs across registered adapters with planning and concurrency.

Options:
  -s, --seasons TEXT              Season expression (e.g. 2020, 2015-2024, or all).
  -d, --datasets TEXT             Dataset(s) to ingest: name (one source) or source:name
                                  (repeatable, comma-separated).
  --refresh                       Bypass local cache and force fresh download.
  --dry-run                       Plan jobs and print them without executing.
  -c, --concurrency INTEGER RANGE
                                  Max concurrent worker threads (minimum 1).  [x>=1]
  --limit INTEGER RANGE           Bound the per-game, per-player or per-game-feed fan-out of opt-in
                                  datasets (default: all).  [x>=1]
  --stop-on-error                 Halt execution immediately when a job raises an error.
  --json                          Output results as newline-delimited JSON objects.
  --help                          Show this message and exit.
```

## `baseballpy migrate-layout`

```text
Usage: baseballpy migrate-layout [OPTIONS]

  Migrate a v1 data lake (cache/<source>/...) to layout v2 (raw/ + processed/).

Options:
  --dry-run     Print the plan without touching any file.
  --delete-old  Delete migrated v1 files after verification (unknown files are never touched).
  --help        Show this message and exit.
```

## `baseballpy quarantine`

```text
Usage: baseballpy quarantine [OPTIONS] COMMAND [ARGS]...

  Inspect and display dead-letter quarantine files and unparseable records.

Options:
  --help  Show this message and exit.

Commands:
  list  List dead-letter quarantine files and their error summaries.
  show  Display records from a quarantined dead-letter JSONL file.
```

## `baseballpy quarantine list`

```text
Usage: baseballpy quarantine list [OPTIONS]

  List dead-letter quarantine files and their error summaries.

Options:
  --source TEXT   Filter by data source.
  --dataset TEXT  Filter by dataset name.
  --since TEXT    Filter by date (YYYY-MM-DD) on or after.
  --json          Output results as newline-delimited JSON.
  --help          Show this message and exit.
```

## `baseballpy quarantine show`

```text
Usage: baseballpy quarantine show [OPTIONS] PATH

  Display records from a quarantined dead-letter JSONL file.

Options:
  -n, --limit INTEGER RANGE  Maximum records to display.  [default: 5; x>=1]
  --json                     Output raw full JSON lines.
  --help                     Show this message and exit.
```

## `baseballpy refs`

```text
Usage: baseballpy refs [OPTIONS] COMMAND [ARGS]...

  Show or update the pinned upstream commit SHAs (reproducible GitHub sources).

Options:
  --help  Show this message and exit.

Commands:
  show    List the effective pinned ref of every GitHub-hosted source.
  update  Resolve the latest commit SHA of each source (set GITHUB_TOKEN to avoid rate limits).
```

## `baseballpy refs show`

```text
Usage: baseballpy refs show [OPTIONS]

  List the effective pinned ref of every GitHub-hosted source.

Options:
  --help  Show this message and exit.
```

## `baseballpy refs update`

```text
Usage: baseballpy refs update [OPTIONS]

  Resolve the latest commit SHA of each source (set GITHUB_TOKEN to avoid rate limits).

Options:
  --dry-run  Resolve and print the latest SHAs without writing.
  --help     Show this message and exit.
```

## `baseballpy statcast`

```text
Usage: baseballpy statcast [OPTIONS]

  Download Statcast pitch-level tracking data with chunking and rate limits.

Options:
  -s, --start TEXT               Start date (YYYY-MM-DD)  [required]
  -e, --end TEXT                 End date (YYYY-MM-DD)  [required]
  -d, --destination TEXT         Target destination path
  -f, --format [duckdb|parquet]  Output format
  -t, --table TEXT               DuckDB table name
  --refresh                      Bypass local cache and force fresh download
  --help                         Show this message and exit.
```

## `baseballpy stream`

```text
Usage: baseballpy stream [OPTIONS] GAME_PK

  Stream live pitch and play events for a game in real time or replay mode.

Options:
  --replay               Ignore stored watermark and emit every event again.
  --jsonl FILE           Append events as JSON objects to this file.
  --duckdb FILE          Upsert events into a DuckDB file destination.
  --table TEXT           Target table name when saving to DuckDB.  [default: live_events]
  --poll-interval FLOAT  Polling interval override in seconds.
  --max-events INTEGER   Stop streaming after processing N events.
  --json                 Print events as JSON lines to stdout.
  --help                 Show this message and exit.
```
