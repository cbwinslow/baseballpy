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

Fill in when the tasks land: the shipped table, the live re-run numbers for every `stats_stat_splits_*`
pool, the sampled-code comparison, and the recorded block for the single-season family.

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
