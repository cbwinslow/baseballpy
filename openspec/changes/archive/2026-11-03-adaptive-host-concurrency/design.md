# Design: adaptive-host-concurrency (rejected)

## What was built (discarded)
`core/gate.py` `AdaptiveGate`: `limit = clamp(ceil(rate x latency x 1.25), floor, ceiling)`,
latency as a moving average (weight 0.3), growth at most two slots per observation, immediate
shrink, back to the floor for 30 s after a retryable status or transport error, ceiling 16,
pools sized by the ceiling, a switch (`adaptive_concurrency`) to pin the floor. 11 unit and
client tests; two of them were shown to fail when the error back-off or the latency measurement
was removed. The files are not kept in the repository.

## Evidence (2026-11-03, live)
1. **Where the "slow phases" really were.** One heavy league-wide pool (`stats_sabermetrics_pitching`,
   all sports, 2024): 156 HTTP calls in 21.5 s = 7.2 calls/s against the 8/s limit; network time per
   call 0.03 s (mean), 38 MB. The "17-19 s per request" in the season audit log was mostly time
   waiting for the host's token bucket (offered load above 8/s), not network time. Two more pools
   (`outs_above_average_running`, `season_hitting`) behaved the same (0.11 s and 0.14 s per call,
   7.2 calls/s). These are rate-bound; more requests in flight cannot help, and the gate correctly
   never grew above its floor (highest limit 4 with ceiling 16).
2. **The only genuinely slow endpoint found, `stats_leaders`** (20 calls, 2.3 MB each, 4-8 s per
   call, up to 30 s): cold-season A/B (a different season per run, because MLB caches repeated
   identical requests; repeating the same season gave 59 s, 15 s and 6 s). Wall time, adaptive on:
   33.6 s and 48.2 s (mean 40.9); pinned: 34.1 s and 29.6 s (mean 31.9). Network time per call was
   higher with adaptive (5.8 s, 8.4 s, 7.7 s, 8.1 s against 3.8 s, 4.8 s, 6.3 s, 5.0 s): the server
   answers slower when it gets more at once, and the wall time is set by the slowest single request
   (21-30 s), not by the concurrency.
3. **Savant**, 40-day cold ranges (8 five-day windows, 150k rows), two rounds: adaptive up to 16:
   3,324 and 2,999 rows/s; pinned at 8: 3,414 and 2,919 rows/s; 0 back-offs. A first round showed one
   slow adaptive run (1,046 rows/s) that did not repeat. Each window took about 40 s whatever the
   limit: Savant's server sets the throughput (about 3,100 rows/s).
4. **Cache artefacts to remember.** Both Savant and MLB serve repeated identical requests much
   faster (Savant: 92.8 s then 7.4 s then 8.0 s on the same range). Any benchmark must use fresh
   ranges or seasons.

## Decision
Keep the fixed per-host limits of ADR 57 (4, Savant 8). Do not ship adaptive concurrency: no gain
on rate-bound pools (they sit on the host's rate), none on Savant, a loss on MLB's slow endpoint,
plus a feedback risk (a server that slows under load pushes the limit up). The remaining lever on
MLB is the host rate itself (see ADR 59 when measured).

## Reuse check
aiolimiter has no latency-driven concurrency; httpx limits are static; tenacity retries but does
not size concurrency. The custom gate was the smallest correct implementation and it did not pay
for itself.
