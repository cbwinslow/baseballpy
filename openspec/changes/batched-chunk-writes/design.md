# Design: batched-chunk-writes

## Decisions

- **D1 Explicit batch boundary and atomic flush:**
  Batches are bounded by a fixed game count (e.g. 50 games) or the end of a season. Tables for all 13 endpoints accumulate in memory during the batch. When the batch completes, `pyarrow.concat_tables()` combines the records and writes one consolidated `part-batch-<start_pk>-<end_pk>.parquet` file per endpoint with a single manifest commit.
- **D2 Invariant resume checkpointing:**
  A batch is either fully committed or not at all. If the process terminates while game 38 of 50 is downloading, the temporary `.part` files are removed on the next run, the manifest checkpoint remains at the previous committed batch, and extraction resumes cleanly from game 1 of the uncommitted batch.
- **D3 Coexistence with legacy files and compaction:**
  Batched chunk files adhere to the existing partition directory structure (`processed/<source>/<dataset>/season=<season>/`). DuckDB views and `baseballpy.read` scan the entire directory with zero change. Future `baseballpy compact` runs merge any remaining single-game chunks into standard seasonal files seamlessly.

## Measurements & Speed Projections
- Profiling baseline: ~150 ms pure normalization vs ~520–1,114 ms total per game with individual writes.
- With batched writes of 50 games: 1 manifest rewrite and 1 file write per 50 games drops write overhead from ~400 ms/game down to ~15 ms/game, cutting elapsed ingestion time per season by **60% to 75%**.
