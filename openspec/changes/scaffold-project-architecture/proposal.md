# Change Proposal: Scaffold Project Architecture

## Why
Baseball data ingestion in Python has historically suffered from fragmented, unmaintained, or poorly typed packages (e.g. `pybaseball`, `mlbstatsapi`, legacy scripts). Analysts and engineers frequently encounter:
1. Untyped string data (all-VARCHAR) leading to type confusion and memory bloat.
2. Inability to sink directly to modern analytical engines (DuckDB, Polars, PostgreSQL via dlt) without inefficient pandas roundtrips.
3. Lack of rate-limiting, connection pooling, and retry logic, leading to IP bans or dropped requests on high-volume endpoints (Baseball Savant, MLB Stats API).
4. Lack of streaming or change-detection for live in-game data ingestion.

This proposal establishes the foundational project architecture for `baseballpy`, including the OpenSpec spec framework, ADR log, protocol-based interfaces, `uv` configuration, and initial package structure.

## What Changes
1. Initialize repository with `AGENTS.md`, `CLAUDE.md`, and OpenSpec constitution (`openspec/config.yaml`, `openspec/project.md`).
2. Establish `docs/DECISIONS.md` with ADR 1 through ADR 6.
3. Configure `pyproject.toml` with modern Python 3.11+ tooling (`uv`, `ruff`, `mypy --strict`, `pytest`, `duckdb`, `polars`, `pyarrow`, `dlt`, `httpx`).
4. Define abstract `typing.Protocol` interfaces for `Extractor`, `Normalizer`, and `Sink` in `src/baseballpy/core/protocols.py`.
5. Provide top-level module scaffolding in `src/baseballpy/`.
