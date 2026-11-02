# Tasks: v1-coverage-and-smart-concurrency

- [x] 1.1 Author OpenSpec change proposal, design, tasks, and spec deltas for `v1-coverage-and-smart-concurrency`, and update `docs/agents/BACKLOG.md`.
- [x] 1.2 Implement smart bounded concurrency for MLB API player hydrate batches and multi-endpoint extraction in `src/baseballpy/sources/mlb_api/generic.py` and `api.py`.
- [x] 1.3 Verify and optimize concurrency across Statcast weekly chunks and Retrosheet multi-season ingestion.
- [x] 1.4 Implement `baseballpy catalog coverage` command (expected vs. held games with remediation commands) in `src/baseballpy/cli_catalog.py` and `src/baseballpy/cli.py`.
- [ ] 1.5 Add automated tests for concurrency and coverage, verify all quality gates (`pytest`, `ruff`, `mypy`, `openspec validate --specs`), update documentation, and archive change.
