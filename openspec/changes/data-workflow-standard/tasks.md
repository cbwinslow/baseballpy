# Tasks: data-workflow-standard

- [x] 1. Decide
  - [x] 1.1 Owner picks the update-check rule (Decision A) and the dlt role (Decision B); record both as ADRs
- [ ] 2. Shared mechanism
  - [x] 2.1 Manifest records an upstream fingerprint per raw file (git blob SHA, ETag or Last-Modified, content sha256); `RawStore.put` takes it
  - [x] 2.2 One `is_current()` function exists and Chadwick uses it (the other sources move over in 2.5 to 2.8)
  - [x] 2.3 `baseballpy cache check`: verify local sha256 (uses `RawStore.verify`) and report files whose upstream fingerprint changed
  - [x] 2.4 Ingest jobs report that they skipped work (audit `cache_hit`); today a cached rerun of `ingest chadwick` logs `cache_hit=False` (found in chadwick-source-review S6)
  - [x] 2.5 Lahman records fingerprints and decides with `is_current()` (inside lahman-source-review)
  - [x] 2.6 Retrosheet records fingerprints and decides with `is_current()` (inside the Retrosheet review)
  - [x] 2.7 Statcast records fingerprints and decides with `is_current()` (inside the Statcast review)
  - [ ] 2.8 MLB API records fingerprints and decides with `is_current()` (inside the MLB API review)
  - [x] 2.9 `cache check --upstream` says so when nothing could be compared (no file has a git fingerprint) instead of "add --upstream" (found in lahman-source-review 1.4)
- [x] 3. Document
  - [x] 3.1 `docs/DATA_WORKFLOW.md`: the five steps, the cache folders and overrides, and how to read or export the data (Arrow, Polars, DuckDB, PostgreSQL, files)
