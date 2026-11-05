# Code tightening (behaviour-preserving)

## Why
The owner asked for a tightening pass while the MLB backfill runs (2026-11-05). `ruff` with a complexity limit of 15 flags 7 functions: `ingest_cmd`, `migrate.retrosheet`, `run_jobs`, `parse_seasons`, `requests_for`, `parse_box_text`, `StatcastAdapter.run`.

## What changes
Each flagged function is split into small named helpers. Output, error messages and downloaded data stay identical; the existing tests are the proof. One function (or one pair) per commit, all gates after each, nothing that changes what a running or future download writes.

## Out of scope
New features, schema changes, renamed datasets, anything under `core/stores.py` write paths.
