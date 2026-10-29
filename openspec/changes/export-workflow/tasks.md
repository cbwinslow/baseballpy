# Tasks: export-workflow

- [ ] 1. Decide
  - [ ] 1.1 Owner answers decisions A to D in design.md; record ADR 46
- [ ] 2. Build (generic, registry-driven; tests first)
  - [ ] 2.1 `exports/` tier in `LakeConfig` and the path rules
  - [ ] 2.2 CSV sink with the `.schema.json` sidecar and an Arrow round trip
  - [ ] 2.3 Typed `dlt` database sink: explicit column types from the Arrow schema, registry key as primary key, replace/append/merge
  - [ ] 2.4 `export_dataset()` and the verify step (rows and schema read back) with audit events
  - [ ] 2.5 `baseballpy export` command
- [ ] 3. Tests
  - [ ] 3.1 Round trips for Parquet, CSV, DuckDB and embedded PostgreSQL (dev dependency, skipped when absent)
- [ ] 4. Chadwick as the model
  - [ ] 4.1 Export all four Chadwick datasets to every target, compare, record the numbers
  - [ ] 4.2 `docs/DATA_WORKFLOW.md` export section and a short "onboarding a source" checklist with the exceptions
- [ ] 5. Close
  - [ ] 5.1 Spec delta merged, ADR 46, change archived
