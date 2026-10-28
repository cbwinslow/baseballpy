# Proposal: Retrosheet CSV bundles

## Why
Retrosheet publishes its whole corpus as seven master CSV files (plus a simplified set and per-season files for `plays`) on its downloads pages. Source: https://www.retrosheet.org/downloads/csvoverview.html and https://www.retrosheet.org/downloads/csvdownloads.html (found 2026-10-28; the pages describe games 1898-2025, 224,877 games, box scores for 221,443 and event files for 205,886, and a `stattype` column where `value` is the main estimate and `lower`/`upper` flag uncertain rows).

baseballpy ingests Retrosheet from the pinned `chadwickbureau/retrosheet` git tree (event/box files parsed with Chadwick, game logs, schedules, rosters, reference tables, discrepancies, box accounts). Nothing in `sources/retrosheet/` reads the CSV bundles (verified by search for `csv`/`.zip` handling in the package, 2026-10-28), so by the "never leave upstream data behind" rule they are either ingested or registered `unsupported` with evidence.

## What
Register the bundle files as datasets and ingest them from retrosheet.org through the existing downloader/`HttpClient`, as typed Parquet like every other dataset. The retrosheet.org ingest path is not changed and the git-tree sources stay as they are; this adds datasets beside them.

## Open facts (must be obtained before design)
- Exact file names, columns and types: `csvcontents.html` / the overview page are not reachable from the development machine, so no schema may be written yet (types come from data, never from guessing).
- Download URLs and whether per-season `plays` files exist for every season.
- Licence and attribution wording on the downloads pages (add to `docs/DATA_LICENSES.md`).

## Out of scope
Changing any existing Retrosheet dataset, mirroring Retrosheet's files from any location other than retrosheet.org (or the git tree the repo already pins).

## Decision needed from the owner
Approve implementation. It depends on reaching retrosheet.org (the generator that probes the files and widens types has to download them once); the code itself must work for any user who can reach it.
