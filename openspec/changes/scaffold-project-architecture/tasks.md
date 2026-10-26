# Tasks: Scaffold Project Architecture

- [x] Create root configuration: `AGENTS.md`, `.gitignore`, `pyproject.toml`
- [x] Configure OpenSpec directory: `config.yaml`, `project.md`, `specs/`
- [x] Author Architecture Decision Records in `docs/DECISIONS.md` (ADR 1 to ADR 6)
- [ ] Create package directory structure in `src/baseballpy/`
  - [ ] `src/baseballpy/__init__.py`
  - [ ] `src/baseballpy/core/protocols.py`
  - [ ] `src/baseballpy/core/config.py`
  - [ ] `src/baseballpy/sources/` (statcast, mlb_api, lahman, chadwick, retrosheet)
  - [ ] `src/baseballpy/sinks/` (duckdb, parquet, polars, dlt)
  - [ ] `src/baseballpy/cli.py`
- [ ] Create initial test suite in `tests/`
  - [ ] `tests/test_protocols.py`
- [ ] Verify test suite and static analysis via `uv` (`pytest`, `ruff`, `mypy`)
