# MLB game memory

## Why
On 2026-11-07 the per-game download of 2026 (all levels, about 16,000 games, 13 datasets read in parallel) ended with `MemoryError` after 7.9 hours, while writing a manifest part file (`atomic.py::save`). The major-league default (ADR 85) makes a season five times smaller, but the cause is unknown and a long run could hit it again.

## What changes
Measure the memory of a long game run, find what grows (manifest state, per-game tables kept in threads, request lists), and fix or bound it.
