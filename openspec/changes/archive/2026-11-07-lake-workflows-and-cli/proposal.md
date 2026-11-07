# Lake workflows and CLI

## Why
The owner wants the download and ingest workflows to just work and the command line to be easy and complete. A review on 2026-11-07 found: no single command to see the lake (`catalog status` needed more than 110 seconds because it opened every Parquet footer of 480 datasets), no one-command way to bring the lake up to date (a plan file had to be written by hand and none shipped), season lists that went stale (`2008-2026` typed by hand), blank cells and `NaN` text quarantined as if they were errors (26 quarantine files, for example Retrosheet `box_starters.position` and MLB `leverage_index`), a legacy `statcast` command that wrote `baseball.duckdb` into whatever folder it was run from, and a profiler output file committed in the repository root.

## What changes
1. `baseballpy status`: one fast screen per source (datasets, rows, seasons, newest, gaps, disk, what is downloading, quarantine and leftover files).
2. `catalog status` reads manifests (seconds); `--verify` opens every file.
3. Season expressions accept `current` (alone, in a list or as a range end).
4. Built-in plans `daily` and `full`; `backfill` takes a file or a plan name; `update` runs `daily`.
5. A blank cell in a typed column is NULL and `NaN`/`Infinity` text in a float column is that float; neither is quarantined.
6. The legacy `statcast` command writes under the lake's `exports/` by default; `prof.out` leaves the repository.
