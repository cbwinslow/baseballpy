# Tasks: auto-concurrency-and-intra-source-parallelism

- [x] 1.1 Centralized `resolve_concurrency` utility in `src/baseballpy/core/concurrency.py`
- [x] 1.2 Update `run_jobs` in `src/baseballpy/ingest/runner.py` to accept `concurrency: int | str | None = None` and auto-resolve
- [x] 1.3 Update `baseballpy ingest` CLI option `--concurrency` in `src/baseballpy/cli_ingest.py` to default to auto-resolution
- [x] 1.4 Unit and property tests for auto-concurrency resolution and runner execution in `tests/test_auto_concurrency.py`
- [x] 1.5 Update docs (`docs/CLI.md` via `baseballpy docs generate`), update OpenSpec specs, and quality gates check
