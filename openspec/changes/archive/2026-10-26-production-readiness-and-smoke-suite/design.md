# Design: Production Readiness, Pydantic V2 Settings, and Comprehensive Smoke Suite

## 1. Pydantic Settings Architecture

`src/baseballpy/core/config.py` is upgraded from standard `pydantic.BaseModel` to `pydantic_settings.BaseSettings` with nested environment variable parsing.

### Settings Model Hierarchy
```text
PipelineConfig (BaseSettings) [env_prefix="BASEBALLPY_"]
 ├── cache: CacheConfig (BaseSettings) [env_prefix="BASEBALLPY_CACHE_"]
 ├── audit: AuditConfig (BaseSettings) [env_prefix="BASEBALLPY_AUDIT_"]
 ├── rate_limit: RateLimitConfig (BaseSettings) [env_prefix="BASEBALLPY_RATE_"]
 ├── streaming: StreamingConfig (BaseSettings) [env_prefix="BASEBALLPY_STREAM_"]
 └── quarantine: QuarantineConfig (BaseSettings) [env_prefix="BASEBALLPY_QUARANTINE_"]
```

### Environment Variable Bindings
- `BASEBALLPY_HOME`: Overrides base directory (default: `~/.baseballpy`).
- `BASEBALLPY_CACHE_BASE_DIR` or `BASEBALLPY_CACHE_DIR`: Explicit cache root.
- `BASEBALLPY_CACHE_ENABLED`: Boolean toggle (default: `true`).
- `BASEBALLPY_CACHE_TTL_SECONDS`: Integer seconds for TTL (default: 30 days).
- `BASEBALLPY_RATE_MAX_CONCURRENCY`: Default concurrency semaphore cap (default: 4).
- `BASEBALLPY_RATE_SAVANT`: Savant token rate (default: 2.5 rps).
- `BASEBALLPY_RATE_STATSAPI`: MLB API token rate (default: 8.0 rps).
- `BASEBALLPY_RATE_GITHUB`: GitHub CDN token rate (default: 15.0 rps).
- `BASEBALLPY_AUDIT_ENABLED`: Boolean telemetry toggle (default: `true`).
- `BASEBALLPY_AUDIT_LOG_DIR`: Custom telemetry directory.

## 2. Comprehensive Multi-Season Smoke Test Suite

`tests/test_smoke.py` validates the following failure modes and production behaviors using deterministic `respx` mocked fixtures:
1. **Multi-Season Retrosheet Download & Chadwick Parsing:**
   - Test sequential downloads and parsing for consecutive seasons (e.g., 2022, 2023, 2024).
   - Ensure `raw/` and `processed/` folders are created and isolated without cross-season collisions.
   - Test `manifest.json` generation and checkpoint verification.
   - Verify second run completes with zero HTTP calls (idempotent cache hit).
2. **Multi-Chunk Statcast Search:**
   - Execute pitch search across a 15-day range spanning 3 distinct 5-day chunks.
   - Assert all 3 chunks download to `.part`, validate, and rename to final parquet cache.
   - Verify all chunks concatenate correctly into a single 94-column Arrow Table.
   - Verify subsequent run loads entirely from cache.
3. **MLB Stats API Multi-Game Flow:**
   - Fetch schedule with multiple games, extract boxscores, verify DuckDB sink ingestion.
4. **Failure Recovery & Atomic Guarantee:**
   - Simulate an interrupted network transfer (exception mid-stream).
   - Assert `.part` file is not promoted to final cache path.
   - Assert manifest marks partition as failed or uncommitted.
   - Assert retry successfully cleans up `.part` and commits valid download.

## 3. High-Value Sabermetric Innovations Roadmap

Author `docs/ROADMAP.md` covering 15 strategic capability pillars:
1. Lahman Complete Baseball Database Async SQLite & Parquet Ingestion.
2. Hawkeye 3D Biomechanics & Skeletal Pose Ingestion (18-joint tracking).
3. FanGraphs Sabermetric Leaderboards & Projections (ZiPS, Steamer, ATC).
4. Baseball-Reference Historical WAR Crosswalk & Ingestion.
5. 3D Ballpark Spatial Polygons & Hit Trajectory Overlays (GeoParquet).
6. Local Sabermetrics Feature Store (Rolling xwOBA, Stuff+, Pitch Calling Entropy).
7. Baseballpy Agent MCP Server (Model Context Protocol for AI Agents).
8. Live Gameday Microsecond Win Probability & Run Expectancy Ingestion.
9. Pitch Clock & Rule Invariant Transition Matrices (2020 7-inning, 2023 clock).
10. Japanese NPB & Korean KBO Foreign League Data Ingestion.
11. Minor League (MiLB) Triple-A / Double-A Statcast Tracking.
12. Amateur Draft Prospect Trackman & College Cape Cod Ingestion.
13. Historical Weather & Elevation Environmental Adjustments (Open-Meteo).
14. High-Performance Arrow Native C++ Extensions / Rust Accelerators.
15. Rich CLI Interactive Dashboard & TUI Monitor for Live Games.
