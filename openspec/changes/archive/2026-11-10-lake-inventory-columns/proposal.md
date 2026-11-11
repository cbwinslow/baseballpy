# Proposal: `v_season_catalog` becomes the lake inventory

## Why

The owner asked how downloaded files are tracked and found it hard to see "what do I hold". The
records already exist: per-dataset `_manifest.json` files, raw checksums, `catalog status`, and the
DuckDB view `v_season_catalog` (one row per source, dataset and season with `row_count` and `files`,
computed from Parquet footers at `db sync`). What the view lacks is what a person needs to read it as
an inventory: which view to query, how big it is on disk, and when it was last written.

## What

- Add three columns to `v_season_catalog`, after the existing five (no existing query breaks):
  `view_name` (the DuckDB view that serves the dataset; for an unregistered folder
  `<source>_<dataset>`), `bytes` (size of the visible Parquet files) and `last_written_at`
  (newest file modification time, UTC).
- Document the view as the inventory (README, `docs/DATA_WORKFLOW.md`).
- One requirement and scenario in the `lake-access` spec, one ADR.

## Out of scope

- No new tracking file, no change to manifests, raw checksums or the audit log.
- No "missing datasets" rows: what the lake should hold is `catalog status` and `catalog coverage`.
- `last_written_at` is the file time, not the provider download time (compaction rewrites files);
  the per-chunk `fetched_at` stays in the manifests (reading every manifest would slow `db sync`).
