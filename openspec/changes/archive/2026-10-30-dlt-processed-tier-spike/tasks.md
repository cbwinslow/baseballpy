# Tasks: dlt-processed-tier-spike

- [x] 1. Measure
  - [x] 1.1 Ingest Lahman (27 tables) into a scratch lake with the current path; record seconds, files and bytes from the audit log
  - [x] 1.2 Write `scripts/dlt_processed_spike.py`: load the same typed tables through dlt (filesystem, Parquet, `replace`) into a second scratch lake
  - [x] 1.3 Compare layout, column names and types, row equality (hash of sorted rows), seconds, code size
  - [x] 1.4 Behaviour: add a column, interrupt and resume, repeat run, partitioned layout (`season=YYYY/`), what each path loses
- [x] 2. Decide
  - [x] 2.1 ADR 50 (adopt, adopt for some, or reject) with the numbers; plain-words recommendation; update `TOOLING.md`; archive the change
