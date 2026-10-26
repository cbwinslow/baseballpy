# Change: Comprehensive Enums, Structured Telemetry Audit, and Top-Level API Polish

## Why
Following the implementation of the sharded Chadwick register and Lahman database (1871–2025), a comprehensive codebase audit is needed to:
1. Standardize type-safe Enums across all data sources (`StatcastLeaderboard`, `PitchType`, `PlayerType`, `RetrosheetReferenceTable`, `GameLogType`, `EventCode`, `GameType`, `SportId`, `GameState`, `WriteMode`, `CompressionCodec`), giving users and agents robust autocomplete and compile-time correctness while maintaining 100% backward compatibility via `StrEnum` / `IntEnum`.
2. Ensure consistent telemetry and audit logging across all sources, specifically wrapping all Lahman table operations and archive imports in `default_audit_logger.track(...)`.
3. Eliminate any file clobbering or non-atomic file writes, verifying two-phase atomic write scopes (`atomic_write`, `atomic_write_parquet`) guard every write operation.
4. Export all core functions, sources, and enums directly at the root `baseballpy` package (`baseballpy/__init__.py`), making the developer experience seamless.
5. Record ADR 20 in `docs/DECISIONS.md` and update `docs/QUICKSTART.md` and living specs.

## Scope
- Author Enums across `statcast`, `retrosheet`, `mlb_api`, `lahman`, and `sinks`.
- Update `LahmanSource` to track all operations in `default_audit_logger`.
- Expose all core functions and classes in `src/baseballpy/__init__.py`.
- Add unit tests verifying Enums, top-level imports, and telemetry.
- Verify 100% strict mypy and 0 ruff errors.
