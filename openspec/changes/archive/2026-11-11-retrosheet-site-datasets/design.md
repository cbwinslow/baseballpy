# Design: retrosheet-site-datasets

## 1. Evidence
Real files (2026-11-11): `tran.txt` 101,594 rows, 16 fields, no header row (the layout is in `readme.txt`);
managers0 859, umpires0 1,762, coaches0 12,501, ballparks0 521, teams0 178 rows. Findings that shaped the schema:
transaction dates carry partial precision (`19520000`: month and day unknown), so `primary_date` and `secondary_date`
stay text; `transaction_id` is shared by every player of a trade, so it is not a key; the file has 2 exact duplicate
rows, kept (nothing is dropped).

## 2. Prior art and reuse check
Reused: `HttpClient`, `RawStore`, `ProcessedStore.put_stream`, `RetrosheetFlatParser` (strict schema, quarantine),
`Fingerprint(INPUT_SET, sha256 of the zip)` for freshness, the registry, `schema_from_columns`, audit logger. The only
new logic is the declarative `SITE_DATASETS` table and one generic `ingest_site`.

## 3. Decisions
- The `site` unit is resolved from the declarative `SITE_DATASETS` table (no name prefix); every dataset is `opt_in`.
- Zips are never re-fetched when stored; the processed chunk is rebuilt only when the zip's sha256 changes.
- A fetch that stops, fails or is blocked raises; no partial result is reported as done.

## 4. Tests
`tests/test_retrosheet_site_datasets.py`: registry entries opt-in and strict; a default plan has no site job; zips
become typed tables with no request; end-to-end write then skip; unknown names refused; missing zip reported.
