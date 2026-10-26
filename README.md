# baseballpy

Fast, modular, and strongly-typed baseball data ingestion layer for Python.

Unified extraction, normalization, and ingestion for **Statcast (Baseball Savant)**, **MLB Stats API**, **Lahman Database**, **Chadwick Register**, and **Retrosheet** into **DuckDB**, **Polars**, **PyArrow**, and **dlt** (PostgreSQL, Snowflake, BigQuery, MotherDuck).

---

## Key Features

- **Strictly Typed Columnar Storage:** Never dumps all-VARCHAR untyped text. Normalizes all 94+ Statcast attributes, MLB Gameday feeds, Retrosheet event files, and Lahman tables directly into physical PyArrow types (`date32`, `timestamp[us]`, `float32`, `int16`, `dictionary`).
- **Decoupled Architecture:** Network extractors, schema normalizers, and storage sinks are separated via strict Python `typing.Protocol` interfaces (`ExtractorProtocol`, `NormalizerProtocol`, `SinkProtocol`, `StreamExtractorProtocol`).
- **Adaptive Sinks:** Stream into embedded **DuckDB**, write partitioned **Parquet** datasets, yield zero-copy **Polars** DataFrames, or use **`dlt`** to sync directly into cloud and relational databases.
- **Two-Phase Atomic Ingestion & Manifest Checkpointing:** Downloads write to `.part` files and rename atomically via `os.replace()` upon validation. Pause and resume partitioned downloads seamlessly without data duplication or silent truncation.
- **Real-Time & Historical Ingestion:** Supports full multi-season bulk downloads with automatic 5-day chunking, token bucket rate limiting (`aiolimiter`), and exponential jitter backoff (`tenacity`).
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
uv add "baseballpy[retrosheet]"

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

### 2. Statcast Pitch-by-Pitch Ingestion
Fetch and normalize Statcast pitches into PyArrow tables or DuckDB:

```python
from baseballpy.sources.statcast import StatcastExtractor, StatcastNormalizer
from baseballpy.sinks import DuckDBSink

extractor = StatcastExtractor()
normalizer = StatcastNormalizer()

# Fetch pitch data (auto-chunked into safe 5-day windows with token bucket rate-limiting)
raw_csv_chunks = extractor.extract_range("2024-06-01", "2024-06-05")

# Parse into strongly typed PyArrow table (94 columns including bat tracking)
table = normalizer.normalize(raw_csv_chunks)

# Sink directly into DuckDB
sink = DuckDBSink(db_path="baseball.duckdb")
sink.write(table, destination="statcast_pitches")
```

### 3. Retrosheet Historical Play-by-Play
Extract and parse historical Retrosheet seasons directly in memory with two-tier raw/processed storage:

```python
from baseballpy.sources.retrosheet import RetrosheetExtractor, RetrosheetNormalizer

extractor = RetrosheetExtractor()
normalizer = RetrosheetNormalizer()

# Download raw season archive (.EVN, .EVA files) atomically with checksum validation
raw_dir = extractor.extract_season(2023)

# Parse event rows (97 fields) and game logs (161 fields) via chadwickpy
events_table = normalizer.normalize_events(2023, raw_dir=raw_dir)
gamelogs_table = normalizer.normalize_gamelogs(2023, raw_dir=raw_dir)
```

---

## CLI Utilities

`baseballpy` provides rich CLI inspection commands:

```bash
# Inspect ingestion execution audits and telemetry
baseballpy audit summary
baseballpy audit tail -n 20
baseballpy audit stats

# Download Statcast pitch batches directly from terminal
baseballpy statcast --start 2024-05-01 --end 2024-05-05 --output pitches.parquet
```

---

## Cache Configuration

By default, data is cached under `~/.baseballpy/cache/` partitioned cleanly by source:
- `~/.baseballpy/cache/statcast/`
- `~/.baseballpy/cache/chadwick/`
- `~/.baseballpy/cache/retrosheet/`
- `~/.baseballpy/cache/mlb_api/`
- `~/.baseballpy/cache/lahman/`

To relocate the cache root to a custom mount or directory:
```bash
export BASEBALLPY_CACHE_DIR=/path/to/custom/baseballpy_cache
```

---

## Architecture & Specifications

- **Architecture Decision Records (ADRs):** Documented in [docs/DECISIONS.md](docs/DECISIONS.md).
- **Source Endpoint Catalogs:** Exhaustive column-by-column schemas in [docs/sources/](docs/sources/).
- **OpenSpec Living Specs:** Managed under [openspec/specs/](openspec/).
- **Agent Operating Contract:** Mandatory design invariants in [AGENTS.md](AGENTS.md).

---

## Citation & License

This project is licensed under **GPL-3.0-or-later**. See [LICENSE](LICENSE) for details.

If you use `baseballpy` in academic or sabermetric research, please cite using [CITATION.cff](CITATION.cff).
