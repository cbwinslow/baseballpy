# Proposal: Savant leaderboards and Retrosheet reference files under the lake contract

## Why

`download-lake-contract` (ADR 105) proves the lake shape for Statcast pitches, Retrosheet seasons, Chadwick,
Lahman and MLB. Row B-433 listed the sources still outside it. Two are core to the MLB library and cheap to add:
the Savant leaderboards (each supported variant is its own dataset) and Retrosheet's reference ingest.

## What

Two additions to `tests/test_download_contract.py`: every supported Savant leaderboard for one season from its
recorded page, and `ingest_reference()` in the Retrosheet test. Measured 2026-11-11: both pass the contract on
the current code, before and after compaction, so no production change is needed.

The Kalshi, Polymarket, FanGraphs and Baseball-Reference sources stay deferred with their other rows
(ADR 102); B-433 is narrowed to them.

## Out of scope

Changing any layout; the deferred sources.
