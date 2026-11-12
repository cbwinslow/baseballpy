# Proposal: retrosheet-site-logs (phase 2: player, manager and umpire logs as tables)

## Why
The owner asked (2026-11-11) for the Retrosheet files we lack to become queryable tables (Parquet, DuckDB, Polars),
not raw files. Three consulted models advised leaving the logs raw to stay simple; the owner decided: build the tables.
The files are regular (checked 2026-11-11): every member of a kind has the same header.

## What
Five opt-in datasets from the zips already stored by `retrosheet-site-files`, in the same `ingest retrosheet` command
(the `site` unit): `player_batting_logs` (21,999 files, 40 columns), `player_fielding_logs` (21,714, 29),
`player_pitching_logs` (11,279, 43), `manager_logs` (859, 112) and `umpire_logs` (1,762, 48). Members are streamed in
batches into strict typed Parquet; an `umpire_id` column is added from the file name because the umpire logs do not
carry it; unknown columns land in `_extras`; nothing is dropped.

## Out of scope
Negro Leagues bundle, event CSV bundles and official-total ledgers (still raw, decision pending); `catalog find`.
