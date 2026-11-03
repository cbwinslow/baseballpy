# Design: mlb-rate-10

## Decisions
- 10 is the top of the range `AGENTS.md` allows; nothing above it without a new decision.
- Only the default changes; the token bucket, retries with `Retry-After` and the per-host
  in-flight limits are untouched, so a 429 still backs off.
- Revert criterion: any 429, refused request or error in the full-season proof run.

## Evidence (2026-11-03)
- **Cold-season test, `stats_season_hitting` (all sports, a different season per run because MLB caches repeated requests):** rate 8: 16.9 s and 16.7 s (7.1 calls/s); rate 10: 14.0 s and 12.9 s (8.4 and 8.9 calls/s); 0 errors in all four, network time per call unchanged (0.21-0.22 s mean).
- **Full 2024 season (`ingest mlb_api -s 2024`, fresh scratch lake, same 12,309 network requests each time):** original code 3,234 s (3.78 requests/s); ADR 57 at rate 8: 2,264 s; rate 10: 1,749 s (median 591 requests/min, max 605; 10 requests/s = 600/min). 54 min -> 38 min -> 29 min. 12,311 audit events, 0 non-success, no 429, no traceback.
- **Data check, rate 8 run against rate 10 run:** 132 datasets each, 131 identical in row count. One differs: `standings_by_organization` has 201 team records in the first run and 106 in the second. The raw payload of the second is a valid subset of the first (19 of 30 organization groups, 308,486 bytes against 573,230, `lastUpdated` 20:20:30 against 20:20:00): the provider served a partial answer once for the single request of that dataset. Five fetches made afterwards returned the full 573,230 bytes every time. Not shown to be related to the rate (one request, a stored provider answer), but nothing in the client can tell a partial valid answer from a full one; see B-235.
- **Not verified:** rates above 10 (not allowed by `AGENTS.md` without a new decision); behaviour over a multi-season backfill at 10/s.
