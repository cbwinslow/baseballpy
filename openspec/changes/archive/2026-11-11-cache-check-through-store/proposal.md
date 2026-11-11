# Proposal: every cache decision asks the store, not the file name

## Why

`ProcessedStore.is_cached` and `has_part` know that a chunk can live in a plain `part-*.parquet` file or
inside a `compact-NNNN.parquet` file (`holds_chunk` checks the file exists and its footer still lists the
chunk). Most sources use them. The Statcast pitch extractor does not: `_is_chunk_fresh` asks
`cache_path.exists()` for the plain part file and `_fetch_chunk` reads that path directly
(`sources/statcast/extractor.py`, lines 265 and 332). After `baseballpy compact` the part files are gone, so
every window of a compacted Statcast season would be downloaded again, and a cache hit would try to read a
file that does not exist. The same user running the same workflow twice would get different behaviour
depending on whether they had compacted: this breaks AGENTS.md section 15 (same inputs, same results).

This is task B-409 of `product-mandate-reproducible-outputs`: ingest must treat a chunk its compacted file
holds as stored, and a chunk its compacted file lacks as missing.

## What

- Statcast pitches (`extractor.py`): the freshness check uses `store.has_part` and a cache hit reads with
  `store.read_part`, so plain and compacted chunks behave the same.
- Tests (written first) in `tests/test_cache_through_store.py`: a season that was compacted is served from the
  lake with no request; a compacted file that lost its chunks makes the windows download again and the rows
  come back identical.
- One requirement in `caching-and-invalidation`, one ADR.

## Out of scope

- Retrosheet's quality check and parent lookup read `part_path` directly (they skip a compacted chunk);
  Retrosheet and leaderboard chunks are one per season folder and are never compacted today. Mapped as B-424.
- Leaderboards and Lahman (one chunk per folder; compaction needs two).
