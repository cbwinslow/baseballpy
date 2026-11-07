# Folder and name audit

## Why
The owner asked that folders are organized, files are named properly and storage makes sense. A scripted audit on 2026-11-07 of the registry (480 datasets), the real lake and the repository found the rules were followed but written down nowhere and tested nowhere.

## Findings
- Registry: all 9 sources and 480 datasets are `lower_snake_case`; 0 duplicate view names; every source has a doc file and every doc file has a source; 0 dataset names repeat their source name.
- Views: `<source>_<dataset>` for all datasets except the 365 `mlb_api` ones, whose views start with `mlb_` (`mlb_schedule`). This is one deliberate exception (it is in the README since the first release and in user queries), now written down and tested.
- Lake `processed/`: every folder is a registered dataset (0 unknown). Chunk files are `part-<chunk>.parquet` for every source, and `compact-NNNN.parquet` after compaction; the chunk id carries the meaning (season, date range, game id, series ticker, capture date).
- Lake `raw/`: 6 folders that are not dataset names: `documents` (3 sources), Retrosheet `box_files` and `event_files` (raw inputs of several datasets), and `mlb_api/standings_postseason`, a leftover of an earlier endpoint list (19 files of 193 bytes: empty answers, 0 records). Left in place: deleting raw data needs the owner's word.
- README layout drawing lacked `inbox/`, `exports/`, `locks/` and `compact-NNNN.parquet`.
- Repository: `kalshi.txt` (a private key, not tracked by git) sits in the project folder; the two `dlt` spike scripts are cited by ADR 42 and a test, so they stay.

## What changes
`catalog layout` fails on a `processed/` folder no dataset owns (`UNKNOWN_FOLDER`); a test enforces the naming rules; the README states them and draws the full lake.
