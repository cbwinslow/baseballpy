# Tasks: retrosheet-parallel-parse

- [x] 1.1 Default `parse_workers` from the CPU count (cap 32); tests run with in-process parsing unless they ask for a pool.
- [x] 1.2 One persistent shared process pool with a bounded in-flight window and ordered results; tests for order, bound, failure and reuse.
- [x] 1.3 Season build steps together: measured, not needed, not built (see design.md).
- [x] 1.4 Measure a full season and a multi-season run before and after; compare every table with the single-core run.
- [x] 1.5 Spec, docs, ADR 61, gates, archive.
