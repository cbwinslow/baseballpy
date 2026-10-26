# baseballpy

Fast, modular, and strongly-typed baseball data ingestion layer for Python.

Unified extraction, normalization, and ingestion for **Statcast (Baseball Savant)**, **MLB Stats API**, **Lahman Database**, **Chadwick Register**, and **Retrosheet** into **DuckDB**, **Polars**, **PyArrow**, and **dlt** (PostgreSQL, Snowflake, BigQuery, MotherDuck).

---

## Key Features

- **Strictly Typed Columnar Storage:** Never dumps all-VARCHAR untyped text. Normalizes all 90+ Statcast attributes, MLB Gameday feeds, and Lahman tables directly into physical PyArrow types (`date32`, `timestamp[us]`, `float32`, `int16`, `dictionary`).
- **Decoupled Architecture:** Network extractors, schema normalizers, and storage sinks are separated via strict Python `typing.Protocol` interfaces.
- **Adaptive Sinks:** Stream into embedded **DuckDB**, write partitioned **Parquet** datasets, yield zero-copy **Polars** DataFrames, or use **`dlt`** to sync directly into cloud and relational databases.
- **Real-Time & Historical Ingestion:** Supports full multi-season bulk downloads with automatic chunking and rate-limiting backoff, as well as live Gameday feed polling with state diffing.
- **OpenSpec & ADR-Driven:** Transparent specifications, documented design decisions, and strict regression test suites.

---

## Installation

```bash
# Core package (DuckDB, Polars, PyArrow, dlt, httpx)
pip install baseballpy
# or using uv
uv add baseballpy

# With optional Retrosheet and Chadwick support
uv add "baseballpy[retrosheet]"

# Full installation
uv add "baseballpy[all]"
```

---

## Architecture Decisions

All architectural choices and data source nuances are documented in [docs/DECISIONS.md](docs/DECISIONS.md).

## Specifications

Specifications and active changes are tracked using OpenSpec in [openspec/](openspec/).
