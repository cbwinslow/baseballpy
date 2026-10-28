# Tasks: Unified Pipeline and CLI

Prerequisites: harden tasks 1-7; restructure tasks 1-4; coverage task 0 (registry + schema tools). CLI commands for
datasets appear as their coverage sections land; this change builds the framework and commands against whichever datasets are registered.

Original task list (superseded by the as-built plan below; design sections 8-10 explain each deviation):
- 1 Pipeline core: done as `baseballpy.ingest` (types, selection, runner) plus one `IngestAdapter` per source instead of `pipeline.py` and `DatasetSpec` hooks.
- 2 Protocol conformance: closed by decision, ADR 39 (adapter layer is the enforced boundary; `tests/test_ingest_contract.py`).
- 3 Config: done (`get_config`/`reset_config` existed; `BASEBALLPY_ENV_FILE` opt-in added, tests in `tests/test_config.py`).
- 4 CLI: done as registration modules (`cli_ingest`, `cli_catalog`, `cli_db`, `cli_stream`, `cli_quarantine`) instead of a `cli/` package; `docs`, `audit` (filters), `refs`, `migrate-layout`, `doctor` in place; `quarantine replay` dropped (design section 10).
- 5 Verification and 6 Docs: see D and F below.

## As-built plan (design section 8)
- [x] A. `ingest/types.py`, `ingest/selection.py`, `ingest/adapters.py`, `ingest/runner.py` + tests (agy, reviewed)
- [x] B. one adapter per source in `sources/<source>/adapter.py`, `sources/adapters.py::register_all_adapters` (agy, reviewed)
- [x] C. CLI `ingest`, `catalog status`, `doctor` in `cli_ingest.py` + CliRunner tests (agy, reviewed; wired into `cli.py` by one call)
- [x] D1. Manual 2026-10-27 (scratch home): `ingest all --seasons 2023 --dry-run` planned 35 jobs with zero requests; real runs of lahman (28 tables), chadwick and retrosheet 1964 (gamelogs + box accounts) completed; the re-run of retrosheet was SKIPPED; `catalog status` and `doctor` correct (0 orphans)
- [x] D2. Live 2026-10-28 (scratch home, `ingest statcast --seasons 2023 --datasets pitches`): killed with TaskStop after 7 chunks (54 MB), 0 orphan `.part` files, `doctor` clean; re-run (45 s) left the 7 files' mtimes unchanged, added 6 chunks and filled the one chunk the kill had left open; 13 chunks, 208,580 pitches, 840 games, 2023-02-24..2023-04-25 queried through `db query`; nothing quarantined. NOT verified: a real Ctrl-C (KeyboardInterrupt path is unit-tested only; the kill was a hard stop) and a complete season (the drive has about 480 MB free)
- [x] E1. `catalog list|show` (`cli_catalog.py`, agy + review) and source-qualified `--datasets source:name` (2026-10-27)
- [x] D3. Live 2026-10-27: mlb_api reference (5,317 rows; re-run skipped), statcast leaderboards 2023 (21,208 rows), mixed-source `source:name` datasets, mlb_api season 2023 (658,502 rows, 35 minutes; found and fixed the sport/team fan-out 404s, change `mlb-sport-fanout-404`)
- [x] P-5 analysis (2026-10-27): 2 of 6 extractors (Chadwick, Statcast pitches) satisfy ExtractorProtocol (`extract`/`extract_async`); Lahman, MlbApi, MlbEndpoint and the leaderboard extractor do not; 2 of 6 normalizers (Chadwick, Statcast pitches) have `schema`/`normalize`/`normalize_stream`, the rest only `normalize` or nothing. The non-conforming ones serve many datasets (27 Lahman tables, hundreds of MLB endpoints, 34 leaderboards), where one `schema` property has no meaning; adding wrappers just to satisfy the Protocol would be conformance theater. DECIDED by the owner 2026-10-27: option (b), see ADR 39 and design section 9. Options were: (a) keep the Protocols for single-dataset sources and add `schema_for(dataset)`/`extract(dataset, ...)` to the multi-dataset ones, with the contract test enforcing that, or (b) declare the adapter layer (`IngestAdapter`, tested) the enforced boundary and relax the extractor-level Protocols in AGENTS section 2
- [x] E2. P-5 closed by decision (b): `tests/test_ingest_contract.py` (every source has a conforming adapter), ADR 39, AGENTS section 2, core-protocols spec updated
- [x] E. Config opt-in dotenv, audit filters (`0dfd5a5`), `db views|query|shell`, `stream`, `quarantine list|show` (`174d46c`, agy draft + review), generated `docs/CLI.md`, README/QUICKSTART CLI sections
- [x] F. Live 2026-10-28: `stream 718497 --replay --duckdb` twice and a third time: 443 events, 443 distinct keys each time (6 event kinds); without `--replay` the stored watermark yields 0 events. Spec `cli-and-ingest` merged into `openspec/specs/`, ADR 25 final
- Not verified / owner: `catalog status` has no MISSING rows after `ingest all` (needs a full lake, disk is too small here); real Ctrl-C on Windows

## Status (2026-10-28)
Complete; archived.
