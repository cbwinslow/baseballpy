# Design: response-log-segments

The owner decided this design on 2026-11-08 after a review by an Opus design pass. This file says how it works,
which numbers are measured and which are guessed, and what can go wrong.

## 1. The flow for one source and one season

```text
fetch URL once -> journal record (zstd, flushed per game)
               -> parse once -> rows for every dataset made from that URL (in memory, <= ~50 games)
every 250 games or 10 minutes (to test):
   _open/seg-NNNN.*.part  ->  rename into place  ->  append one line to segments.json   (= commit)
```

- **D1 One download, one stored copy.** A response is identified by the sha256 of its original bytes. Every dataset
  made from it points at it with `_raw_sha256`. Nothing is stored per dataset on the raw side.
- **D2 Parse once.** A response that feeds several datasets is parsed once and the parsed value is handed to each
  normalizer. Which datasets come from which URL is data in the endpoint registry (one declarative table), not code
  per source.
- **D3 Journal.** `raw/<source>/season=Y/_open/journal.zst`: one record per response, each record its own zstd frame
  (`pyarrow.Codec("zstd")`) with a length prefix, so a torn last record after a crash is detected and dropped. It is
  flushed after each game. On restart the journal is replayed into the open batch: finished games are not fetched
  again. The journal is deleted only after the segment's commit line exists.
- **D4 Raw segment.** `raw/<source>/season=Y/seg-NNNN.parquet`, columns `url`, `fetched_at`, `status`, `etag`,
  `sha256` (of the original bytes), `body` (the original bytes), plus `legacy_path` for rows made by the converter.
  Parquet compresses `body` with zstd. Pages must be large enough to hold many bodies, or Parquet compresses each
  body alone and the "many games together" gain below is lost (`data_page_size` is a writer option; the value is
  measured in task 2.4).
- **D5 Processed segments.** `processed/<source>/<dataset>/season=Y/seg-NNNN.parquet`, one per dataset per segment,
  written with a `pyarrow.parquet.ParquetWriter` one row group of about 50 games at a time, so at most about 50 games
  of rows are in memory. A dataset with no rows in a segment gets no file (its count in the commit line is 0).
- **D6 Commit protocol.** Every file is first written in `_open/` with a name ending in `.part` (readers only match
  `*.parquet`, and `_open` is hidden from pyarrow by its underscore). For processed files the `_open/` folder is the
  dataset's own season folder (`processed/.../season=Y/_open/`), so the rename never crosses a disk, even when
  `LakeConfig` puts `raw` and `processed` on different drives. Renames use the existing retry
  (`core/atomic.py::_replace_with_retry`). The last step appends one JSON line to `raw/<source>/season=Y/segments.json`:
  segment id, the game (chunk) ids, the sha256 of each file, row counts per dataset, the schema fingerprint per
  dataset, the raw location. A game is stored only when its line exists. A torn last line is ignored.
- **D7 Start-up.** For each season folder: delete `.part` files and renamed files that no line names, then replay
  the journal. This is the same rule for a crash, a kill and a power cut.
- **D8 One writer.** One writer per source and season. The existing host lock (`core/hostlock.py`, one downloader per
  host) already gives this for downloads; the converter, the rebuild and the round-trip check take the same lock.

## 2. The listing rule (no double count)

- Views and `read` read `season=*/*.parquet` for a season-split dataset (one folder level, so `_open/` and
  `_legacy/` are never read), and `*.parquet` for one that is not split. Today views use `**/*.parquet`; this
  changes.
- **Refresh of a committed segment** (rare: a corrected game, a schema rebuild): the new file takes the old file's
  name and replaces it with one atomic rename. A reader sees the old rows or the new rows, never both. The refresh's
  journal stays in `_open/` until its commit line is written; on start an open refresh is run again (it is
  repeatable: same journal, same files), so a crash between renames never leaves a mixed segment for long.
- **Migration of a season** (task 6.3): the old `part-*`/`compact-*` files are first moved into `season=Y/_legacy/`
  (hidden), then the segments are renamed in. During that step a reader may see a season with no rows for a moment,
  never with rows twice. `_legacy/` is deleted only after the row-count check passes.

## 3. Numbers: measured and guessed

**Measured** (read-only pass over the 2024 lake, 40 sampled files per dataset, 2026-11-08):

| What | Size |
|---|---|
| live feed, one game, raw | 828 KB |
| live feed, gzip (today) | 128 KB |
| live feed, zstd level 9 | 102 KB |
| live feed, zstd level 19 | 90 KB |
| 30 live feeds compressed together, zstd 19 | 2.29 MB (gzip files today: 4.05 MB) |
| boxscore, 30 games together, zstd 19 | 0.14 MB (gzip files today: 0.56 MB) |
| 2024 feed files that were NOT byte-identical across the 4 datasets | 177 of about 83,000 |

**Measured earlier** (carried over from the drafts and ADRs, not re-checked here):
- `shared-raw-bytes` draft: `raw/mlb_api` held 23.3 GB, about 12 GB of it exact copies. It also gave 3.02 MB per live
  feed and 0.57 MB per boxscore uncompressed, which does not match the 828 KB above; task 2.4 re-measures.
- `batched-chunk-writes` draft and ADR 92: normalizing a game takes about 150 ms; storing 13 per-game chunks took
  350 to 950 ms; one 611-column chunk took 96 ms to store; 50 games in one write cost 133 ms.
- ADR 94: compacting a season's 38,000 small files took more than 45 minutes; the download takes about 35.

**Guessed** (to be replaced by measurements in tasks 2.4, 4.4 and 5.4):
- raw for 2008-2026 about 12-15 GB instead of about 47 GB today.
- whole lake about 40-50 GB with all raw kept.
- 250 games or 10 minutes per segment, 50 games per row group: chosen so memory stays small; not tested.
- zstd 19 write speed is fast enough for a season (a few minutes against a 35-minute download).

## 4. Risks and what we do about each

| Risk | Mitigation |
|---|---|
| Windows file locks and antivirus hold a file during a rename or delete | Open files live only in `_open/`; renames and deletes use the existing retry; a rename that still fails stops the run loudly and the journal is replayed on the next start. |
| Memory: wide tables grow about 28 times in memory on Windows (commit a885134) | Row groups of about 50 games written as they fill; nothing holds a whole segment. 250/50 are guesses; task 4.4 measures peak memory on a real season and adjusts. |
| Double count between a refresh's rename and the old file's delete | Section 2: a refresh replaces the file under the same name (no second file), migration hides old files first (a short gap, never a double). Tested in `tests/test_segment_views.py`. |
| Two writers on one season | Host lock (D8), also taken by the converter, rebuild and round-trip check. |
| Live feed: many small files while games are in play | Out of scope here. Plan: one small segment per in-play game, replaced as it updates, merged into the day's segment once final. `compact` stays until that change. |
| 177 of about 83,000 feed files in 2024 differ between the 4 datasets | Do not assume identical bytes. Task 1.3 finds out why before the converter is built. The converter checks each file's sha256 and keeps every distinct body as its own row. |
| `_raw_sha256` added to every processed schema changes every schema digest, so every stored chunk would look stale ("A Schema Change Invalidates Stored Chunks") | Task 3.7: the lineage column is added by the generic writer and left out of the schema digest; old files read it as empty. Needs an ADR amendment if built differently. |
| A raw-only move loses data we have not typed | The round-trip check (task group 8) only passes when the processed rows hold every value of the response; anything untyped shows up as a failure, and raw stays. |

## 5. Prior art

Web search done 2026-11-08 (task 1.2, standard mode, three searches; sources are mostly secondary pages, so the
points below are what they say, not first-hand checks of the specs):
- **WARC (ISO 28500, web archives).** One record per HTTP response (header block + body), written into large
  files, each record compressed on its own (one gzip stream per record, joined end to end) so a single record can
  be read without the rest. Identical content is recorded once as a "revisit" record that points at the first
  record by digest; the format does not dedupe by itself, the writer must look up the digest. This is our raw
  segment idea (one row per response, digest, big file). Differences: we use Parquet rows with zstd so DuckDB can
  query the metadata, and one shared row serves all 13 datasets (the same job as a revisit record, without a
  second record). Per-record compression is also why WARC dedupes badly inside the file; compressing a whole row
  group together (our measurement: 2.29 MB vs 4.05 MB for 30 games) is the better fit.
- **DuckLake (DuckDB Labs; 1.0 announced).** Data stays in Parquet, metadata lives in a SQL database. "Data
  inlining" keeps small inserts (default limit 10 rows per insert) in the catalog and flushes them to Parquet
  later, so small writes do not create tiny files. That is exactly our live-feed problem. Reported caveats: the
  big speed claims come from DuckDB Labs or articles repeating them, not independent tests, and one source says
  writes go through a single DuckDB process, the same limit as our one-writer rule. It needs a catalog database
  file, and only DuckDB reads the table correctly. Not chosen now (ADR 97). Revisit before the live feed, and
  measure its inlining then. Our `segments.json` stays plain files in the meantime.
- **pybaseball.** Its cache is off by default (so it does not use the user's disk without asking), stores Parquet
  or CSV, and lives in `~/.pybaseball/cache` (override with `PYBASEBALL_CACHE`). It caches the parsed result of a
  call, not the raw response, and a known problem is that a call for a future date caches an empty result. Lesson
  for us: never commit an empty or failed response as a finished game (task 4.x checks that a game is complete
  only when all its URLs returned data). baseballr and the SportsDataverse packages: the search found nothing
  about raw-response caching; the earlier guess in this file ("one file per request") was not confirmed and is
  withdrawn.
- **Conclusion.** Nothing found contradicts the design (large compressed files, one record per response with a
  digest, plain Parquet for typed data). The only new design input is the pybaseball empty-result lesson, added as
  a test requirement in task 4.1.

Sources: motherduck.com/blog/ducklake-architecture-deep-dive, ducklake.select (data inlining, 2026-04-02),
loc.gov/preservation/digital/formats/fdd/fdd000236.shtml (WARC), pypi.org/project/warcio, pypi.org/project/pybaseball.

## 5b. Why sibling raw files differ (task 1.3, found 2026-11-08, read-only, from the manifests and a JSON diff)

The differing files are **not corruption and not a bug**. They are the same URL downloaded on different days.
- **Live feed (4 datasets, one URL).** In 2024, 165 of 2,959 games differ. In every one, the odd dataset out is
  `game_feed_linescore_innings` (142 fetched on 2026-11-07, 23 on 2026-11-08); the other three were fetched later
  (2026-11-08) and agree with each other. 2025: 346 differ, all the same odd dataset, all fetched 2026-11-07. 2021:
  1 differs (a different dataset, fetched 2026-11-08). The odd dataset was downloaded in an earlier run, and the other
  three were downloaded again later.
- **What changed between the two downloads.** MLB revises the finished game's live feed: a player gains a
  `primaryNumber` or flips `active`/`lastPlayedDate`, the venue time zone changes (`EST`/`-5` to `EDT`/`-4`), and
  hot/cold zone data appears or goes. Whole-game plays are the same. So the feed is **not immutable after the game**.
- **Box scores (6 datasets, one URL).** In 2024, 8 games split 3 against 3, and the parsed JSON is **identical**: only
  the bytes differ (formatting or key order). The two halves were fetched on different days too (2026-11-07 and
  2026-11-08).
- **What this means for the design.**
  1. A raw row's identity is `(url, fetched_at, sha256)`, not the URL alone. A refetch that returns different bytes
     is a new row, never an overwrite (this is already how the converter is specified; now it is evidence-based).
  2. Today's processed tables are slightly inconsistent for these games: the three feed datasets come from the later
     version and `game_feed_linescore_innings` from the earlier one. The new single fetch removes this by
     construction.
  3. Rebuild (group 6) rule, to be added to the spec: when a URL has more than one stored version, rebuild every
     dataset from the **newest** version and keep the older rows in raw. This makes the 4 datasets agree again.
  4. The converter's hash check (task 5.x) must expect different bytes and keep both bodies; it must not treat a
     difference as an error. It records a count of such URLs in its report.
- **Evidence:** scripts in the session scratchpad (`why_differ.py`, `odd.py`), read-only. Numbers above are from the
  per-season `_manifest.json` files (`sha256`, `fetched_at`) plus a decoded JSON diff of two examples per group.

## 6. Rollback

The git tag `pre-response-log` (already pushed) is the revert point. Until task group 7, the old per-game path and
the old files stay readable, so a revert loses no data written in the old layout. Segments written before a revert
are plain Parquet and stay readable with DuckDB or pyarrow directly.

## 7. Evidence (filled in as tasks land)

Nothing implemented yet.
