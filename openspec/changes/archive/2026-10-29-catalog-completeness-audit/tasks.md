# Tasks: Catalog Completeness Audit

- [x] 1. Library <!-- id: 1 -->
  - [x] 1.1 `baseballpy.audit` with `AuditFinding` and per-source auditors (MLB, Statcast, GitHub-tree sources) reusing the generators' probe functions
  - [x] 1.2 `unsupported` entries gain `verified_on` / `tried` metadata (endpoints.py, lb_catalog.py)
- [x] 2. CLI and CI <!-- id: 2 -->
  - [x] 2.1 `baseballpy catalog audit` (rich table, `--json`, exit codes)
  - [x] 2.2 Weekly audit job in `live.yml` (depends on hygiene 5.1) opening an issue on findings <!-- 2026-10-28: `live.yml` runs the audit with `continue-on-error`, then `gh issue create`/`gh issue comment` on one open issue titled by `AUDIT_ISSUE_TITLE`, then fails the job; `tests/test_workflows.py` parses the workflow and checks the step. NOT verified: a real run on GitHub (Actions not enabled by the owner yet) -->
- [x] 3. Sampling <!-- id: 3 -->
  - [x] 3.1 Multi-era, multi-player combo sampling in `gen_mlb_schemas.py`; record the finding sample per combo <!-- 2026-10-28 `SAMPLE_PEOPLE` (14 players incl. both-league and rookie), `SAMPLE_GAME_DAYS` (four dates, minor-league levels, first/middle/last games), per-sport endpoints over every `ref_sports`; each endpoint's request and row counts are in `docs/mlb_probe.json`; motivated by real-run schema drift, see `verify-optin-paths` -->
- [x] 4. Tests and records <!-- id: 4 -->
  - [x] 4.1 respx tests for each verdict kind
  - [x] 4.2 Write ADR 35 (promised by the proposal, absent from `docs/DECISIONS.md`), merge the `catalog-audit` spec delta into `openspec/specs/`, archive the change

## Status (2026-10-27)
Library, CLI, evidence metadata and tests are done (first run: see `catalog-audit-first-run-fixes`). Open: 2.2 weekly CI job (needs hygiene 5.1), 3.1 multi-era/multi-player combo sampling (see `mlb-parameterized-stat-types`), ADR 35 and spec merge when the change closes.
