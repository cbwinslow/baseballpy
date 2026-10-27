# Tasks: Catalog Completeness Audit

- [ ] 1. Library <!-- id: 1 -->
  - [ ] 1.1 `baseballpy.audit` with `AuditFinding` and per-source auditors (MLB, Statcast, GitHub-tree sources) reusing the generators' probe functions
  - [ ] 1.2 `unsupported` entries gain `verified_on` / `tried` metadata (endpoints.py, lb_catalog.py)
- [ ] 2. CLI and CI <!-- id: 2 -->
  - [ ] 2.1 `baseballpy catalog audit` (rich table, `--json`, exit codes)
  - [ ] 2.2 Weekly audit job in `live.yml` (depends on hygiene 5.1) opening an issue on findings
- [ ] 3. Sampling <!-- id: 3 -->
  - [ ] 3.1 Multi-era, multi-player combo sampling in `gen_mlb_schemas.py`; record the finding sample per combo
- [ ] 4. Tests and records <!-- id: 4 -->
  - [ ] 4.1 respx tests for each verdict kind; ADR 35; spec merge
