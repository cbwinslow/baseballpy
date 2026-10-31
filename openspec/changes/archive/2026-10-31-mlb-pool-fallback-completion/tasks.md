# Tasks: mlb-pool-fallback-completion

Order: 2.1 -> 2.4 land together; 2.5 is the live proof (LONG, homelab); 2.6 and 2.7 close.

## 1. The fallback

- [x] 2.1 `sources/mlb_api/generic.py`: `HYDRATE_LIST_PARAMS` and `_hydrate_value()`; every multi-value
  parameter in `stats(...)` is list-encoded and a comma-joined value is split first. The person route
  (`requests_for`) keeps commas.
  Tests in `tests/test_mlb_coverage.py`:
  `test_hydrate_expression_list_encodes_multi_value_parameters`,
  `test_hydrate_fallback_keeps_every_split_code` (a mocked person answer with `vr` and `vl` stores two
  rows and two split codes).
  Done when both tests pass and an empty `sitCodes` is omitted rather than sent as `sitCodes=[]`.

- [x] 2.2 `sources/catalog.py`: a per-stat-type parser revision for `statSplits`/`statSplitsAdvanced`
  (the mechanism of ADR 51, keyed by the endpoint's `stats` parameter, never by dataset name), so a
  split part stored by the old fallback is stale and is fetched again without `--refresh`; every other
  MLB dataset keeps `MLB_REVISION`.
  Test: `test_a_split_pool_written_before_the_list_fix_is_fetched_again`.
  Done when the test passes and a non-split MLB dataset written under the old revision is still served.

- [x] 2.3 `sources/mlb_api/generic.py`: `NO_PERSON_EQUIVALENT` (stat type -> measured evidence) and
  `PoolFallbackUnavailableError`. A 406 on a pool whose stat type is listed raises with the type and
  the evidence; the people route is not called and no empty part is stored.
  Test: `test_a_pool_stat_type_without_a_person_equivalent_is_refused`.
  Done when the test passes for `statsSingleSeason`, and the error text names the stat type and the
  change design section it comes from.

- [x] 2.4 `sources/mlb_api/generic.py`: `_pool_pages_by_hydrate` halves a batch on HTTP 414 and retries,
  down to one id; at one id the error propagates. Raw page names stay unique across retries.
  Test: `test_a_414_on_a_hydrate_batch_halves_it`.
  Done when the test passes and a successful retry stores every returned page as raw bytes.

- [x] 2.5 Live proof (LONG, homelab): on a scratch `BASEBALLPY_HOME`, run every `stats_stat_splits_*`
  pool with `include_history=True`; record rows, requests, seconds, quarantine and the split codes of a
  sampled subject, compared with the person route for the same season and group. Re-run one failed
  pool to show resume. Record the single-season family's 503 and the empty per-person
  `statsSingleSeason` as the block, and open a card for the season-by-season rebuild (design D5).
  Evidence goes under "As built" in `design.md`.
  Done when every split pool is stored with its codes, or has a recorded root cause that is not the
  list-syntax defect; the single-season block is written with its evidence.

## 2. Close the change

- [x] 2.6 `probe.py`: a canary with
  `hydrate=stats(group=[hitting],type=[statSplits],season=Y,sitCodes=[vr,vl])`; the fallback shape is
  visible in `baseballpy probe`.
  Test: `tests/test_probe.py::test_probe_checks_the_hydrate_list_syntax`.
  Done when the canary answers 200 in a live probe and the CLI table names it.

- [x] 2.7 Docs and close-out: the pool section of `docs/sources/mlb_api.md` states the list rule, the
  refusal for types without a person equivalent, the 414 behaviour and the single-season block; ADR 55
  (written 2026-10-31); merge the delta into `openspec/specs/mlb-api-ingestion/spec.md`; update ADR 53's
  consequences; move the change to `openspec/changes/archive/<date>-mlb-pool-fallback-completion/`.
  Done when `openspec validate --specs`, `docs generate --check` and the four gates are green and the
  change is archived.
