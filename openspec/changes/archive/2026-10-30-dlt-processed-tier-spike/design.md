# Design: dlt-processed-tier-spike

## Method
Same input for both paths: the typed Arrow tables the Lahman normalizer produces (27 tables), so only the writer differs. Scratch homes are created under the user's profile and deleted at the end. Numbers come from `logs/audit.jsonl`, `time.perf_counter` in the script, and file listings.

## Known before the spike (2026-10-30, `scratchpad/dlt_schema_spike.py`)
- dlt filesystem destination, `append`: a column added later is written in a new file that has the column; old files are left as they were. `replace`: old files are removed and new ones written with the new columns. The schema version moved 2, 3, 4 across the three loads. DuckDB reads mixed files with `union_by_name`.
- Earlier spike (`dlt-pipeline-core`): filesystem destination falls back from `merge` to `append`; integers widen (`int32` to `BIGINT`); no raw bytes, quarantine or rate limiting.
- Sources: https://dlthub.com/docs/general-usage/schema-evolution, https://dlthub.com/blog/how-dlt-uses-apache-arrow

## Results (2026-10-30, dlt 1.31.0, `scripts/dlt_processed_spike.py`; Lahman, 27 tables, 706,466 rows; this PC)

Input: the typed Arrow tables the current path produced. Only the writer differs.

| Question | Current path (`ProcessedStore`) | dlt (filesystem, Parquet, `replace`) |
|---|---|---|
| Write seconds, 27 tables | 1.43-1.46 | 1.98-2.68 (about 40% slower) |
| Bytes | 8.58 MB including manifests | 10.70 MB of data plus 10.91 MB of dlt pipeline state in the pipelines folder (cause of the larger data not checked) |
| File layout | `processed/lahman/<Table>/part-data.parquet` plus `manifest.json` | `lake/lahman/<Table>/<load_id>.<file_id>.parquet` plus `_dlt_loads`, `_dlt_version`, `_dlt_pipeline_state` folders |
| Names | provider names kept | **default naming rewrote all 27 table names and columns** (`playerID` to `player_id`); `SCHEMA__NAMING=direct` keeps them, with a warning that table names containing `/` are unsafe in the default layout |
| Columns, types, rows (direct naming) | reference | 27/27 same column names, 27/27 same types, 27/27 same sorted rows; no dlt-added columns for Arrow input |
| Repeat run | skipped (cache hit, fingerprints) | rewrites all 27 tables (2.07 s); dlt has no currency check of its own for this |
| Column added | stale chunk rebuilt by the schema digest (ADR 49, test) | `replace` writes a new file with the new column, schema version bumps; it does not decide whether a reload is needed |
| Crash during a load | atomic part file, old part kept | the earlier good file survived a simulated crash (1 file before, 1 after) |
| Rebuild one season of a season-partitioned dataset | one `part-<chunk>.parquet` per season, replaced alone | **not expressible**: with `layout=.../season={season}/...` and `extra_placeholders`, `replace` of 2015 then 2016 leaves only `season=2016`; `append` twice leaves two 2015 files (duplicates) |
| `partition` column hint on plain Parquet | n/a | silently ignored (one file) |
| Fingerprints, quarantine, footer row-count check, raw tier, our file names | provided | not provided; would need custom code around dlt, which is what we are trying to remove |

Code size is not comparable: the dlt writer is about 12 lines in the script, but it replaces only `ProcessedStore.put` (about 40 lines) while the supporting code (atomic writes 299 lines, manifests, fingerprints, currency checks, quarantine) would stay.

## Reading
dlt works for what it is built for: a table that it owns end to end, in a database or a folder, with schema versions and loads tracked. For our processed tier it fails the requirement that matters most for the big sources: rebuilding one season without touching the others (Retrosheet has 150+ season chunks per dataset, Statcast has per-window chunks). Making it work needs one dlt table per season (changes view names and the registry) or our own deleting of old files, which is the custom code we wanted to avoid. It also changes names unless told otherwise and would add a second place where state lives.

## Decision path
ADR 50: reject dlt as the writer of the processed tier; keep ADR 44 (dlt delivers to databases and warehouses) and ADR 49 (our schema digest). Re-open if dlt's filesystem destination gains per-partition replace (watch dlt release notes) or for a source with one unpartitioned table where nothing is lost.
