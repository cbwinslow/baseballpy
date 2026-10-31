# Progress Report: mlb-schema-drift-regeneration (B-190)

Started: 2026-10-31 (after owner's pause on 2026-10-30, HANDOFF_2026-10-30.md).
Agent: Claude (this session). Previous agent: opencode (ran out of tokens).
Path chosen: Resume B-190 with current design (NOT dlt; ADR 50 stands).

## Reuse check (before any edit)

From docs/agents/TOOLING.md:
- HTTP/network: `core/http.py::HttpClient` (httpx + tenacity + aiolimiter). The generator uses `get_json()` which uses this.
- Typed interchange: `pyarrow`. The generator writes Arrow schemas; fixtures are Arrow/JSON.
- Large JSON: `msgspec`. Not needed for generator fixtures (small JSON payloads).
- Tests: `pytest`, `respx`, `hypothesis`. The anti-drift test uses `pytest`.
- No new runtime dependency needed. No custom code needed for the generator fix (it uses existing `hydrate_request_params()` and `stats_payload()` from `generic.py`).

Evidence for custom code: none needed — the fix is using the existing `hydrate_sample()` and `hydrate_request_params()` helpers that the uncommitted code already introduces.

## What was found when starting

- Uncommitted changes: `scripts/gen_mlb_schemas.py`, `src/baseballpy/sources/mlb_api/generic.py`.
- New folder: `openspec/changes/mlb-schema-drift-regeneration/` (proposal.md, design.md, tasks.md, specs/mlb-api-ingestion/spec.md).
- No commits made by opencode (git status shows uncommitted only; 4 commits ahead of origin/main are from earlier work).
- Gates at last commit (HANDOFF_2026-10-30.md): all green (pytest 1,176 passed, ruff, ruff format, mypy --strict, docs generate --check, openspec validate --specs 16 passed).

## Slice 1: Commit existing task 1.1 code (done by opencode)

Status: IN PROGRESS.
Files: `scripts/gen_mlb_schemas.py`, `src/baseballpy/sources/mlb_api/generic.py`.
Task: 1.1 of `tasks.md` (`hydrate_request_params()` public helper; generator maps direct refusal to hydrate sample).
Evidence needed: `git diff`, `ruff check`, `mypy --strict src`, `pytest` (at least the generator-related tests).
Not verified: the live generator run (needs network; 406 is known; will be verified in slice 2).

## Next slices (planned order)

1. Slice 1: Commit 1.1 (this message).
2. Slice 2: Regenerate schemas (task 1.2) — run generator with `--only stats_stat_splits_* --skip-combos`.
3. Slice 3: Anti-drift test (task 1.3) — `tests/test_mlb_coverage.py::test_every_fixture_key_has_a_typed_column`.
4. Slice 4: Docs, spec merge, archive (task 1.4) — `docs/sources/mlb_api.md`, `tasks.md` ticked, archive folder, `BACKLOG.md` updated.

Every slice will have: command output pasted, gates run, "not verified" said plainly for anything not actually executed.
