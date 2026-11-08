# Design: download-throughput

## Decisions
- D1 Measure from the audit log, which already records every request with its time and answer time. The speed report reads the end of the log; it adds no instrumentation to the download.
- D2 Little's law gives the in-flight use: requests per second times the answer time. Below half the allowance with a rate under the cap means idle capacity, so the wait is local. Near the cap means network bound. A 2% or higher share of 429 or 5xx answers means the host is pushing back and nothing should be sped up.
- D3 The speed watch advises and does not tune. Evidence: raising the in-flight limit from 4 to 12 left the rate at 2.9 requests per second and made answers three times slower. An automatic tuner would have raised it and made things worse. Pushing the request rate above the cap is a policy decision (AGENTS.md section 4), not a tuning one.
- D4 The real limit is per-game local work, so the speed-up is in the work, in this order: (1) batch chunk writes (about 20 times fewer file writes on wide tables), (2) cheaper normalization of the live feed (profile first), (3) worker processes. Worker processes break the one-process-per-host rule (`core/hostlock.py`: the caps are per process), so they need an owner decision and a shared rate limit.

## Web check
Python's GIL serializes pure-Python parsing in threads, which fits a flat rate with idle threads. The standard remedies are less Python per record (columnar libraries), fewer and larger writes, or processes. Parquet writers cost per column per row group, which is why a 611-column table is slow in small pieces.

## Evidence
See the proposal. The scripts are throw-away probes (`probe_server.py`, `bench_put.py`, `prof_put.py`); their numbers are recorded here and in ADR 92.
