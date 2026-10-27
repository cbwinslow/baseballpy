# Tasks: Parameterized MLB Stat Types

- [x] 1. Discovery <!-- id: 1 -->
  - [x] 1.1 Extend `gen_mlb_schemas.py` with the parameter-discovery protocol and a per-stat-type `tried` log
  - [x] 1.2 Run it; record which stat types gain combinations and which stay empty
- [x] 2. Registry <!-- id: 2 -->
  - [x] 2.1 List-valued fan-out parameters (`sit_codes`, `metrics`) in `endpoints.py`/`requests_for` with injected columns
  - [x] 2.2 Register productive combinations; `unsupported` + `verified_on` + `tried` for the rest
- [x] 3. Tests and docs <!-- id: 3 -->
  - [x] 3.1 Fan-out and key tests, fixtures for the new datasets
  - [x] 3.2 Generated docs; audit shows no NO_DATA stat types without an `unsupported` entry
- [x] 4. Verification <!-- id: 4 -->
  - [x] 4.1 Gates; live ingest of one 2024 sample per new family
