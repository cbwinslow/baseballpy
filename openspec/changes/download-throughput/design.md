# Design: download-throughput

## Decisions
- D1 Measure from the audit log, which already records every request with its time and answer time. The speed report reads the end of the log; it adds no instrumentation to the download.
- D2 Little's law gives the in-flight use: requests per second times the answer time. Below half the allowance with a rate under the cap means idle capacity, so the wait is local. Near the cap means network bound. A 2% or higher share of 429 or 5xx answers means the host is pushing back and nothing should be sped up.
- D3 The speed watch advises and does not tune. Evidence: raising the in-flight limit from 4 to 12 left the rate at 2.9 requests per second and made answers three times slower. An automatic tuner would have raised it and made things worse. Pushing the request rate above the cap is a policy decision (AGENTS.md section 4), not a tuning one.
- D4 The real limit is per-game local work, so the speed-up is in the work, in this order: (1) batch chunk writes (about 20 times fewer file writes on wide tables), (2) cheaper normalization of the live feed (profile first), (3) worker processes. Worker processes break the one-process-per-host rule (`core/hostlock.py`: the caps are per process), so they need an owner decision and a shared rate limit.

## Web check
Python's GIL serializes pure-Python parsing in threads, which fits a flat rate with idle threads. The standard remedies are less Python per record (columnar libraries), fewer and larger writes, or processes. Parquet writers cost per column per row group, which is why a 611-column table is slow in small pieces.

## What the per-game profile found (2026-11-08, real payloads from memory, no network, 40 games)
- Cost per game with an empty lake: 526 ms; with both stores switched off, 414 ms: normalization (flatten the JSON, build typed columns) is most of it and is pure Python.
- Cost per game with each of the 13 processed manifests holding 25,000 entries (what the lake has by the last seasons): 1,114 ms, about what the real download does. Two costs grow with the lake: (1) `ProcessedStore._refuse_name_clash` copied every manifest entry and tested each one at every put; (2) every put rewrote the whole manifest (0.13 s at 29,000 entries), 13 times a game; and the shared tracker cache (24) was smaller than the manifests in use (13 processed plus 13 raw), so a manifest could be parsed again and again.
- After an index for the clash check (a set difference per put), deferred manifest saves in bulk runs (every 500 entries) and a tracker cache of 48: 520 to 630 ms per game at the same manifest size. About twice as fast, and no longer growing with the lake.
- Normalizing in 8 worker processes was tried: 630 to 530 ms per game, and about 2.4 GB more committed memory. Not kept.
- Not the cause of the crashes seen: the Windows commit limit. See the proposal's addendum.

## Evidence
See the proposal. The scripts are throw-away probes (`probe_server.py`, `bench_put.py`, `prof_put.py`); their numbers are recorded here and in ADR 92.

### Task 2.1 Normalization Profile (cProfile on live feed and boxscore payloads, 2026-11-08)
- Sampled real fixture payloads (`game_feed_plays.json`, `game_feed_play_events.json`, `game_boxscore_players.json`):
  - Normalization speed: ~11.5 ms per endpoint (~34.5 ms for the 3-dataset subset; ~150 ms for all 13 endpoints of a complete game).
  - Internal time distribution across 1.726 s (50 iterations of 3 endpoints):
    1. `from_records` (column-by-column value extraction): 0.448 s tottime (1.305 s cumtime, 75.6% of normalization). Dominated by iterating over 42,250 field-value extractions via dict `.get()` (302,400 calls, 0.099 s) and Arrow array building.
    2. `_array` and `safe_array` (type checking and Arrow chunk construction): 0.445 s tottime (0.708 s cumtime, 41.0%).
    3. `_flatten` and `_walk` (nested JSON structure traversal and list serialization): 0.205 s tottime (0.369 s cumtime, 21.4%).
- **Architectural Takeaway:** Normalization CPU time (~150 ms/game) is dwarfed by unbatched filesystem operations (~350–950 ms/game across 13 individual Parquet file writes and 13 manifest atomic updates). Therefore, `batched-chunk-writes` (Task 2.2) targets the true 70–80% bottleneck.
