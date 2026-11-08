# Proposal: shared-raw-bytes

> **Superseded (2026-11-08) by `openspec/changes/response-log-segments/` (ADR 95).** The owner chose one mechanism for
> both raw copies and small files: each response stored once in Parquet raw segments, not one blob file per
> response. This folder is kept for its evidence (the 23.3 GB / 12 GB measurement in `design.md`). Do not implement
> its tasks and do not merge its spec delta; archive it as superseded when `response-log-segments` closes (task 10.2).

## Why
In `raw/mlb_api/`, upstream responses are saved once per dataset cut from them rather than once per HTTP request. Specifically, MLB Stats API per-game extraction fetches two large multi-dataset payloads:
1. `v1.1/game/{game_pk}/feed/live` (~3.02 MB uncompressed): 4 datasets (`game_feed_plays`, `game_feed_play_events`, `game_feed_linescore_innings`, `game_feed_officials`) each write a complete copy of the live feed JSON.
2. `v1/game/{game_pk}/boxscore` (~0.57 MB uncompressed): 6 datasets (`game_boxscore_teams`, `game_boxscore_players`, `game_boxscore_info`, `game_boxscore_officials`, `game_boxscore_top_performers`, `game_boxscore_pitching_notes`) each write a complete copy of the boxscore JSON.

Across a single 2,430-game season, the live feed alone writes ~12.08 GB of raw data where ~9.06 GB is pure duplicate bytes. Across 16 seasons (2008–2024), this represents ~140 GB of raw duplicate copies. This redundancy recently pushed available disk space down to the 4.0 GB safety threshold, pausing the automated history runner.

## What changes
- Content-addressed shared raw storage: `RawStore` supports content-addressed raw blobs under `raw/_blobs/<sha256>.json.gz` (or `raw/<source>/_shared/<endpoint_group>/`).
- Manifest raw references: Dataset raw manifests record `blob_ref` (or content pointer) pointing to the shared payload with its verified sha256 checksum, file size, and timestamp.
- Deduplication of existing lake data: A safe `baseballpy deduplicate-raw` command that inspects existing raw manifests, replaces redundant physical copies with blob references, and frees ~12+ GB of immediate disk space without losing a single byte.
- Zero-copy ingest: When multiple datasets are normalized from the same in-memory response, `RawStore.put` saves the raw blob once and creates lightweight pointer entries in each dataset's manifest.

## Impact
- Spec: `caching-and-invalidation`.
- Code: `src/baseballpy/core/stores.py`, `src/baseballpy/sources/mlb_api/generic.py`, `src/baseballpy/cli_lake.py`.
- Tests: `tests/test_raw_shared.py`, `tests/test_cache_check.py`.
