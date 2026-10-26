# Change: Production Readiness, Pydantic V2 Settings, and Comprehensive Smoke Suite

## Why
`baseballpy` has unified Statcast pitch tracking, 11 dedicated analytical leaderboards, Retrosheet's full historical corpus (events, boxscores, daily appearances, substitutions, and gamelogs), Chadwick register, MLB Stats API v1 suite, real-time live event streaming, and multi-target sinks (DuckDB, Parquet, Polars, dlt).
To guarantee enterprise production stability and researcher-friendly developer ergonomics:
1. System configuration must be fully driven by `pydantic-settings` (V2 `BaseSettings`), enabling seamless environment variable overrides (`BASEBALLPY_CACHE_DIR`, `BASEBALLPY_RATE_LIMITS`, `BASEBALLPY_MAX_CONCURRENCY`, `BASEBALLPY_LOGS_DIR`, etc.) and profile-driven setups without code modifications.
2. A comprehensive, multi-season smoke test suite (`tests/test_smoke.py`) is required to stress-test multi-season partitioning, manifest checkpointing, zero-loss idempotency, atomic downloads, and schema coercion under varied configurations.
3. The public interface must be cleanly cataloged and documented with explicit dataset-to-function guides so data engineers and sabermetricians know exactly what function to invoke for every dataset.
4. An ambitious, visionary roadmap of 15–20 high-value innovations (`docs/ROADMAP.md`) must be authored to direct subsequent development phases beyond legacy libraries (`pybaseball`, `baseballr`).

## Scope
- Migrate `src/baseballpy/core/config.py` to `pydantic-settings` (`BaseSettings`) with environment prefix `BASEBALLPY_`.
- Validate configuration overrides via `.env` files and environment variables.
- Implement exhaustive smoke tests in `tests/test_smoke.py` covering multi-season Retrosheet extraction, Statcast 5-day chunking over wide date intervals, MLB API seasonal schedules and boxscores, manifest tracking, cache verification, and atomic file guarantees.
- Author `docs/ROADMAP.md` cataloging 15+ high-impact sabermetric architectures (Lahman SQLite sync, Hawkeye 3D biomechanics, FanGraphs projections, Baseball-Reference WAR crosswalk, 3D ballpark boundary polygons, LLM Agent MCP Server, Sabermetrics feature store, async CLI progress bars).
- Document Architecture Decision Record 18 in `docs/DECISIONS.md`.
- Verify 100% strict mypy and 0 ruff errors.
