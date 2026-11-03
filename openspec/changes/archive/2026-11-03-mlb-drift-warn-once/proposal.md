# Proposal: mlb-drift-warn-once

## Problem
The `mlb-api-ingestion` spec says unknown fields are kept in `_extras` "with a one-time drift
warning", but the MLB normalizer logged the warning for every request. A 2024 season run wrote
2,210 identical `schema_drift` lines, which hides real warnings (found while watching the live
run log, 2026-11-03).

## Solution
Use the shared `warn_drift_once` helper (already used by Chadwick, Lahman and Retrosheet) in the
MLB normalizer, so each dataset and field is reported once per process. No data changes: the
fields stay in `_extras`.

## Scope
`src/baseballpy/core/schema_tools.py` (helper made public), `src/baseballpy/sources/mlb_api/generic.py`,
`tests/test_mlb_coverage.py`, the `Verified by` line of the existing scenario.
