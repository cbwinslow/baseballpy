# Design: mlb-pool-fallback-completion

All numbers were measured live on 2026-10-31 from this PC with `curl.exe` and the project's user agent
(ADR 40), against `statsapi.mlb.com`. The requests are in section 6.

## 1. Evidence

### 1.1 A multi-value hydrate parameter keeps only its first value

| Request | Status | Splits | Codes |
|---|---|---|---|
| `/v1/people?personIds=592450&hydrate=stats(group=[hitting],type=[statSplits],season=2025,sportId=1,sitCodes=vr,vl)` | 200 | **1** | `vr` |
| the same with `sitCodes=[vr,vl]` | 200 | **2** | `vl\|vr` |
| `/v1/people/592450/stats?stats=statSplits&group=hitting&season=2025&sitCodes=vr,vl` (person route) | 200 | **2** | `vl\|vr` |

The person route accepts a comma list; the hydrate expression does not. The fix belongs in
`_hydrate_expression`, not in `requests_for`. `sitCodes=[vr]` also returns one split, so list-encoding a
single value is safe.

### 1.2 A stat type with no person equivalent

| Request | Status | Result |
|---|---|---|
| `/v1/people/116539/stats?stats=statsSingleSeason&group=hitting` | 200 | `"stats":[]` |
| `/v1/people/116539/stats?stats=statsSingleSeasonAdvanced&group=hitting` | 200 | `"stats":[]` |
| `/v1/people/116539/stats?stats=career&group=hitting` | 200 | one split, 2,747 games |
| `/v1/people/116539/stats?stats=careerAdvanced&group=hitting` | 200 | one split |

A fallback for `statsSingleSeason`/`statsSingleSeasonAdvanced` would therefore write zero rows and
report success. That must be an error, not an empty pool.

### 1.3 Batch size and URL length

| Request | Status | Bytes | URL chars |
|---|---|---|---|
| hydrate, 800 ids, short `stats=season` expression | 200 | 1,271,637 | 5,599 |
| hydrate, 1,200 ids, same expression | **414** | – | 8,399 |
| hydrate, 602-code `sitCodes` expression, 1 id | 200 | 1,247 | 4,360 |
| hydrate, 602-code expression, 10 ids | 200 | 791,247 | 4,423 |

The provider's URL limit is between 5,599 and 8,399 characters. The current `POOL_BATCH = 150` with
the longest measured expression (602 situation codes) is about 5,520 characters, inside the accepted
range; 150 ids of a split pool are about 12 MB of response (791,247 bytes for 10 ids, 0.8–1.2 s) and
fit the 180 s heavy-page timeout. The batch is not raised: the margin is what keeps the request valid.

### 1.4 What a split pool actually returns

Ten 2025 hitters, all 602 situation codes, group hitting: splits per person `0 / 10 / 0 / 146 / 10 /
148 / 112 / 0 / 153 / 142`, 791,247 bytes in 1.23 s, about 1,097 bytes per split. A subject with no
split for a code returns 0 splits, which is a value, not a failure. The person route serves 146 of the
602 codes for a hitter; the pool must keep exactly the splits the route serves, not one per code.

## 2. Decisions

**D1 — Multi-value hydrate parameters are list-encoded, in one place.**
`HYDRATE_LIST_PARAMS = {"group", "type", "sitCodes", "metrics"}` and `_hydrate_value()` split a
comma-joined value and wrap it in brackets. `group` and `type` are already bracketed by the current
builder; moving them through the same function removes the special case that hid the bug. The person
route is unchanged: it accepts commas (measured in 1.1). A split part stored under the earlier chunk
digest is invalidated by a per-stat-type revision (task 2.2), because the columns do not change and
ADR 49's schema digest would otherwise keep the old single-code data.

**D2 — Keep `POOL_BATCH = 150`; shrink on 414 instead of guessing a URL budget.**
150 with the longest measured expression is accepted, and the response fits the timeout. A 414 is the
provider's own answer that a batch is too long, so the fallback halves that batch and retries, down to
one id; at one id the error propagates. A URL-length budget would duplicate a rule the provider already
enforces, and would need the same 414 path anyway.

**D3 — A stat type with no person equivalent is refused, loudly.**
`NO_PERSON_EQUIVALENT: Mapping[str, str]` holds the measured evidence keyed by stat type
(`statsSingleSeason`, `statsSingleSeasonAdvanced`). A 406 on such a pool raises
`PoolFallbackUnavailableError` naming the stat type and the evidence; the people route is not called.
In a `keep_going` run the refusal lands in the endpoint report and the job ends failed, with the stored
data kept — the existing "a refused request does not stop the rest" contract.

**D4 — The split pools are verified live, not asserted complete.**
After the list fix, every `stats_stat_splits_*` pool is re-run on a scratch home; the evidence records
rows, requests, seconds, the split-code coverage per subject and the quarantine state. The acceptance
rule is: for a sampled subject, the codes stored by the pool equal the codes the person route returns
for the same season and group.

**D5 — The single-season pools stay on the direct route; rebuilding them is its own change.**
`stats_stats_single_season_*` and `stats_stats_single_season_advanced_*` are `heavy` and skipped by
`ingest_season`. Their 503 comes from deep offsets, not page size (halving to `MIN_PAGE_SIZE = 125`
still fails), and the person route cannot reproduce them (1.2). A viable path is to rebuild them
season by season: `/v1/sports/1/players?season=Y`, then
`hydrate=stats(group=[g],type=[season],season=Y)` per batch, which returns the same one-row-per-player-
season shape. That is a different ability (season enumeration, first season, era-sport mapping) and
becomes a new card, not a special case here.

**D6 — The probe exercises the shape the fallback sends.**
`baseballpy probe` gains a canary with `hydrate=stats(group=[hitting],type=[statSplits],season=Y,
sitCodes=[vr,vl])`; a 200 proves the list syntax and the fallback route together. The existing plain
person-stats canary stays.

**D7 — Research (AGENTS.md 13.2).** MLB-StatsAPI's `stats` endpoint does not list `sitCodes` in its
query parameters and does not build hydrate expressions, so there is no list-syntax code to borrow;
pybaseball does not call `statsapi.mlb.com` at all. The list form is the provider's own behaviour,
measured above. The alternative (one code per request) would multiply the request count by the number
of codes and is rejected.

## 3. As built

### 3.1 The shipped code

- `sources/mlb_api/generic.py`: `HYDRATE_LIST_PARAMS = {group, type, sitCodes, metrics}` and
  `_hydrate_value()`; a comma-joined value is split first and each list parameter is bracket-encoded.
  An empty parameter is omitted (not sent as `sitCodes=[]`). `NO_PERSON_EQUIVALENT` holds
  `statsSingleSeason`/`statsSingleSeasonAdvanced` with their measured evidence;
  `PoolFallbackUnavailableError` raises before the people route is called, and `ingest()` records the
  refusal under `keep_going` so the rest of the run continues and the job ends failed.
  `_pool_pages_by_hydrate` keeps `POOL_BATCH = 150` as a ceiling, halves the batch on HTTP 414 and
  retries the same players (`offset` only advances after a 200), raising at one id.
- `sources/catalog.py`: `MLB_STAT_TYPE_REVISIONS = {"statSplits": 2, "statSplitsAdvanced": 2}` and
  `_mlb_revision(endpoint)`, keyed on the endpoint's `stats` parameter and only on the `v1/stats` path.
- `src/baseballpy/probe.py`: canary `statsapi people hydrate list (fallback shape)` with
  `sitCodes=[vr,vl]` and the fallback text "the split pools cannot be rebuilt while this route fails".

### 3.2 Live re-run of every `stats_stat_splits_*` pool

2025, sport 1, `sit_codes` = all 602 codes from `/v1/situationCodes`, scratch lake
`%TEMP%\baseballpy-pool-20261031`, 1,470 players in the sport-season (10 hydrate pages of 150 per
pool), one logical request per pool, `allow_heavy=True`, 2026-10-31.

| Pool | Rows | Hydrate pages | Raw MB | Seconds | Errors | Quarantine |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| `stats_stat_splits_hitting` | 104,547 | 10 | 107.8 | 21.5 | 0 | 0 |
| `stats_stat_splits_pitching` | 126,676 | 10 | 168.6 | 58.0 | 0 | 0 |
| `stats_stat_splits_fielding` | 158,697 | 10 | 81.9 | 71.2 | 0 | 0 |
| `stats_stat_splits_catching` | 25,451 | 10 | 14.6 | 42.5 | 0 | 0 |
| `stats_stat_splits_running` | 104,882 | 10 | 55.9 | 27.5 | 0 | 0 |
| `stats_stat_splits_advanced_hitting` | 104,547 | 10 | 92.4 | 33.5 | 0 | 0 |
| `stats_stat_splits_advanced_pitching` | 126,676 | 10 | 134.0 | 42.7 | 0 | 0 |
| `stats_stat_splits_advanced_fielding` | 158,697 | 10 | 81.9 | 32.5 | 0 | 0 |
| `stats_stat_splits_advanced_catching` | 25,451 | 10 | 14.6 | 25.8 | 0 | 0 |
| `stats_stat_splits_advanced_running` | 104,882 | 10 | 55.9 | 26.0 | 0 | 0 |

Every pool answered 406 on `/v1/stats`, fell back to the people hydrate, stored 10 raw pages and
reported no refusal and no quarantine. The advanced family holds the same rows as its plain twin (it
adds columns, not subjects), which is what the provider answers.

- **Resume:** re-running `stats_stat_splits_hitting` on the same lake reported `cached=1` in 0.7 s and
  stored nothing again (manifest resume of the 10 pages); the driver exited 0 both times (the
  `schema_drift` lines on stderr are warnings, not errors).
- **No 414 in the live run:** the 602-code expression with 150 ids stayed inside the provider's limit;
  the halving path is exercised by `test_a_414_on_a_hydrate_batch_halves_it` only.
- **Schema drift:** the run found `gameType`, `numTeams` and `sport.abbreviation` (the latter two in the
  fielding pool) and preserved them in `_extras` with a `schema_drift` warning; a regeneration of
  `mlb_tables.py` through the fallback shape is a separate card (B-190).

### 3.3 Sampled-code comparison (acceptance rule of D4)

The busiest subject of each compared pool, 2025, all 602 situation codes on the person route:

| Pool | Stat type compared | Subject | Stored codes | Served codes | Missing | Extra | Verdict |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | :--- |
| `stats_stat_splits_hitting` | `statSplits` | 641658 | 125 | 125 | – | – | MATCH |
| `stats_stat_splits_advanced_hitting` | `statSplitsAdvanced` | 641658 | 125 | 125 | – | – | MATCH |
| `stats_stat_splits_pitching` | `statSplits` | 570632 | 120 | 120 | – | – | MATCH |

The pool-wide code set (136 codes for hitting, 126 for pitching) is wider than any one subject's,
because a subject only has splits for the codes he faced; the comparison is per subject, per D4.

### 3.4 The single-season family (recorded block, D5)

- `/v1/stats` answers 406 there too, and the person route cannot replace it:
  `stats=statsSingleSeason` and `statsSingleSeasonAdvanced` return `"stats":[]` (design 1.2), so the
  fallback now refuses instead of storing an empty part.
- The direct route's own failure is unchanged: deep offsets answer 503 and halving the page to
  `MIN_PAGE_SIZE = 125` rows does not help (evidence in
  `openspec/changes/mlb-stats-route-406-and-deep-pools/design.md`), so it is not a page-size defect.
- Both pools stay registered and are not marked `unsupported` (the provider's data exists). They are
  skipped by `ingest_season` as `heavy`. The season-by-season rebuild (`/v1/sports/1/players?season=Y`
  plus `type=[season],season=Y` per batch) is B-191, a new change.

## 4. Not verified

- No full season or history run is claimed here; task 2.4 is the live check.
- The provider's exact URL limit is not binary-searched; the design only relies on the measured
  accepted and rejected sizes and on the 414 guard.
- Response-size estimates for a 150-id split batch are extrapolated from 10 ids.

## 5. Risks

- The 602-code expression plus 150 ids is close to the measured 5,599-character accepted request. A
  longer expression must hit the 414 path; the guard is tested with a mocked 414, and a live run that
  reaches it records the smaller batches.
- A split pool is heavy: about 12 MB per request and thousands of requests. It belongs on the homelab,
  in the background, with the existing manifest resume.
- The person route's code set can change with the provider's scoring rules; the acceptance comparison
  is per season, so a change is visible as a mismatch, not a silent difference.

## 6. Reproduction

```
curl.exe -g -s -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1/people?personIds=592450&hydrate=stats(group=[hitting],type=[statSplits],season=2025,sportId=1,sitCodes=vr,vl)"
curl.exe -g -s -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1/people?personIds=592450&hydrate=stats(group=[hitting],type=[statSplits],season=2025,sportId=1,sitCodes=[vr,vl])"
curl.exe -g -s -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1/people/116539/stats?stats=statsSingleSeason&group=hitting"
curl.exe -g -s -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1/people/116539/stats?stats=career&group=hitting"
```
