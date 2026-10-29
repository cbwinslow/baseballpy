# Tasks: data-workflow-standard

- [x] 1. Decide
  - [x] 1.1 Owner picks the update-check rule (Decision A) and the dlt role (Decision B); record both as ADRs
- [ ] 2. Shared mechanism
  - [ ] 2.1 Manifest records an upstream fingerprint per raw file (git blob SHA, ETag or Last-Modified, content sha256); `RawStore.put` takes it
  - [ ] 2.2 One `is_current()` function used by every source, replacing the per-source checks (moved source by source inside the source tracks)
  - [ ] 2.3 `baseballpy cache check`: verify local sha256 (uses `RawStore.verify`) and report files whose upstream fingerprint changed
- [ ] 3. Document
  - [ ] 3.1 `docs/DATA_WORKFLOW.md`: the five steps, the cache folders and overrides, and how to read or export the data (Arrow, Polars, DuckDB, PostgreSQL, files)
