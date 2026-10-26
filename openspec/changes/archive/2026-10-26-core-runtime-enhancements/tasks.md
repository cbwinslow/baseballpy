# Tasks: Core Runtime Enhancements

- [x] Install dependencies: `narwhals` and `msgspec`
- [x] Update `docs/DECISIONS.md` with ADRs 11 to 14
- [x] Update `AGENTS.md` with OpenSpec and minimal splash damage rules
- [x] Author system specifications: `audit-and-benchmarking`, `caching-and-invalidation`
- [ ] Implement `baseballpy.core.config`: source-partitioned cache paths & env overrides
- [ ] Implement `baseballpy.core.audit`: `AuditEvent`, `AuditLogger`, benchmark context manager
- [ ] Implement `baseballpy audit` CLI commands (`summary`, `tail`, `stats`)
- [ ] Write tests for config, audit logging, and CLI in `tests/test_audit.py` and `tests/test_config.py`
- [ ] Verify test suite with `uv run pytest`, `ruff`, and `mypy --strict`
