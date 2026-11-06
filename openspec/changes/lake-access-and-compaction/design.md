# Design: lake access and compaction

## Evidence (real lake, 2026-11-06, other downloads running at the same time)
| Test | Result |
|---|---|
| Statcast processed: files, size | 963 files, 1.57 GB, median 2 MB, one row group each (5-day windows of about 20,000 rows) |
| `count(*)` of all pitches through the DuckDB view | 2.1 s |
| `sum(release_speed)`, all years, one column | 2.1 s |
| One season, all 121 columns, DuckDB view to Arrow | 5.4 s |
| Same, DuckDB `read_parquet` on the files | 3.7 s |
| Same, DuckDB on one 100 MB file | 2.4 s |
| Same, pyarrow `read_table` | 1.1 s |
| Same, Polars `read_parquet` | 0.14 s |
| **All 14,971,703 pitches x 121 columns, Polars** | **1.8 s** (6.3 GB in memory) |
| Polars group by season, mean velocity, all years | 0.38 s |
| **All pitches, DuckDB view to Polars** | **549 s**; a direct DuckDB read without `union_by_name` did not finish in 280 s |
| MLB per-team datasets | 13,211 raw and 13,193 Parquet files per dataset, 1 to 20 KB each; 387,000 of 403,000 files in the lake |
| Raw size | MLB 16.9 GB in 218,070 files, Statcast 11.6 GB, all uncompressed; Kalshi catalog raw fell 2.2 GB to 58 MB once gzipped |

Reading: the Hive layout is the standard recommendation and Polars and pyarrow read it very fast. DuckDB is excellent for questions that return little (counts, sums, joins, group by) but is slow when asked to hand every row and column back as a DataFrame, and its views pay a per-file cost (`union_by_name` opens every file). So two doors, one lake: `read` for bulk rows into a DataFrame, `sql` for analysis. Joins through DuckDB were not timed yet (task 1.2).

## Outside reading (web search 2026-11-06)
- DuckDB documentation: Hive-style folders let filters skip folders; per-file sizes of 100 MB to 10 GB; row groups of 100,000 to 1,000,000 rows (default 122,880), at least as many row groups per file as query threads; per-row-group min/max statistics skip data when sorted by the filter column; row groups under 5,000 rows can be 5 to 10 times slower. Many small files are an inference from the metadata cost per file.
- `statcast-pitches` (PyPI, Hugging Face dataset): Polars lazy filter by year or DuckDB SQL; its own benchmark loads in 27 s (Polars). `FFDB` (GitHub): local Statcast in Parquet plus DuckDB with a refresh CLI. No source documents a year-partitioned Statcast lake with both Polars and DuckDB examples, so this is built here.

## Decisions
1. Keep `processed/<source>/<dataset>/season=YYYY/` Hive Parquet as the one truth (DuckDB, Polars, pyarrow, pandas all read it directly).
2. Views: `read_parquet(glob, hive_partitioning=true)` without `union_by_name`; a test fails if two parts of one dataset have different schemas (then the strict schema is wrong, not the view).
3. `baseballpy.read(dataset, seasons=None, columns=None, backend="polars", lazy=False)` and `baseballpy.sql(query, backend="polars")`, with recipes in the quickstart and a test that checks results equal the DuckDB view and that a season loads in a time budget relative to the file size.
4. `baseballpy compact [--source S] [--dataset D]`: per dataset and season, merge all parts into files of about 100 MB to 1 GB, row groups of about 122,880 rows, zstd, sorted by the dataset key, written atomically; the manifest records the compacted file and the chunk ids it replaced; a rerun only compacts what changed; chunks stay resumable until compaction runs. Row counts and key sets before and after must be equal (checked by the command and by a test).
5. Raw files: stored zstd or gzip compressed with the checksum of the original bytes; `RawStore.get` decompresses; one command converts the existing lake; no source reads raw files by path.
6. Run compaction and conversion only when no ingest is running.

## Not decided
Whether very small datasets (a few thousand rows) become one file for all seasons (likely yes), and the exact target size per source.

## Result of the quick fix (2026-11-06, tests running at the same time)
| Test | Before | After |
|---|---|---|
| `count(*)` all pitches, DuckDB view | 2.1 s | 1.3 s |
| One season, all 121 columns, DuckDB view | 5.4 s | 4.6 s |
| Group by season, DuckDB view | 2.1 s | 2.5 s (noise) |
| All pitches x 121 columns, `baseballpy.read` | 1.8 s (Polars direct) | 2.0 s |
| One season, 3 columns, `baseballpy.read` | n/a | 0.13 s |
Dropping `union_by_name` helps a little; the real fix for bulk rows is `read`. `db sync` took over 15 minutes because it opens about 400,000 small files (route names, footers); compaction (2.1) is what fixes that.

## Result of compaction on the real lake (2026-11-06)
| Measure | Before | After |
|---|---|---|
| Parquet files in `processed/` | about 400,000 (84,022 small chunks, 115,017 zero-row) | about 4,300 |
| `baseballpy db sync` | over 15 min | 19.5 s |
| DuckDB count of all pitches | 1.3 s | 0.27 s |
| DuckDB one season, 121 columns | 4.6 s | 0.84 s |
| DuckDB group by season | 2.5 s | 0.34 s |
| `baseballpy.read` all pitches | 2.0 s | 1.4 s |
| Chunk lookups (40 cached reads) | 4.6 s | 0.26 s |
| `ingest mlb_api --seasons 2022`, everything downloaded | about 6 h | 57 s, 0 requests |
| Processed size | 4.9 GB | 6.9 GB incl. Kalshi trades 3.1 GB (trades grew 7 percent) |
Found on the way: the first real run refused Statcast 2008 because each chunk has its own dictionary for text categories (the check now compares values); 12,652 zero-row files per dataset were never merged (now deleted); `dataset_manifest()` built a new tracker, and parsed 4.5 MB, on every call (now shared).
