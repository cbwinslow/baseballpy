# baseballpy

Fast, modular, and strongly-typed baseball data ingestion layer for Python.

Unified extraction, normalization, and ingestion for **Statcast (Baseball Savant)**, **MLB Stats API**, **Lahman Database**, **Chadwick Register**, and **Retrosheet** into **DuckDB**, **Polars**, **PyArrow**, and **dlt** (PostgreSQL, Snowflake, BigQuery, MotherDuck).

---

## Key Features

- **Strictly Typed Columnar Storage:** Never dumps all-VARCHAR untyped text. Normalizes every Statcast pitch column (119 today, plus `_extras` for new ones), MLB Gameday feeds, Retrosheet event files, and Lahman tables directly into physical PyArrow types (`date32`, `timestamp[us]`, `float32`, `int16`, `dictionary`).
- **Decoupled Architecture:** Network extractors, schema normalizers, and storage sinks are separated via strict Python `typing.Protocol` interfaces (`ExtractorProtocol`, `NormalizerProtocol`, `SinkProtocol`, `StreamExtractorProtocol`).
- **Adaptive Multi-Target Sinks:** Stream into embedded **DuckDB**, write partitioned **Parquet** datasets, yield zero-copy **Polars** DataFrames/LazyFrames, or use **`dlt`** to sync directly into cloud data warehouses (PostgreSQL, Snowflake, BigQuery, MotherDuck).
- **Two-Phase Atomic Ingestion & Manifest Checkpointing:** Downloads write to `.part` files and rename atomically via `os.replace()` upon validation. Pause and resume partitioned downloads seamlessly without data duplication or silent truncation.
- **Real-Time Live Streaming & State Diffing:** Low-latency async generator for active MLB Gameday feeds with monotonic sequence watermarks `(atBatIndex, eventIndex)` and HTTP `ETag` conditional polling (`If-None-Match`).
- **Full Data Preservation Mandate:** Every upstream field, metric, and metadata column is preserved with zero arbitrary truncation.
- **Structured Audit Logging & CLI Reviewer:** Automatically logs all extractions to `~/.baseballpy/logs/audit.jsonl` with built-in CLI inspection tools (`baseballpy audit summary`, `tail`, `stats`).
- **OpenSpec & ADR-Driven:** Transparent specifications, documented design decisions, and strict regression test suites.

---

## Installation

```bash
# Core package (DuckDB, Polars, PyArrow, dlt, httpx, msgspec, aiolimiter)
uv add baseballpy
# or with pip
pip install baseballpy

# With optional Retrosheet and Chadwick support
uv add "baseballpy[retrosheet]"  # alias; chadwickpy is installed by default

# Full installation
uv add "baseballpy[all]"
```

---

## Quick Start

### 1. Chadwick Player Register Lookup
Resolve player IDs across MLBAM, Retrosheet, Baseball-Reference, and FanGraphs with O(1) in-memory lookups:

```python
import baseballpy as bb

# Resolve by name or any identifier
player = bb.resolve_player(name="Shohei Ohtani")
print(player["key_mlbam"], player["key_retro"], player["key_bbref"])

# Resolve by MLBAM ID
judge = bb.resolve_player(mlbam=592450)
print(judge["name_first"], judge["name_last"], judge["key_fangraphs"])
```

### 2. Statcast Pitches & Analytical Leaderboards
Fetch granular pitch data or any of the 34 Baseball Savant leaderboard variants (see `docs/sources/statcast.md`):

```python
import baseballpy as bb
from baseballpy.sources import statcast

# 1. Pitch-level tracking (auto 5-day chunking with rate limiting)
pitches = bb.statcast("2024-06-01", "2024-06-05")

# 2. 2024+ Bat Tracking Leaderboard (bat speed, swing length, squared up %)
bat_speed_df = statcast.bat_tracking(year=2024, min_swings="q")

# 3. Expected Statistics (xBA, xSLG, xwOBA)
xstats_df = statcast.expected_statistics(year=2024)

# 4. Outs Above Average (OAA) Defensive Leaderboard
oaa_df = statcast.outs_above_average(year=2024)

# Convert zero-copy to Polars or DuckDB
polars_df = bb.to_polars(bat_speed_df)
bb.to_duckdb(pitches, destination="baseball.duckdb", table_name="pitches_2024")
```

### 3. Retrosheet: Play-by-Play, Box Scores, Daily Splits & Reference
Extract and parse historical Retrosheet seasons directly in memory via `chadwickpy`:

```python
from baseballpy.sources import retrosheet

# 1. Play-by-play events (97 canonical fields)
events = retrosheet.events(2023)

# 2. Game-by-game box scores (batting and pitching)
batting_box, pitching_box = retrosheet.boxscores(2023)

# 3. Daily player lines (154 fields for batting, pitching, and fielding)
daily_splits = retrosheet.daily_splits(2023)

# 4. In-game player substitutions
subs = retrosheet.substitutions(2023)

# 5. Historical game logs (161 fields: 1871-present)
gamelogs = retrosheet.game_logs(2023)

# 6. Reference tables (ballparks, ejections, coaches, relatives, biofile, teams)
ballparks = retrosheet.reference("ballparks")
ejections = retrosheet.reference("ejections")
```

### 4. MLB Stats API & Real-Time Gameday Streaming
Query official schedules, box scores, standings, and stream live games:

```python
import asyncio
from baseballpy.sources import mlb

# 1. Official game schedule
schedule = mlb.get_schedule(season=2024)

# 2. Game box score
batting, pitching = mlb.get_boxscore(game_pk=745789)

# 3. League standings
standings = mlb.get_standings(season=2024)


# 4. Real-time live game streaming with state diffing
async def watch_game(game_pk: int):
    async for event in mlb.stream_game(game_pk, poll_interval=1.5):
        if event["is_pitch"]:
            print(
                f"Pitch: {event['pitch_type']} at {event['start_speed']} mph - {event['description']}"
            )
        elif event["event"]:
            print(f"Play Result: {event['event']} - {event['description']}")


# asyncio.run(watch_game(745789))
```

### 5. Multi-Target Storage Sinks
Stream seamlessly into DuckDB, Parquet, Polars, or `dlt` (PostgreSQL / Snowflake / BigQuery):

```python
import dlt
from baseballpy.sinks import DltSink, DuckDBSink, ParquetSink, PolarsSink

# Sink into DuckDB
duck_sink = DuckDBSink()
duck_sink.write(table, destination="analytics.duckdb", table_name="pitches")

# Sink into Polars DataFrame or LazyFrame
polars_sink = PolarsSink()
df = polars_sink.to_dataframe(table)
lf = polars_sink.to_lazyframe(table)

# Stream into PostgreSQL or Snowflake via dlt
dlt_sink = DltSink(
    pipeline=dlt.pipeline(
        pipeline_name="mlb_warehouse",
        destination="postgres",
        dataset_name="raw_mlb",
    )
)
dlt_sink.write(table, destination="statcast_pitches")
```

---

## CLI Utilities

One command surface runs the whole library. Every command and option is listed in the generated
[`docs/CLI.md`](docs/CLI.md).

```bash
# What does the registry cover, and what is in the lake?
baseballpy catalog list
baseballpy catalog show statcast.pitches
baseballpy catalog status --missing
baseballpy catalog status --gaps    # MISSING datasets the default ingest should have filled

# Plan, then run, ingestion for any mix of sources (re-runs skip what is complete)
baseballpy ingest all --seasons 2023 --dry-run
baseballpy ingest statcast mlb_api --seasons 2022-2023 --concurrency 2
baseballpy ingest lahman chadwick                  # season-less sources
baseballpy ingest retrosheet --seasons 1964 --datasets gamelogs

# Query what you ingested
baseballpy db sync
baseballpy db views
baseballpy db query "SELECT count(*) FROM statcast_pitches"

# Live games, dead letters and housekeeping
baseballpy stream 745789 --duckdb live.duckdb      # --replay re-emits a finished game
baseballpy quarantine list
baseballpy audit summary --status FAILURE --since 2026-10-01
baseballpy doctor
```

A dotenv file is read only when `BASEBALLPY_ENV_FILE` points at one; nothing is picked up implicitly
from the working directory.

---

## Data Lake Layout

Everything lives under `$BASEBALLPY_HOME` (default `~/.baseballpy`), layout version 2 (see
[docs/examples/layout.txt](docs/examples/layout.txt) for a real listing):

```text
$BASEBALLPY_HOME
├── raw/<source>/<dataset>/[season=YYYY/]<upstream files>          immutable upstream bytes (+ manifest.json)
├── processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet  typed Parquet, one dataset per directory
├── quarantine/<source>/<YYYY-MM-DD>/<dataset>-<id>.jsonl          rows that failed coercion (dead letters)
├── cache/http/                                                    HTTP bookkeeping only; always safe to delete
├── databases/baseball.duckdb                                      views over processed/ (no data copies)
├── logs/audit.jsonl
└── VERSION                                                        layout version (2)
```

- DuckDB views (`baseballpy db sync`) read only `processed/`; each registered dataset gets one view
  (`statcast_pitches`, `retrosheet_events`, `retrosheet_events_postseason`, `lahman_batting`,
  `chadwick_register`, `mlb_schedule`, ...), plus `v_player_crosswalk` and `v_season_catalog`.
- GitHub-hosted sources (Retrosheet, Chadwick Register, Lahman) are fetched at commit SHAs pinned in
  `src/baseballpy/core/sources_lock.json`; `baseballpy refs show` lists them and
  `baseballpy refs update` moves them forward. Override per source with
  `BASEBALLPY_RETROSHEET_REF`, `BASEBALLPY_CHADWICK_REF`, `BASEBALLPY_LAHMAN_REF`.
- Upgrading from the old `cache/<source>/` layout: `baseballpy migrate-layout --dry-run`, review, then
  `baseballpy migrate-layout` (copies and verifies; add `--delete-old` to remove migrated v1 files).

To relocate the lake: `export BASEBALLPY_HOME=/path/to/lake` (individual tiers can be moved with
`BASEBALLPY_RAW_ROOT_OVERRIDE`, `BASEBALLPY_PROCESSED_ROOT_OVERRIDE`, ...).

---

## Architecture & Specifications

- **Architecture Decision Records (ADRs):** Documented in [docs/DECISIONS.md](docs/DECISIONS.md).
- **Source Endpoint Catalogs:** Exhaustive column-by-column schemas in [docs/sources/](docs/sources/).
- **OpenSpec Living Specs:** Managed under [openspec/specs/](openspec/).
- **Agent Operating Contract:** Mandatory design invariants in [AGENTS.md](AGENTS.md).

---

## Citation & License

This project is licensed under **GPL-3.0-or-later**. See [LICENSE](LICENSE) for details.

`baseballpy` ships no data. Each upstream source (MLB/Statcast, Retrosheet, Lahman, Chadwick Register) has its own terms and attribution requirements: see [docs/DATA_LICENSES.md](docs/DATA_LICENSES.md) or run `baseballpy --licenses`.

`baseballpy` ships no data. Each upstream source (MLB/Statcast, Retrosheet, Lahman, Chadwick Register) has its own terms and attribution requirements: see [docs/DATA_LICENSES.md](docs/DATA_LICENSES.md) or run `baseballpy --licenses`.

If you use `baseballpy` in academic or sabermetric research, please cite using [CITATION.cff](CITATION.cff).
