# Design: mlb-stats-route-406-and-deep-pools

## 1.1 Research (2026-10-30, extended 2026-10-31)

Searched for how other clients handle HTTP 406 on `statsapi.mlb.com/api/v1/stats`. No issue, forum
post or client documentation reports this status for that route; results were generic definitions of
406 (the server cannot produce a response matching the request's `Accept` headers), a community
OpenAPI client that lists `GET /api/v1/stats` (parameter reference only) and unrelated clients.

Read the two clients the owner named, on 2026-10-31:

- **MLB-StatsAPI** (`toddrob99/MLB-StatsAPI`): `def get()` calls `requests.get(url)` with no headers,
  no timeout argument and no retry; its `stats` endpoint configuration does not even list `sitCodes`
  among the query parameters, and it never builds a `hydrate=stats(...)` expression. There is no
  header, retry or parameter trick to borrow.
- **pybaseball**: no module calls `statsapi.mlb.com`; its data comes from FanGraphs, Baseball-Reference
  and Baseball Savant. Nothing to borrow for this route.

## 1.2 Retest log (one request per hour at most; control `v1/teams`)

- 2026-10-29: 406 on league-wide `v1/stats` from this PC and the homelab; `v1/teams` and
  `v1/people/{id}/stats` answered 200.
- 2026-10-30: `v1/stats?stats=season&group=hitting&season=2025&sportIds=1&playerPool=ALL&limit=5`
  answered 406 again; control `v1/teams?sportId=1&season=2025` answered 200.
- 2026-10-31: 406 for the same query with `python-requests/2.32.3`, a browser agent and no agent at
  all; HTTP/1.1 and HTTP/2; `Accept: application/json`, `Accept: */*` and `Accept: text/html`;
  `stats=season`, `stats=career`, `stats=byDateRange`; zero parameters and a trailing-slash path.
  Controls on the same host: `/v1/teams` 200, `/v1/people/{id}/stats` 200, `/v1/stats/leaders` 200,
  `/v1.1/stats` 404. Still open (B-32).

## 1.3 Conclusion: the refusal is path-level

- A bare `curl` with no Python, HTTP/1.1 and **no query parameters at all** answers 406 for
  `/api/v1/stats` and for `/api/v1/stats/`; `/api/v1/stats/leaders` on the same host answers 200.
- No user agent, `Accept` header, parameter set or protocol version changes the answer.
- `ws.statsapi.mlb.com` is not a push socket: a plain GET returns the same 663,043-byte live feed
  (200), and an Upgrade request answers Cloudflare 500.

What the evidence supports is a **provider-side refusal of this path** (a front-end rule or content
negotiation at MLB's edge), not a user agent, parameter, rate or content-negotiation problem on our
side. The internal rule is not observable from here, so this is a path-level conclusion, not a
"root cause confirmed" claim about MLB's configuration.

## 2.1 Generator guard (2026-10-30)

`scripts/gen_mlb_schemas.py`: `get_json` logs every provider error (403, 406, 429, 500, 502, 503, 504)
with its status and remembers it in `PROVIDER_ERRORS`; `probe_param_combos` does not mark a stat type
`unsupported` when a provider error occurred during its probe protocol; `write_combos` refuses to
replace `stat_combos.py` with an empty league-wide player or team table. Tests:
`tests/test_gen_mlb_keys.py::test_a_provider_error_is_logged_and_remembered_never_read_as_no_data`,
`::test_an_empty_league_wide_table_is_never_written` (both fail without the change).

## 2.2 Deep pools (2026-10-30)

The single-season pools (`stats_stats_single_season_*` and `..._advanced_*`, about 190k rows each)
ignore the season, so a per-season split is impossible; the 503s came from deep offsets with 1,000-row
pages. `MlbEndpointExtractor._get_paginated` halves the page size from the same offset after a 5xx
(down to `MIN_PAGE_SIZE = 125`) and continues with the smaller page, logging each step. Test
`tests/test_mlb_coverage.py::test_a_5xx_at_a_deep_offset_is_retried_with_smaller_pages` (fails without
the change). Not verified live: the route answers 406 (1.2), so the pools cannot be re-run yet (3.1).

## 2.3 The hydrate fallback and the two defects found on 2026-10-31

ADR 53's fallback (`/v1/people?hydrate=stats(...)`) answers 200, but it did not reproduce a split pool:

- **Multi-value parameters lose all but the first value inside a hydrate expression.** For Aaron
  Judge, 2025, `sitCodes=vr,vl` returned one split (`vr`); `sitCodes=[vr,vl]` returned two (`vr`,
  `vl`). The person route accepts the comma list. Fixed by `mlb-pool-fallback-completion` task 2.1.
- **Two stat types have no person equivalent.** `/v1/people/{id}/stats?stats=statsSingleSeason` and
  `statsSingleSeasonAdvanced` answer 200 with `"stats":[]` (Jeter and Judge), while `career` and
  `careerAdvanced` return a split. A fallback for those pools would store zero rows silently. Refused
  by `mlb-pool-fallback-completion` task 2.3.
- **An oversized hydrate request answers 414.** 800 ids with a short expression (5,599 characters)
  answered 200; 1,200 ids (8,399 characters) answered 414. The current batch of 150 plus the longest
  measured `sitCodes` expression is about 5,520 characters and is accepted; task 2.4 adds the guard.

## 3.2 (2026-10-30)

`gen_mlb_schemas.py --only` regenerated the eight `team_stats_year_by_year_*` (and `_advanced_*`)
schemas: 40 requests each, all answered 200, keys unique; 78 stat columns (`stat_fly_hits`,
`stat_balls_in_play`, `stat_ground_outs`, ...) are now typed instead of landing in `_extras`. Test
`tests/test_mlb_param.py::test_year_by_year_team_stats_type_the_fields_the_real_run_showed`.

## 4. What is blocked, and what is not

- **Blocked: the single-season family.** The direct route 406s (1.2) and per-person
  `statsSingleSeason` is empty (2.3), so neither the direct nor the hydrate path can build it today.
  A season-by-season rebuild is the viable route (new card in `mlb-pool-fallback-completion`).
- **Blocked: the 406 itself** (B-30/B-32). Only the provider can clear it; the hourly retest is the
  only action.
- **Not blocked: the split pools.** Once the list fix lands, every `stats_stat_splits_*` pool is served
  by the person route; the live proof is task 2.5 of `mlb-pool-fallback-completion`.
- **Not blocked: the career and season pools already stored.** They were ingested before the 406 began
  and are not affected.

## 5. Next action

Work `mlb-pool-fallback-completion` tasks 2.1-2.4 (code and tests), then 2.5 on the homelab. Retest
`/v1/stats` no more than once an hour (B-32); when it answers 200, the single-season family can be
re-run on the direct route before the season-by-season rebuild is needed.

## As built: task 3.3 (2026-11-07)

Re-probed all supported endpoints with `gen_mlb_schemas.py --skip-combos --only <all names>` (the `--only` merge keeps endpoints that return nothing). 142 endpoints gained typed columns (`*_name_slug`, `hot_cold_zone_stats_stats` and similar) that had been landing in `_extras`. 25 league-wide `stats_*` endpoints (projected, season, season advanced, outs above average, expected statistics, sabermetrics, last x games) lost columns in the new sample because `v1/stats` still answers 406 (B-30): their old tables, probe entries and fixtures were restored. They stay open for B-35 once the route answers 200. The count of 61 in the backlog was not recorded anywhere; the real number is 142.

## As built: task 3.4 (2026-11-08)

Regenerated the 31 game, roster, schedule and draft datasets with `gen_mlb_schemas.py --skip-combos --only ...`, with eight more sample games (`SAMPLE_GAMES`) that carry rare fields. Gained: challenge-review details with a player and `additional_reviews` in `game_feed_play_events`, `game_feed_plays`, `game_play_by_play` and `game_win_probability` (and `injuryType`). Nothing lost.

Still in `_extras` (no data is lost, but the fields have no typed column yet because no sampled response carried them): `schedule_postseason` reschedule and resume fields and `status.reason`; `draft_prospects` `person.xrefIds`; `team_affiliates` conference; roster `parentTeamId` and `note`; `reviewDetails.additionalReviews` in the play-event twin; and the 25 league-wide `stats_*` datasets, which wait for the 406 (B-30). The next regeneration should add samples that carry them (a season with a rescheduled postseason game, a loaned player, a conference-bearing affiliate).

## As built: tasks 1.2 and 3.1 (2026-11-12)

Correction (same night): the route is **intermittent**, not back for good. It answered 200 from about 16:00 to 19:15 local time on 2026-11-12 (control `v1/teams` 200), and answered 406 again at 19:45 for every request shape tried (`sportId` 1 and 11, `projected` and `season`, with and without `playerPool`). The refetch below ran in the 200 window but with `-d <pools>`, which asks only for sport 1; the minor sports (11 and up) were not refetched, so they still hold the fallback data. `ingest mlb_api -s Y --refresh` without `-d` (as the sample run does) asks for every sport.

`/v1/stats` with `playerPool=ALL` answered 200 on 2026-11-12 (control `v1/teams` 200). `verify-sample mlb_api -s 2024 --limit 3` then showed that the lake's league-wide pools had been filled by the hydrate fallback during the 406 window: projected hitting held 652 rows, the live route returned 3,709 (four pages), and the lake held `*.hydrate.pN.json` raw files the direct route does not write. All 35 `stats_*` pools were refetched with `ingest mlb_api -s Y --refresh -d <pools>` for every season 2008-2026: 35 jobs completed per season, 0 failed, about 2 minutes per season, disk use flat. The old hydrate raw files stay (raw is never deleted).

Two problems surfaced and were fixed with tests: (1) the live route puts `splitsTiedWithOffset` and `splitsTiedWithLimit` (page-boundary copies of rows already stored) in every page; copied onto each row they made one season of the two projected pools 775 MB (now 1.3 MB, same row counts), see ADR 116; (2) the store refused to rewrite old chunks holding the two columns, so a declared `retire_columns` registry was added. 72 of 74 stats schemas were regenerated; the two `careerStatSplits` tables hit a provider 503 and keep the columns until a later regeneration.

## Evidence: fresh MLB 2024 sample against the lake (2026-11-12, night)

`baseballpy verify-sample mlb_api -s 2024 --limit 3 --all` after the schema regeneration and `compact --source mlb_api` (564 old-schema files rewritten): 12,275 processed chunks compared, 11,698 identical (95.3%), none missing in the lake. All game datasets (boxscore, linescore, play by play, win probability, feed) are identical. The 577 chunks that differ are of two kinds: (a) data the provider changes over time and that the lake fetched earlier (`team_alumni` 244, `team_roster_gameday` 51, `team_roster_all_time` 42, `schedule_hydrated` 14, `players_season` 11, one each for standings, venues, draft, personnel, ...: ages, shirt numbers, rosters), expected to differ; (b) 186 league-wide stat-pool chunks of the minor sports that still hold fallback data (B-35: the direct route answered 406 again at 19:45 local time). `verify-sample` earlier showed the same pools 652 vs 3,709 rows (projected hitting), which is why they are refetched when the route answers 200.

## Evidence: is the hydrate fallback complete for the minor sports? (2026-11-13)

Question: does the player list of the fallback (`/v1/sports/{id}/players`) miss players the direct route would return? Oracle: Statcast minor-league pitches (`statcast_pitches_minors`, all levels it tracks) joined to the schedule for the level, regular season only. Every distinct batter and pitcher Statcast saw at a level was looked up in the lake's `stats_season_hitting` / `stats_season_pitching` of that level.

| Season | Level (sport id) | Hitters seen / in pool | Pitchers seen / in pool |
| --- | --- | --- | --- |
| 2023 | 11 (Triple-A) | 907 / 907 | 1,242 / 1,242 |
| 2023 | 14 | 339 / 339 | 456 / 456 |
| 2024 | 11 | 865 / 865 | not run |
| 2024 | 14 | 367 / 367 | not run |
| 2025 | 11 | 895 / 895 | 1,264 / 1,264 |
| 2025 | 14 | 355 / 355 | 492 / 492 |

Sport 1, 2024: 651 batters with a plate appearance in the stored boxscores, all 651 in the pool. Nobody was missing in any row.

False alarm worth recording: a first comparison that ignored the level reported 319 Triple-A batters missing. They were Single-A players (all 319 sit in the sport 14 player list). The "652 against 3,709" gap seen on 2026-11-12 was the projected pools of sport 1, which the direct route now holds (3,709 rows); it was not a player-list defect. Season rosters (`fullSeason` and `allTime`) would not have helped either: they covered 0 and 62 of those 319.

What this does not show: levels Statcast does not track (rookie leagues, Dominican Summer League), the pools other than season stats, and any field the direct route carries that the people route does not (`nameSlug`, `gameType`, `numLeagues`). The fallback chunks therefore stay provisional (ADR 117) and are re-fetched when the route answers 200.
