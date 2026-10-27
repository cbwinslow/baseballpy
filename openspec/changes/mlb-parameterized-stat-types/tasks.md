# Tasks: Parameterized MLB Stat Types

- [ ] 1. Discovery <!-- id: 1 -->
  - [ ] 1.1 Extend `gen_mlb_schemas.py` with the parameter-discovery protocol and a per-stat-type `tried` log
  - [ ] 1.2 Run it; record which stat types gain combinations and which stay empty
- [ ] 2. Registry <!-- id: 2 -->
  - [ ] 2.1 List-valued fan-out parameters (`sit_codes`, `metrics`) in `endpoints.py`/`requests_for` with injected columns
  - [ ] 2.2 Register productive combinations; `unsupported` + `verified_on` + `tried` for the rest
- [ ] 3. Tests and docs <!-- id: 3 -->
  - [ ] 3.1 Fan-out and key tests, fixtures for the new datasets
  - [ ] 3.2 Generated docs; audit shows no NO_DATA stat types without an `unsupported` entry
- [ ] 4. Verification <!-- id: 4 -->
  - [ ] 4.1 Gates; live ingest of one 2024 sample per new family
