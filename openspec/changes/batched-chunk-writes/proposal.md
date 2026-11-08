# Proposal: batched-chunk-writes

> **Superseded (2026-11-08) by `openspec/changes/response-log-segments/` (ADR 95, ADR 96).** Many games per Parquet
> file, with an atomic commit and a clean resume, are that change's segments (250 games or 10 minutes, row groups of
> about 50 games, a commit line in `segments.json`). This folder is kept for its evidence (the profiling numbers in
> `design.md`). Do not implement its tasks and do not merge its spec delta; archive it as superseded when
> `response-log-segments` closes (task 10.2).

## Why
Currently, MLB per-game ingestion writes one `.parquet` file and performs an atomic manifest commit for every individual game across 13 datasets. In a 2,430-game season, this produces ~31,500 tiny Parquet files and ~31,500 manifest re-serializations per season.

Profiling (Task B-335) confirmed that in-memory normalization takes only ~11.5 ms per endpoint (~150 ms for a full game), whereas the individual filesystem writes and manifest updates take 350–950 ms per game (70–80% of total runtime). Writing many games into larger chunk files per dataset partition will reduce I/O overhead by 10x–20x, dramatically speed up historical downloads, and produce optimal Parquet file sizes for DuckDB and Polars query engines.

## What changes
- Batched chunk writing: The ingest runner and `ProcessedStore` buffer game rows up to a configurable batch size (default 50 games per batch, or a calendar month) before committing a single consolidated `part-batch-<N>.parquet` file per dataset partition.
- Atomic commit & resume guarantees: Manifests record the set of `game_pk`s contained within each batch. If an extraction is interrupted mid-batch, the uncommitted `.part` file is discarded, and resuming picks up cleanly from the first uncommitted game without duplicate rows or missing contests.
- Seamless reading: Readers (`baseballpy.read`, DuckDB synced views, Polars scans) read batched files transparently alongside legacy single-game files without requiring schema or code changes.

## Impact
- Spec: `caching-and-invalidation`, `cli-and-ingest`.
- Code: `src/baseballpy/core/stores.py`, `src/baseballpy/ingest/runner.py`, `src/baseballpy/sources/mlb_api/generic.py`.
- Tests: `tests/test_batched_chunks.py`.
