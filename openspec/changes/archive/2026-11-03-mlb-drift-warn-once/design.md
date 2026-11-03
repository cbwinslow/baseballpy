# Design: mlb-drift-warn-once

Reuse check (TOOLING.md): the once-per-process helper already exists; no new code beyond using it.

## Evidence
- Before: 2,210 `schema_drift` lines in one MLB season run (136 per drifted dataset).
- After: `tests/test_mlb_coverage.py::test_unknown_field_is_warned_about_once_per_dataset_not_once_per_request` (five identical payloads, one warning); related suites 511 passed.
- Not fixed here: the drift itself (new upstream fields such as `numLeagues`, `sport.code`, `player.nameSlug`, `gameType`); they remain in `_extras` until the pool schemas are regenerated (handoff shortcoming 4).
