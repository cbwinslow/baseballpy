# Proposal: response-log-segments

## Why
- We keep the raw upstream bytes (the contract: never leave upstream data behind), but today we keep them once per
  dataset, not once per download. One MLB game is 5 URLs that feed up to 13 datasets. The live-feed JSON is saved
  4 times and the boxscore JSON 6 times: about 20 GB of copies in `raw/mlb_api` (owner's count, 2026-11-08).
- Every game also writes one small Parquet file per dataset and a manifest entry. That is tens of thousands of small
  files per season, a compaction pass that takes longer than the download (ADR 94), and most of the per-game time
  (ADR 92, ADR 93).
- Two drafts tried to fix one half each: `shared-raw-bytes` (store raw once) and `batched-chunk-writes` (many games
  per file). Both problems have one cause: data is stored per dataset and per game instead of per download and per
  batch. This change fixes both with one mechanism and replaces the two drafts.

## What changes
- **Response log.** Each HTTP response is stored once, compressed, and shared by every dataset made from it. The flow
  per source and season is: fetch each URL once, parse it once, feed every dataset that comes from it.
- **Crash journal.** Finished responses go to `raw/<source>/season=Y/_open/journal.zst` (one compressed record per
  response, flushed after each game). A crash or restart never downloads a finished game again.
- **Segments.** Every 250 games or 10 minutes (both numbers to be tested) the open batch closes as a segment: one raw
  file `raw/<source>/season=Y/seg-NNNN.parquet` (url, time, status, etag, sha256, zstd body) and one file per dataset
  `processed/<source>/<dataset>/season=Y/seg-NNNN.parquet`, written in row groups of about 50 games so memory stays
  bounded. Each processed row carries `_raw_sha256`, the response it came from.
- **Commit by one line.** Files are written in `_open/` under temporary names and then renamed. The last step appends
  one line to the season's `segments.json`. A game counts as stored only when that line exists. On start, files with
  no line are deleted and the journal is replayed.
- **Readable at once.** New data can be queried as soon as its segment commits. DuckDB views and `baseballpy.read`
  read segment files beside the old `part-*`/`compact-*` files and never read `_open/`.
- **One format.** Parquet with zstd everywhere; no new dependency (`pyarrow` has zstd). The `.duckdb` file keeps only
  views.
- **Less compaction.** A season ends as a few big files per dataset, written once. The queue's heavy compaction step
  goes away for sources that write segments. `baseballpy compact` stays for old part files and for the future live
  pipeline.
- **Schema changes.** One generic path: rebuild a segment from its raw rows with the new normalizer (extends ADR 87).
- **Old data.** A converter turns the existing gzip raw files into raw segments, checks every sha256 against the old
  manifests, keeps every distinct body, and removes copies only after a full check (dry run first). Processed
  segments are then rebuilt from raw and their row counts compared with today's files.
- **Retention.** All raw stays on the laptop for now. Later, raw may move off the laptop only after a per-segment
  round-trip check passes; it is moved, never deleted, and `segments.json` records where it is.
- **All sources.** After MLB, Statcast, Retrosheet and the others use the same generic mechanism (registry plus one
  function, behind `SinkProtocol`; no per-source special cases).

## Not in this change
- DuckLake, Iceberg or Delta tables, and data inside the `.duckdb` file (ADR 97 says why and when to look again).
- The live-feed pipeline itself (its small per-game segments and their merge are described in `design.md` only).

## Replaces
- `openspec/changes/shared-raw-bytes/` and `openspec/changes/batched-chunk-writes/`: kept for their evidence, marked
  superseded, their tasks folded into this change (see their `proposal.md`). Their spec deltas are not to be merged.

## Impact
- Specs: `caching-and-invalidation` (how responses and segments are stored and committed) and `lake-access` (how
  readers see them). Two capabilities because the storage rule and the reading rule change together; each delta
  stays inside its own spec.
- ADRs 95, 96 and 97.
- Code (later tasks, not this slice): a new `core/` response-log and segment writer behind `SinkProtocol`, the MLB
  per-game path, `database.py` and `access.py` listing, a converter and a rebuild command, the queue's compaction
  step, then the other sources.
- Rollback: git tag `pre-response-log` (already pushed) is the revert point. The old layout stays readable until
  task group 7.
