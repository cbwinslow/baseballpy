# Change Proposal: Repo Hygiene, Dependency Review, CI, and Documentation Sync

## Context & Motivation
Review findings that are neither bugs in ingestion nor new features, but make the repo inconsistent,
duplicated, or under-documented (IDs `G-n`). This change also performs the dependency review requested
("are we using the dependencies to the fullest; should we add/remove anything").

## Findings Fixed
| ID | Finding |
|----|---------|
| G-1 | **License contradiction:** `CLAUDE.md` says Apache-2.0; `pyproject.toml`, `LICENSE`, `NOTICE` say GPL-3.0-or-later; `chadwickpy` (GPL) is a core dependency and is imported unconditionally in Retrosheet parsers. |
| G-2 | `AGENTS.md` has two "§3" sections and does not mention the HttpClient, layout, `_extras`, quarantine replay, or CLI mandates introduced by the other changes. |
| G-3 | Docs drift: README claims "all schemas strongly typed" and "94+ attributes"; specs say "94 fields"/"11 leaderboards"/HTTP2 AsyncClient for MLB (all inaccurate before these changes); ROADMAP says Lahman 1871–2024; QUICKSTART uses v1 paths. |
| G-4 | Duplicated code: sync/async twins in Lahman and Chadwick extractors; `_safe_int/_safe_float/_safe_bool` copied in 4 modules; per-endpoint copy-paste in MLB extractor; 7× view blocks in `database.py` (fixed in restructure); `track`/`async_track` bodies (fixed in harden). |
| G-5 | Style/robustness: `assert` for type narrowing in `PolarsSink`; function-local `import concurrent.futures`; `# type: ignore` without codes; inconsistent module docstring style; undocumented public classes/functions (models, helper functions) violating AGENTS §1.3. |
| G-6 | No CI (`.github/workflows` absent); no coverage gate; unit tests can accidentally hit the network (no socket guard); live tests not separated. |
| G-7 | Dependency usage gaps (below). |
| G-8 | Packaging: no `py.typed` marker despite `Typing :: Typed` classifier; no `CHANGELOG.md`; docs group declares mkdocs but no `mkdocs.yml`; version still 0.1.0. |
| G-9 | Tests: no Hypothesis (AGENTS §9.5), no signature-level protocol tests, no CLI tests, no concurrency tests, smoke test not documented as manual vs CI. |

## Dependency Review (G-7) — decisions
| Dependency | Current use | Decision |
|------------|-------------|----------|
| `httpx[http2]` | Per-call sync clients; HTTP/2 unused | Used fully via `HttpClient` (pooling, HTTP/2, limits). |
| `tenacity` | Hand-rolled decorators in 3 modules | Centralized in `HttpClient`; honor `Retry-After`. |
| `aiolimiter` | Created, mostly unused | Used for per-host buckets in `HttpClient`. |
| `pydantic-settings` | Config classes defined, mostly unused | Fully wired (`LakeConfig`, `PipelineConfig`); settings exposed in `doctor`. |
| `msgspec` | Audit events; `mlb_api/models.py` dead | Use for `LiveEvent` and JSON decoding of large MLB payloads; delete dead models. |
| `pyarrow` | Core | Use `pq.ParquetWriter` row-group streaming, `pq.write_to_dataset` for partitions, `RecordBatchReader` end-to-end. |
| `duckdb` | Append-only sink, views | Add upsert, `COPY ... TO ... (PARTITION_BY)`, `read_parquet` views, `BY NAME` inserts. |
| `polars` | Arrow→DataFrame handoff | Keep; add `scan_parquet` helpers (`baseballpy.scan(dataset)`), lazy by default. |
| `narwhals` | Register only | Use in public helper return types (`to_dataframe(backend="polars"|"pandas"|"pyarrow")`) so pandas stays optional. |
| `dlt[duckdb,postgres,snowflake]` | Thin pass-through | Add merge dispositions with `primary_key=spec.keys`, destination selection, schema-contract `evolve`; move `postgres`/`snowflake` extras to optional `dlt-postgres`, `dlt-snowflake`, `dlt-bigquery`, `dlt-motherduck` extras (core install lighter). |
| `rich`, `click` | Audit CLI | Progress bars, tables, `--json`; keep. |
| `fsspec` | Unused | Remove from core deps; add optional `remote` extra (`fsspec`, `s3fs`, `gcsfs`) only if remote lake is built later (documented in ROADMAP). |
| `chadwickpy` | Core dep + unconditional import | Keep core only if the GPL decision (G-1) keeps GPL; isolate in `_chadwick_adapter.py` regardless. |
| `retrosheetpy` | Optional extra but unused in code | Keep as optional extra only if actually imported; otherwise remove from extras. |
| `pandas` | Optional | Keep optional. |
| `websockets` | Extra declared | Remove unless the streamer adopts WebSockets (not planned); keep ROADMAP note. |
| Dev: `hypothesis`, `respx`, `pytest-cov` | `hypothesis` unused | Use hypothesis; enforce coverage gate. |
| Add dev: `pytest-socket` | — | Block real network in unit tests; allow with `--force-enable-socket`/`live` marker. |
| Add dev: `pytest-timeout`, `pytest-randomly` (optional) | — | Hang protection; ordering robustness. |
| Add dev: `mkdocs*` configured | Declared, no config | Provide `mkdocs.yml` and `docs/index.md` (generated API docs via mkdocstrings). |
| Python | `>=3.11`, classifiers up to 3.14 | CI matrix 3.11–3.13 (+3.14 allow-failure). |

## Proposed Changes
1. **License decision (default: keep GPL-3.0-or-later).** Rationale: repository `LICENSE`/`NOTICE` and the GPL `chadwickpy` dependency already make GPL the consistent choice; Apache-2.0 would require removing `chadwickpy` from the dependency closure or shipping it only as an optional adapter plus a rewrite of the Retrosheet parsing path. Update `CLAUDE.md`, `openspec/project.md`, README, CITATION to GPL-3.0-or-later; ADR 26 records the decision and the alternative. If the owner chooses Apache-2.0 instead, the fallback task list (§1.3) applies.
2. Rewrite `AGENTS.md` (fix numbering, add new mandates) and `CLAUDE.md` (commands, layout, license) in lockstep with code.
3. Shared helpers: `core/coerce.py` (`safe_int`, `safe_float`, `safe_bool` returning `(value, ok)`/raising a typed `CoercionError` for the quarantine path), `core/lazy.py` (lazy singleton helper).
4. De-duplicate sync/async fetch code via `HttpClient`; collapse MLB per-endpoint methods into the endpoint framework (coverage change).
5. Quality gates: ruff rule set extended (`D1` pydocstyle for public API in `src`, `S` bandit subset: `S101` ignored in tests, `S608` for SQL string building, `PL` selected checks: `PLR0912`, `PLR0915`), `mypy --strict` kept, `# type: ignore[code]` only with codes and reasons.
6. CI: `.github/workflows/ci.yml` — jobs `lint` (ruff check/format), `types` (mypy strict), `test` (matrix os × python; `pytest --cov=baseballpy --cov-fail-under=85 -m "not live and not smoke_live"`), `build` (hatch build + `twine check`), `docs` (`baseballpy docs check`, mkdocs build). Nightly `live` workflow (manual dispatch + cron) running `pytest -m live`.
7. Packaging: add `src/baseballpy/py.typed`; `CHANGELOG.md` (Keep a Changelog); bump to `0.2.0`; `mkdocs.yml` + `docs/index.md`.
8. Documentation sync: README (features, install extras, layout, CLI, license), QUICKSTART (v2 layout, `ingest`, `catalog`, `db`), ROADMAP (accurate current state, move delivered items), `docs/DECISIONS.md` ADRs 22–26, every spec in `openspec/specs/*` updated from deltas and verified against code, `docs/sources/*.md` regenerated (coverage change), `docs/ENDPOINT_CATALOG.md` kept current.
9. Test-suite modernization: Hypothesis tests, CLI tests, concurrency tests, signature contract tests, `@pytest.mark.live` and `@pytest.mark.smoke_live` markers registered in `pyproject.toml`; `tests/test_smoke.py` split into CI-safe (mocked) and manual (live) parts.
10. Archive each completed change into `openspec/changes/archive/<date>-<name>/` with `openspec` conventions, after merging deltas into `openspec/specs/`.

## Out of Scope
Feature work (other changes). Publishing to PyPI (a release checklist is added to `docs/RELEASING.md` but not executed).

## Impact
Version 0.2.0; dependency extras reorganized (`dlt-*` extras; `websockets`/`fsspec` removed from defaults). Recorded in ADR 26.
