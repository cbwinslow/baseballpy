# Change Proposal: Aligned Statcast Chunk Windows (No Overlap Duplicates)

## Context & Motivation
AGENTS.md section 3 requires idempotent upserts keyed by `(game_pk, at_bat_number, pitch_number)`. The Statcast extractor writes one parquet part per *window*, named after the window (`part-<start>_<end>.parquet`), and `extract(start, end)` anchors its 5-day windows at the caller's `start`. Two calls whose ranges overlap but start on different days therefore write differently named parts that contain the same pitches, and the DuckDB view returns each overlapped pitch twice. Found 2026-10-27 during the minor-league live check: an unfiltered re-fetch of 2024-06-15 after a 2024-06-10..16 ingest produced 6,042 duplicate pitch keys.

| ID | Gap |
|----|-----|
| A-1 | Window boundaries depend on the caller's start date, so persisted chunks can overlap. |
| A-2 | `ingest_season` (anchored at the season start) and ad hoc `extract` ranges can overlap each other. |
| A-3 | No test asserts that overlapping/nested requests leave the dataset duplicate-free. |

## Proposed Changes
1. `grid_windows(start, end, chunk_days)`: windows anchored to a fixed per-year grid (block *k* = January 1 + k x chunk_days), so a given day always belongs to the same window regardless of the caller. Windows never cross a year boundary.
2. `extract`/`extract_async` and `ingest_season` fetch grid windows; `extract` filters the result to the requested `game_date` range, so callers still get exactly what they asked for.
3. `duplicate_keys` becomes part of `extract`'s persistence path for the touched season (warns when it finds surplus rows), and a regression test covers overlapping, nested and adjacent ranges.
4. Document the grid in `docs/sources/statcast.md`; `split_date_range` remains as the plain splitter.

## Out of Scope
Re-chunking data written by earlier versions (none exists outside scratch lakes); a `repair`/`dedupe` command (belongs to the unified CLI change).

## Impact
Part file names for unaligned requests change (windows are grid-aligned); view schemas and keys are unchanged. Recorded as ADR 32.
