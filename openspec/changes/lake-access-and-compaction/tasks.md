# Tasks
- [x] 1.1 views without `union_by_name`; a test that all parts of a dataset share one schema; timing recorded
- [x] 1.2 `baseballpy.read` and `baseballpy.sql` with tests and quickstart recipes (Statcast 2008 to 2026, join, group, sum, filter)
- [x] 2.1 `compact` command with before and after equality checks and tests
- [x] 2.2 compressed raw files and a conversion command, audit that every raw read still works
- [ ] 2.3 layout checks: files per dataset and season, row group size, schema equality, in `catalog audit`
- [ ] 3.1 run compaction and conversion on the lake after the downloads, record sizes and query times
- [ ] 3.2 spec, ADR, docs, gates, archive
- [x] 1.3 manifests are parsed only when the file changed (found when three MLB seasons failed with MemoryError)
