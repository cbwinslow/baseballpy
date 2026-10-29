# Proposal: League-wide v1/stats answers 406; deep all-time pools answer 503

## Why
On 2026-10-29 every league-wide `statsapi.mlb.com/api/v1/stats` request answers HTTP 406 from this PC and the homelab (`stats=season`, with or without `playerPool`, `limit`, `sitCodes`, a browser User-Agent), while `v1/teams` and `v1/people/{id}/stats` answer 200. The route worked earlier the same day. The league-wide datasets (`stats_*`, including the per-season default ones, and the all-time pools) all depend on it. Separately, `stats_stats_single_season_{hitting,fielding,advanced_fielding}` answered 503 after 170-262 s on deep offsets of a 190k-row pool (evidence: `verify-optin-paths/design.md`).

## What
Research the 406 (pybaseball, MLB-StatsAPI, baseballr issues; record in `design.md`), retest at most hourly, report it as a provider error (never `unsupported` without a 200-control), stop the generator from writing an empty combo table when phase 1 sees only non-200 answers, split the three deep pools into smaller pages or per-season requests, then re-run the 15 failed pools and a modern season once the route answers 200. Also regenerate the `team_stats_year_by_year_*` schemas whose real-run `schema_drift` was never absorbed.

## Out of scope
Changing the User-Agent again (ADR 40) or impersonating a browser.
