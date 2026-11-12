# Proposal: fast-view-sync (the DuckDB view refresh no longer reopens every Parquet footer)

## Why
Every `baseballpy ingest` ends with a DuckDB view refresh. It rebuilt the `v_season_catalog` inventory by opening the
footer of every Parquet file in the lake (176,897 files on 2026-11-11) to count rows: about 35 minutes after a download
that took 3. The owner wants the tool to be easy and fast.

## What
Row counts of Parquet footers are cached in `cache/footer_rows.json`, keyed by relative path with the file size and
modification time. A footer is opened only for a new or changed file, and those first reads run 16 at a time.
