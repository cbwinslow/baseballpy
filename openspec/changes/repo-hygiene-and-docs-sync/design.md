# Design: Repo Hygiene, Dependencies, CI, Docs Sync

## 1. License handling (G-1)
- Default path: GPL-3.0-or-later everywhere. Files to align: `CLAUDE.md` ("License Boundary" rewritten: "baseballpy is GPL-3.0-or-later; GPL dependencies may be imported directly; third-party non-GPL-compatible deps must stay optional"), `openspec/project.md`, `README.md` badge/section, `CITATION.cff` (`license: GPL-3.0-or-later`), `NOTICE` (add baseballpy's own notice and Retrosheet attribution text required by Retrosheet's terms: "The information used here was obtained free of charge from and is copyrighted by Retrosheet. Interested parties may contact Retrosheet at www.retrosheet.org."), `pyproject.toml` already GPL.
- Data attribution: add `docs/DATA_LICENSES.md` listing each source's terms (MLB/Statcast: MLBAM copyright notice and usage restrictions — personal/non-commercial research; Retrosheet: attribution notice above; Lahman: CC BY-SA 3.0; Chadwick Register: ODC-By 1.0 per upstream; verify wording from upstream repos and quote links, do not paraphrase legal terms). Surface in `baseballpy --version --licenses` and README.
- Fallback task list if the owner picks Apache-2.0: (a) move `chadwickpy` import behind `_chadwick_adapter.py` (already done in coverage change) and make `chadwickpy` an optional extra `retrosheet`; (b) re-verify no other GPL deps (`dlt` Apache-2.0, `duckdb` MIT, etc.); (c) change metadata; (d) write the ADR; (e) legal note that the `retrosheet` extra is GPL when installed.

## 2. Shared helpers
`core/coerce.py`:
```python
class CoercionError(ValueError): ...
def to_int(v, *, nulls=NULL_TOKENS) -> int | None      # raises CoercionError for non-null, non-parseable (NO silent None)
def to_float(v, ...); def to_bool(v, ...); def to_date(v, fmt)
NULL_TOKENS = frozenset({"", "NA", "N/A", "null", "None", "(null)", "<NA>", "NaN", "--"})
```
Callers wrap in `try/except CoercionError` and quarantine; nothing returns `None` for garbage anymore. Property tests assert: any str either parses or raises `CoercionError`, never another exception.
`core/lazy.py`: `lazy_singleton(factory)` -> callable with `.reset()` for tests; used by audit logger, config, default sources.

## 3. Lint/type policy
- `ruff` select adds `D1` (public docstrings; `tests` ignored), `S` (security; `S101` ignored in tests; SQL string-building flagged `S608` must carry `# noqa: S608  # identifiers validated by quote_ident`), `PLR0912/PLR0915` (complexity warnings as errors with documented per-file ignores only where table-driven code justifies).
- `mypy --strict` unchanged; every `# type: ignore` must have `[error-code]` and a trailing reason; CI greps for bare ignores.
- `tests`: `pytest -p no:randomly` default; `pytest-randomly` available via `-p randomly` in CI nightly.

## 4. CI (`.github/workflows/`)
- `ci.yml` (push, PR): `lint`, `types`, `test` (ubuntu+windows × py3.11/3.12/3.13; `uv sync --all-extras`; `uv run pytest -m "not live" --cov --cov-fail-under=85 --disable-socket --allow-unix-socket`), `docs` (`uv run baseballpy docs check`, `uv run mkdocs build --strict`), `build` (`uv build`; `uvx twine check dist/*`).
- `live.yml` (workflow_dispatch + weekly cron): `uv run pytest -m live -x --timeout=600` and `uv run python scripts/probe_endpoints.py --write docs/endpoint_probe.json`; uploads the probe JSON as an artifact and opens an issue if any previously-supported endpoint regresses (via `gh issue create`).
- Pre-commit: existing config extended with `ruff`, `ruff-format`, `mypy` (local hook), `check-yaml`, `end-of-file-fixer`, and a local hook rejecting `*.duckdb`/`*.part` files and bare `type: ignore`.

## 5. Docs system
- `mkdocs.yml` (material theme): nav = Home (README excerpt), Quickstart, CLI (generated), Architecture (DECISIONS, layout diagram), Sources (one page per source incl. generated column dictionaries), Endpoint Catalog, API Reference (mkdocstrings for `baseballpy.*` public modules), Data Licenses, Roadmap, Releasing.
- `docs/ARCHITECTURE.md`: layered diagram (sources → pipeline → stores → sinks/DB), data-lake tree, manifest/lock/quarantine/audit flows, extension guide ("add a new dataset in 6 steps": spec, schema, endpoint/doc rows, fixture, planner, test).
- `docs/RELEASING.md`: version bump, changelog, `uv build`, TestPyPI, tag; not executed here.
- `docs/CLI.md` generated from click (`baseballpy docs generate`).

## 6. AGENTS.md / CLAUDE.md rewrite outline
AGENTS.md sections (renumbered 1–12): 1 OpenSpec & docs; 2 Architecture/protocol boundaries; 3 Full data preservation (`_extras`, raw kept); 4 Baseball invariants (keys, eras, upserts); 5 HTTP/rate-limit contract (`HttpClient` only — direct `httpx` use outside `core/http.py` is a violation, enforced by a test grepping imports); 6 Streaming; 7 Audit/telemetry; 8 Errors/quarantine/no silent failure (+ `CoercionError` rule); 9 Atomic writes/manifests/layout; 10 Config; 11 Testing (Hypothesis, respx, socket guard, live markers, coverage gate); 12 Docs generation & catalog freshness. A new import-boundary test (`tests/test_architecture.py`) enforces: sinks don't import `httpx`; sources don't import `duckdb`/`psycopg2`; only `core/http.py` imports `httpx`; only `sources/retrosheet/_chadwick_adapter.py` imports `chadwickpy`.
CLAUDE.md: commands (add `uv run pytest -m "not live"`, `baseballpy docs check`, `baseballpy doctor`), architecture summary, layout, license, "where to add a dataset".

## 7. Test-suite changes (G-9)
- `tests/test_architecture.py` (import boundaries; no bare `except`/`except Exception: pass` via `ast` walk of `src/`; no `safe=False`; no `assert` outside tests).
- `tests/test_properties.py` (Hypothesis for `coerce`, flatten, normalizers).
- `tests/test_cli.py` (CliRunner), `tests/test_concurrency.py` (manifest/atomic), `tests/test_protocol_contract.py` (pipeline change).
- Markers in `pyproject.toml`: `live`, `smoke_live`, `slow`.
- `tests/test_smoke.py`: keep mocked multi-season smoke in CI; add `tests/live/test_smoke_live.py` (manual).

## 8. Packaging
`py.typed`; `[tool.hatch.build]` includes it; `CHANGELOG.md` entries for 0.2.0 summarizing all changes; `project.urls` check; `classifiers` accurate (add `Operating System :: Microsoft Windows`/`POSIX`); `uv.lock` regenerated.
