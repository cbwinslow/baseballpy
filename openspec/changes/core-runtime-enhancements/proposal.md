# Change Proposal: Core Runtime Enhancements

## Why
To support multi-engine dataframes (`narwhals`), high-speed JSON parsing (`msgspec`), clean user-configurable directory partitioning, hash-based cache invalidation, and detailed execution audit logging with a built-in CLI viewer.

## What Changes
1. Add dependencies: `narwhals>=1.10.0` and `msgspec>=0.18.0`.
2. Expand `PipelineConfig` and `CacheConfig` to support source-partitioned paths (`statcast/`, `mlb_api/`, `chadwick/`, `lahman/`, `retrosheet/`) and environment variable overrides (`BASEBALLPY_CACHE_DIR`).
3. Implement `baseballpy.core.audit` with `AuditLogger`, telemetry models, and execution benchmark wrapper.
4. Implement `baseballpy audit` CLI subcommands (`summary`, `tail`, `stats`) using `rich` tables.
5. Record ADRs 11 through 14 in `docs/DECISIONS.md`.
6. Enforce decoupled architecture and minimal splash damage rules in `AGENTS.md`.
