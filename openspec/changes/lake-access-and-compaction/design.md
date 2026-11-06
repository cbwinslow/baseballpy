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
