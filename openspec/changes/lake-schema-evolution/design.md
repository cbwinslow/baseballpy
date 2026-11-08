# Design: lake-schema-evolution

## Decisions
- D1 Read under the registered schema (polars `schema=` with `missing_columns="insert"`, `extra_columns="raise"`). Rejected: `union_by_name` on every view (slower, hides the mix).
- D2 Rewrite old files once instead of tolerating them forever, so the lake returns to "one schema per dataset" that the strict views rely on (ADR 73) and the old values leave `_extras`.
- D3 Promotion uses `map_to_schema` (the ingest's own cast and quarantine) and polars `json_path_match` on the upstream key of each new column; keys are removed with DuckDB `json_merge_patch` (an emptied object becomes NULL).
- D4 Certification rule: after a rewrite the chunk's `schema_sha256` becomes the current fingerprint only if it equals the fingerprint of the file's old columns plus the spec's parser `revision`. Otherwise the chunk stays stale and the next ingest re-downloads it.
- D5 A file that cannot be migrated (unknown column, failed check) is left untouched and reported; nothing is dropped.
- D6 Web check: pybaseball and baseballr re-download on schema change and keep no history; polars documents `missing_columns`/`extra_columns` for exactly this case; DuckDB documents `union_by_name` as the slow general answer.

## Evidence
Filled in as built (see tasks).
