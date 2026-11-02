# Tasks: v1-ergonomics-and-e2e-verification

- [x] 1.1 Author OpenSpec proposal, design, tasks, and spec deltas for `v1-ergonomics-and-e2e-verification`, and update `docs/agents/BACKLOG.md`.

- [x] 1.2 Implement `--sync-db / --no-sync-db` on `baseballpy ingest` to automatically refresh DuckDB views after successful ingestion.

- [x] 1.3 Implement `--fix` flag on `baseballpy catalog coverage` to auto-remediate missing entities.

- [x] 1.4 Perform live end-to-end test on 2024 MLB data (ingest, DuckDB SQL query, coverage check, caching verification).

- [ ] 1.5 Verify all quality gates (`pytest`, `ruff`, `mypy`, `openspec validate --specs`), update documentation, and archive change.
