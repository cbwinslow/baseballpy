# baseballpy — Development Guidelines

## Project Overview
`baseballpy` is a fast, modular, and strongly-typed baseball data ingestion layer for Python. It extracts, normalizes, and ingests baseball data from Statcast (Baseball Savant), MLB Stats API, Lahman, Chadwick Registers, and Retrosheet into DuckDB, Polars, PyArrow, and dlt destinations (PostgreSQL, BigQuery, Snowflake).

## Essential Commands

```bash
# Package & Environment Management
uv sync --all-extras
uv add <package>

# Testing
uv run pytest
uv run pytest tests/test_protocols.py -v

# Linting & Formatting
uvx ruff check .
uvx ruff format .

# Type Checking
uvx mypy --strict src
```

## Architectural Guidelines
1. **Decoupled Architecture:** Keep Extract (`sources/`), Parse/Schema (`schemas/`), and Sink (`sinks/`) decoupled through strict Python Protocols (`typing.Protocol`).
2. **Columnar Typing Mandate:** Every dataset MUST have an explicit, strongly-typed PyArrow schema. No generic all-VARCHAR tables.
3. **OpenSpec & ADR Workflow:** All work is proposed and tracked in `openspec/changes/` and major decisions documented in `docs/DECISIONS.md`.
4. **License Boundary:** Keep `baseballpy` Apache-2.0. Interface with GPL-3.0 dependencies (like `retrosheetpy` / `chadwickpy`) via adapters or optional extras.
