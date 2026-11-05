# MLB backfill fixes (found in the 2008-2012 run)

## Why
Chunk 1 of the MLB backfill (2008-2012, 2026-11-05) found two defects:
1. Season 2011 failed with `could not acquire manifest lock` on `award_recipients`: its manifest holds 3,200+ entries and every save re-wrote it with `json.dumps(indent=2)`, which forces Python's slow encoder (about 50 ms alone, seconds with many writers waiting on one lock).
2. `audit speed` reported 5 requests in flight against a limit of 4. The client measured a request's end after it had given its slot back, so the logged end could overlap the next request on the same slot: a logging error, not an extra request.

## What changes
- Manifests are written as one field per line without `indent` (fast encoder), and the lock wait is 30 s.
- The request duration is measured inside the slot.
- A test saves into a 3,000-entry manifest from 30 threads and must not time out (it failed before the fix).

## Not changed
The 3,399 HTTP 406 answers from `/v1/stats` are the known provider refusal (B-30, change `mlb-stats-route-406-and-deep-pools`).
