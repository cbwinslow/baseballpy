# Design

- `_ints` keeps a non-integer as text and `safe_array` quarantines it; `_info_value` quarantines bad flags and numbers through `record_bad_value`.
- Rejected: skipping the bad line (loses the other cells of the row); failing the season (loses all rows of the season).

## Evidence
- Before: `ingest retrosheet --seasons all` completed 135 and failed 22. After: the same 22 seasons re-run completed 22 of 22; 25 quarantine files hold the unreadable cells; `catalog audit` reports no findings; 15,844,833 events over 118 seasons (1908-2025) and 223,194 box games in the DuckDB views.
- Not verified: that every quarantined cell was a true data error in the provider file (the raw files are kept in `raw/retrosheet/`).
