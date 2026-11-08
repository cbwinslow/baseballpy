# Tasks

- [x] 1.1 `scan_dataset` (polars schema, missing columns inserted, unknown refused) used by `read`
- [x] 1.2 `core/evolve.py`: `promote_extras`, `migrate_dataset`, certification rule
- [x] 1.3 `compact` migrates first; layout message; `db sync` warning
- [x] 1.4 tests/test_schema_evolution.py (10 tests)
- [ ] 1.5 run `baseballpy compact` on the real lake (no ingest running); `catalog layout` has no MIXED_SCHEMA; `read("award_recipients")` returns slugs for all rows
- [ ] 1.6 gates, merge spec delta, archive
