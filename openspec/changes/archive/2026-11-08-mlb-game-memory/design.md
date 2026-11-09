# Design: MLB Game Memory & Manifest Optimization

## Problem

During a full-season download of MLB game feeds (e.g. 2026, ~16,000 games across multiple leagues, writing 13 datasets in parallel across 12 worker threads), the process halted after 7.9 hours with:

```text
  File ".../src/baseballpy/core/atomic.py", line 377, in save
    part_path.write_text(payload, encoding="utf-8")
MemoryError
```

### Root Cause Analysis

1. **Monolithic Dataset Manifests:**
   In `ProcessedStore.put()`, every chunk write called:
   `self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(...)`
   Without `season` specified, `dataset_manifest` placed a single `_manifest.json` at the dataset root (`processed/mlb_api/<dataset>/_manifest.json`).
   For high-cardinality game datasets (`game_feed_plays`, `game_boxscore_officials`, `game_win_probability`), this single file accumulated over 40,000 entries and grew to 9.2 MB – 9.6 MB of text.

2. **Synchronous Serializations Across 12 Worker Threads:**
   In `ManifestTracker._set()`, every single chunk write triggers `self.save()`.
   `save()` used standard library `json.dumps(disk, separators=(",\n", ": "))` which produces a newline after every comma.
   When 12 worker threads concurrently dump 9.6 MB JSON strings in tight loops, the Python heap experiences massive string allocation churn, leading to memory fragmentation and `MemoryError`.

## Design

### 1. Zero-Copy `msgspec` Serialization in `ManifestTracker`
Replace Python's standard `json.loads` and `json.dumps` in `ManifestTracker` with `msgspec.json.decode` and `msgspec.json.encode`.
- `msgspec` encodes directly to UTF-8 bytes at C-speed with minimal memory overhead.
- Writing bytes with `part_path.write_bytes(payload)` eliminates intermediate multi-megabyte string copies.

### 2. Per-Season Manifest Partitioning in `ProcessedStore`
For partitioned datasets (`spec.partition == "season"`), store manifests inside the season directory:
`processed/<source>/<dataset>/season=YYYY/_manifest.json`

- A season manifest contains ~2,430 games instead of 40,000+, keeping the file size under ~150 KB.
- Serializing 150 KB with `msgspec` takes < 1 ms and negligible RAM.

### 3. Backward Compatibility
When checking if a chunk is cached (`is_cached`, `has_part`, `read_part`):
- Check the season-specific manifest first.
- If not found or status != COMPLETED, check the dataset root manifest (`_manifest.json`) so previously ingested partitions remain recognized without re-downloading.

## As built (2026-11-07, B-308)
Only design item 1 (bytes in, bytes out with `msgspec`) was built. Item 2 (per-season manifests) was not: `status`, `compact`, `coverage` and the layout check all read the dataset-level manifest, and the measurement below shows it is not needed yet. The first version of the change used broad `except Exception` handlers and a silent fallback to `json.dumps`; both were removed (they hid failures and brought the memory spike back).

Measurement (scratch script, 50,000-entry manifest of 10.5 MB, 5 saves): 0.41 s in all, peak extra memory 15.3 MB. The real `game_feed_plays` manifest holds about 9,000 game entries (6.9 MB); a full 2008 to 2026 run would reach about 50,000. Not measured: a real 49,000-game run (that is the next download).
ADR 88 records the decision.
