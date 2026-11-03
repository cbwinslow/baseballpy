# Proposal: retrosheet-parallel-parse

## Problem (measured 2026-11-03, one 2022 season, fresh scratch lake, 56-core machine)
A Retrosheet season takes 236.5 s. The 93 downloads take about 25 s; the remaining ~210 s are
the build steps (events 103 s, daily splits 69 s, box scores 33 s, substitutions 19 s), which
run one after another, and the default `parse_workers = 0` parses in one process, so the run
uses about 1 core of 56. With 16 parse workers the same season took 70.7 s (3.3 times faster)
with identical output in all 15 tables; with 32 workers 87.1 s (slower: each build step starts
and stops its own pool of processes, which costs more with more processes).

## Solution
1. `parse_workers` defaults to the CPU count capped at 32 (the measured best; 48 was no better),
   still overridable; 0 or 1 parses in process.
2. One persistent process pool for the whole run, shared by every parse stream and started once
   (no per-step spawn cost, no hundreds of processes when seasons run at the same time); a stream
   keeps at most 2 x workers files in flight, so memory stays bounded; results keep file order.
3. The independent build steps of a season run at the same time on a small thread pool (their
   heavy work is in the process pool), if the measurement after step 2 shows it still helps.

## Scope
`src/baseballpy/core/config.py`, `src/baseballpy/sources/retrosheet/{pool,api}.py`,
`tests/conftest.py`, `tests/test_retrosheet_pool.py`, spec `retrosheet-ingestion`, docs, ADR 61.
