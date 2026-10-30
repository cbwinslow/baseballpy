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
Live run on a scratch home (`baseballpy_mlb`, 2026-10-30), `ingest mlb_api -s 2025 -c 2`: the reference job was skipped (already stored), the 2025 season job stored 682,181 rows in 2,928 s (533 MB), 96 datasets with data, no quarantine, and ended `failed` only because 680 league-wide `v1/stats` requests (all `stats_*` pools) answered HTTP 406 (B-30); the other endpoints were stored. Schema drift found by the real data and fixed with `gen_mlb_schemas.py --only`: `award_recipients.notes`, `team_alumni.death*` (4 columns), `team_affiliates.placeholder`; the generator itself needed two fixes (a sample for endpoints that need team ids, a placeholder team, a wider award sample). Keys on the real rows: 17 datasets had a non-unique registered key; 9 were fixed by extending the key with columns the rows prove unique (5.8) and the rest are task 5.11 and 5.12. Empty-string text in 14 datasets (5.10).

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

## 5.8, 5.9, 5.10 evidence (2026-10-30)
5.8: candidate keys were tested on the 2025 rows before being declared: `players_season (id, sport_id)`, `schedule_hydrated (+sport_id)`, `team_stats_{game_log,at_game_start}_{hitting,pitching,fielding} (+game.gamePk)` all 0 duplicates (jersey numbers were tried as key parts and rejected: an empty jersey number is NULL after 5.10 and a NULL key part breaks merge, so the roster, coach and personnel repeats stay in 5.11); `ref_metrics` is keyed by `metricId` (one metric has the empty name); `stats_leaders` with sport, season, game type and person still has 180 repeats (173 identical provider rows). 5.9: the adapter accepted only `games, history, people_stats, reference, season`; any registered dataset name now plans one `endpoint` job (live: `-d team_affiliates,team_alumni,award_recipients` stored 1,133 + 11,267 + 1,911 rows). 5.10: `_as_string` returns NULL for an empty string and the declarative datasets are at revision 1 (ADR 51 mechanism), which also makes every stored MLB chunk stale once.

## 5.13 and 5.14: root cause of the 406 and the permanent fix (2026-10-30)
Probes (curl, 2026-10-30): `GET /api/v1/stats` answers a Spring-style 406 `Not Acceptable` for every query tried: any user agent (`python-requests/2.x`, a browser, `baseballpy`), any `Accept` header or none, with or without `playerPool`, `sportId(s)`, `limit`, `gameType`, any group or stat type, seasons 2019 to 2025, and even `stats=career&group=hitting` with no season. `v1/teams/stats`, `v1/people/{id}/stats`, `v1/stats/leaders`, `v1/schedule`, the live feed (`v1.1/game/{pk}/feed/live`, `/timestamps`, `/diffPatch`) and `v1/people?personIds=...&hydrate=stats(...)` answer 200 with our user agent (`python-requests/2.32.3`, the one pybaseball sends) and with curl's default. So the 406 is a provider-side fault of that one route, not our user agent, header or rate (8 requests per second); a 403 was not reproduced anywhere today. Fix: the hydrate fallback (live: 921 rows for sport 1, season 2025, in 3 s; maximum `stat.homeRuns` 60) and `baseballpy probe` (11 canaries, about 3 s). Limits: all-time pools without a season (`career*`, `statsSingleSeason*`) have no player list to batch over and stay on the direct route; the hydrate splits carry two fields (`gameType`, `numLeagues`) the direct-route schema lacks, so they are kept in `_extras` and logged as drift until the schemas are regenerated through the fallback.
