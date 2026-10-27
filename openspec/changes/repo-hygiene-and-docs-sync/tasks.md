# Tasks: Repo Hygiene, Dependencies, CI, Docs Sync

Can start immediately for items 1-3 and 5 (independent of other changes); items 4, 6, 7 finish last.

- [x] 1. License alignment (G-1) <!-- id: 1 -->
  - [x] 1.1 Update `CLAUDE.md`, `openspec/project.md`, README, `CITATION.cff` to GPL-3.0-or-later; add baseballpy + Retrosheet notices to `NOTICE`
  - [x] 1.2 Write `docs/DATA_LICENSES.md` quoting each upstream's terms with links (read from upstream repos/pages; do not paraphrase legal text); add `--licenses` flag to `--version`
  - [x] 1.3 (n/a: GPL-3.0-or-later retained, no Apache fallback needed)
  - [x] 1.4 ADR 26
- [x] 2. Shared helpers and cleanup (G-4, G-5) <!-- id: 2 -->
  - [x] 2.1 `core/coerce.py` (`CoercionError`, `to_int/to_float/to_bool/to_date`); replace the four `_safe_*` copies; callers quarantine on `CoercionError`
  - [x] 2.2 `core/lazy.py` `lazy_singleton`
  - [x] 2.3 Remove `assert` from `PolarsSink`; hoist inline imports; add codes+reasons to every `# type: ignore`
  - [x] 2.4 Docstrings on every public class/function/module (ruff `D1` clean)
  - [x] 2.5 Collapse sync/async twins in Lahman/Chadwick extractors onto `HttpClient`
- [x] 3. Dependencies (G-7) <!-- id: 3 -->
  - [x] 3.1 Apply the decision table: remove `fsspec`, `websockets` from defaults; split `dlt` extras (`dlt-postgres`, `dlt-snowflake`, `dlt-bigquery`, `dlt-motherduck`); verify `retrosheetpy`/`chadwickpy` extras match actual imports
  - [x] 3.2 Add dev deps `pytest-socket`, `pytest-timeout`; configure `--disable-socket` default with `live` marker opt-out
  - [x] 3.3 Use `narwhals` for `to_dataframe(backend=...)`; add `baseballpy.scan(dataset)` Polars `scan_parquet` helper; use `pq.ParquetWriter`/`write_to_dataset` in stores
  - [x] 3.4 `uv lock`; `uv sync --all-extras`; confirm install of core-only works (`uv sync` with no extras) and CLI starts
- [ ] 4. Lint/type/test policy (G-5, G-9) <!-- id: 4 -->
  - [ ] 4.1 Extend ruff config (`D1`, `S`, `PLR0912`, `PLR0915`) and fix findings or add justified per-file ignores
  - [ ] 4.2 `tests/test_architecture.py` (import boundaries, AST scan for bare/swallowing excepts, `safe=False`, `assert` in src)
  - [ ] 4.3 `tests/test_properties.py` (Hypothesis), `tests/test_cli.py`, `tests/test_concurrency.py`
  - [ ] 4.4 Register markers `live`, `smoke_live`, `slow`; split smoke tests into mocked (CI) and `tests/live/` (manual)
  - [ ] 4.5 Coverage gate 85% (`--cov-fail-under=85`); raise if already higher
- [ ] 5. CI and packaging (G-6, G-8) <!-- id: 5 -->
  - [ ] 5.1 `.github/workflows/ci.yml` and `live.yml` per design §4; update `.pre-commit-config.yaml`
  - [ ] 5.2 `py.typed`, hatch include, `CHANGELOG.md`, version `0.2.0`, classifiers
  - [ ] 5.3 `mkdocs.yml`, `docs/index.md`, `docs/ARCHITECTURE.md`, `docs/RELEASING.md`; `uv run mkdocs build --strict` passes
- [ ] 6. Documentation sync (G-2, G-3) <!-- id: 6 -->
  - [ ] 6.1 Rewrite `AGENTS.md` (renumber, new mandates) and `CLAUDE.md`
  - [ ] 6.2 Update README, QUICKSTART, ROADMAP to actual state (layout v2, CLI, coverage, counts generated not hand-typed)
  - [ ] 6.3 Verify and update every `openspec/specs/*/spec.md` against code after other changes land; remove claims the code does not satisfy
  - [ ] 6.4 Merge all change spec deltas into `openspec/specs/`, then move changes to `openspec/changes/archive/<date>-<name>/` with tasks checked
- [ ] 7. Verification <!-- id: 7 -->
  - [ ] 7.1 `uv run pytest -m "not live"`, `uvx ruff check .`, `uvx ruff format --check .`, `uvx mypy --strict src`, `uv run mkdocs build --strict`, `uv build`
  - [ ] 7.2 Manual: fresh clone -> `uv sync` -> `baseballpy doctor` -> `baseballpy ingest lahman --seasons all` works on a clean machine/home
  - [ ] 7.3 Manual: grep docs for stale numbers ("94", "11 leaderboards", "27 tables strongly typed") — all must be generated or removed
