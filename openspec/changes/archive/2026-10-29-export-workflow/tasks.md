# Tasks: export-workflow

- [x] 1. Decide
  - [x] 1.1 Owner answers decisions A to D in design.md; record ADR 46
- [x] 2. Build (generic, registry-driven; tests first)
  - [x] 2.1 `exports/` tier in `LakeConfig` and the path rules
  - [x] 2.2 CSV sink with the `.schema.json` sidecar and an Arrow round trip
  - [x] 2.3 Typed `dlt` database sink: explicit column types from the Arrow schema, registry key as primary key, replace/append/merge
  - [x] 2.4 `export_dataset()` and the verify step (rows and schema read back) with audit events
  - [x] 2.5 `baseballpy export` command
- [x] 3. Tests
  - [x] 3.1 Round trips for Parquet, CSV, DuckDB and embedded PostgreSQL (dev dependency, skipped when absent)
- [x] 4. Chadwick as the model
  - [x] 4.1 Export all four Chadwick datasets to every target, compare, record the numbers
  - [x] 4.2 `docs/DATA_WORKFLOW.md` export section and a short "onboarding a source" checklist with the exceptions
- [x] 5. Close
  - [x] 5.1 Spec delta merged, ADR 46, change archived
