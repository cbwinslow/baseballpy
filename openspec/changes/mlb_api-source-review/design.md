# Design: mlb_api-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/05-mlb_api.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Surveyed 2026-10-30 (facts only; the cards decide what is a finding).

- **Provider:** the MLB Stats API (`statsapi.mlb.com/api`, v1 and v1.1; no key). Currency is by response content or freshness (ADR 43): no version marker is offered.
- **Registry:** 366 datasets: 100 default season-partitioned, 221 opt-in season-partitioned (per game, per person, all-time pools), 33 default season-less (reference lists), 6 and 3 `api_only`, 3 on-demand. They use 65 distinct routes (`docs/references/ENDPOINT_CROSSCHECK.md`, generated).
- **Code:** `sources/mlb_api/` is about 4,700 hand-written lines plus two generated tables (`mlb_tables.py` 18,871 lines, `stat_combos.py` 1,146): `endpoints.py` 923, `stream.py` 600, `generic.py` 413, `normalizer.py` 391, `api.py` 361, `extractor.py` 295, `schemas.py` 235, `flatten.py` 174, `adapter.py` 117.
- **Tests:** `test_mlb_api.py`, `test_mlb_coverage.py` (383 tests), `test_mlb_param.py`, `test_mlb_stream.py`, `test_gen_mlb_keys.py`.
- **Spec:** `openspec/specs/mlb-api-ingestion/spec.md` has 11 requirements; `real-time-streaming` covers the live streamer.
- **Known open problem:** league-wide `v1/stats` answers HTTP 406 (B-30, external); the generator now logs provider errors and refuses to write an empty combo table (2026-10-30). Fifteen all-time pools wait for it (`mlb-stats-route-406-and-deep-pools`).
- **Already known from earlier reviews (apply as checks):** keys unique on real rows; every operation audit-logged; empty text vs NULL must round-trip through CSV; dictionary columns of several parts must verify; chunks carry the schema digest (ADR 49) and a `revision` when a value fix keeps the columns (ADR 51); no hard-coded seasons or lists.

## S1 inventory
Checked 2026-10-30: `baseballpy catalog audit --source mlb_api` (live: the provider's lists of stat types, groups, sports, levels and routes against the registry) reports "No findings". The route cross-check against five reference documents (`scripts/endpoint_crosscheck.py`, 65 routes) names 22 routes only the live API shows (spelled differently in the references or undocumented). There is no second way in. Licence: MLBAM's notice (`docs/DATA_LICENSES.md`). There is no git pin.

## S2 conformance
`tests/test_architecture.py`, `tests/test_ingest_contract.py`, `tests/test_lake.py` and the five MLB test files pass (full suite 1,161 passed). The adapter reaches the runner only through `IngestAdapter`; endpoints come from the declarative `ENDPOINTS` table (`endpoints.py`) and the generic fetcher (`generic.py`).

## S3 schema and types
(not started)

## S4 code review against the designated tools
Reuse check per module: `extractor.py` and `generic.py` use the shared `HttpClient`, audit logger, `RawStore`/`ProcessedStore` and the shared freshness policy; `flatten.py` is generic JSON flattening driven by the endpoint table; `stream.py` uses `async_track`. Findings: (1) `api.py` and `extractor.py` hard-coded `season=2024` as the default of standings, transactions and draft (nine signatures), contradicting "no hard-coded seasons"; (2) `extract_standings` did not pass `refresh` to the cache layer, so `refresh=True` was ignored. Both fixed by task 5.6 (card M-15); the test fails without the change.

## S5 tests and spec gaps
(not started)

## S6 live verification
(not started)

## S7 access, export, descriptions, docs, close
(not started)

## 5.1, 5.2, 5.3, 5.4, 5.5 evidence (2026-10-30)
5.1: the four raw writes (`generic.py` x2, `extractor.py` x2) now pass `response_fingerprint` (ETag, else sha256); test fails without the change. 5.2: the generic fetcher already used `schema_matches` (ADR 49); the hand-written `_extract` cache check did not and now does; test fails without the change. 5.3: the MLB Stats API publishes no official documentation page (the references are third-party and listed in `docs/references/`); nothing to keep. 5.4: no second way in. 5.5: only the declarative endpoints had a by-name entry point (`get_endpoint`); `sources/mlb_api/access.py` adds `table(name, season, **arguments)` and `datasets()` over all 366 registered names (nine hand-written plus the declarative ones). 5.6: see S4.
