# Design

- One place decides the name (`part_filename`); every source already wrote through `part_path`, so no source code changed. Manifest keys stay the full chunk id, so cache checks are unaffected.
- Rejected: renaming chunk ids inside every source (many edits, manifest keys change); keeping `manifest.json` and asking readers to filter (every user trips over it).
- Known edge: a table with its own `season` column plus the `season=YYYY` folder gives pandas/pyarrow two `season` fields; documented in DATA_WORKFLOW (use DuckDB or read files one by one).
- Existing lakes written with the old part names are not renamed: no real lake existed yet (B-09 not run). A lake with old names would hold the same chunk twice, so delete and re-ingest it.

## Evidence
- `tests/test_part_names.py` (13 tests): name rules, clash guard, DuckDB/polars/pandas/pyarrow read the same rows, legacy manifest rename.
