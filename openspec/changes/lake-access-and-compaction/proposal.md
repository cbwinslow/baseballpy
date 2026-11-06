# Lake access and compaction

## Why
The owner wants one simple query to load, for example, every Statcast pitch from 2008 to 2026 with all fields into a DataFrame, quickly, and to join, group, sum and filter like a SQL database with DuckDB. Measured on the real lake (2026-11-06): Polars reads all 14,971,703 pitches by 121 columns in 1.8 seconds, but the same rows through the DuckDB view took 549 seconds (and a second DuckDB read had not finished after 280 seconds); one season takes 5.4 s through the view, 3.7 s with DuckDB on the files, 1.1 s with pyarrow and 0.14 s with Polars. The layout (Hive-partitioned Parquet) is right; the access path and the number of small files are not.

## What changes
1. DuckDB views stop forcing a schema merge (`union_by_name`) over every file: the schemas are strict and equal.
2. One documented, tested entry point for the two jobs: `baseballpy.read(...)` loads rows straight from Parquet into Polars (or pandas or Arrow) by season and columns, and `baseballpy.sql(...)` runs DuckDB SQL (joins, group, sum, filter) over the same views.
3. A `compact` step merges the small download chunks of each dataset and season into files of sensible size (DuckDB advises 100 MB to 10 GB per file and 100,000 to 1,000,000 rows per row group), after downloads, without losing resumability.
4. Raw files are stored compressed (checksum of the original bytes unchanged), with a conversion command for the existing lake.
