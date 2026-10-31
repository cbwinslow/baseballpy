# Proposal: Finish the per-person fallback for the league-wide pools

## Why

ADR 53 made a league-wide player pool fall back to `/v1/people?personIds=...&hydrate=stats(...)` when
`/v1/stats` answers 406. Two defects make that fallback incomplete or silent, and the pools it was
meant to unblock are still not done:

1. **A multi-value hydrate parameter loses all but its first value.** Inside a hydrate expression the
   provider keeps only the first item of a comma list: for Aaron Judge, season 2025,
   `sitCodes=vr,vl` returns **1 split** (`vr`) while `sitCodes=[vr,vl]` returns **2** (`vr` and `vl`).
   The person route (`/v1/people/{id}/stats?sitCodes=vr,vl`) accepts commas and returns both, so the
   defect is the hydrate expression builder, not the provider. Every `stats_stat_splits_*` pool
   would store one code per subject and call it complete.
2. **A pool with no per-person equivalent is attempted anyway.** `statsSingleSeason` and
   `statsSingleSeasonAdvanced` have no person-level form: `/v1/people/{id}/stats?stats=statsSingleSeason`
   answers 200 with `"stats":[]` (tested on Derek Jeter and Aaron Judge). If that pool ever receives a
   406, the fallback would write zero rows with no error — the silent loss `AGENTS.md` 7.1 forbids.
3. **An oversized batch aborts the pool.** A 602-code expression plus 1,200 player ids is an 8,399
   character URL and the provider answers **414**; only batches of about 800 ids are accepted. The
   current 150 is safe, but nothing shrinks a batch when a longer expression pushes it over.
4. **Nothing checks the fallback's shape before a long run.** `baseballpy probe` checks the plain
   person route, not the hydrate-with-list request the fallback actually sends.

## What

- One rule for hydrate expressions: multi-value parameters (`group`, `type`, `sitCodes`, `metrics`) are
  list-encoded; a comma-joined value is split first.
- A measured table of stat types with **no per-person equivalent**; a 406 on such a pool raises a named
  error with the evidence instead of storing zero rows.
- A 414 guard that halves the batch and retries, down to one id, then raises.
- A live re-run of every `stats_stat_splits_*` pool with rows, requests and seconds recorded; every
  split code the person route serves is kept.
- A probe canary that sends the fallback's real shape (`sitCodes=[vr,vl]`).
- The three single-season pools stay on the direct route and stay blocked; their evidence is recorded
  and a season-by-season rebuild becomes its own card (they are not a special case here).

## Out of scope

- The direct `/v1/stats` 406 itself (B-30/B-32; the provider must change).
- Rebuilding the three `stats_stats_single_season_*` pools season by season (new card, see `design.md`
  D5).
- Regenerating schemas: the fallback returns the same split objects as the direct route; a new key
  found by a live run is handled by the drift warning and a schema regeneration, separately.
