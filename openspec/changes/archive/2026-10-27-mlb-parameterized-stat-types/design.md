# Design: Parameterized MLB Stat Types

- **Probe protocol (ADR 37):** bare request, then one documented parameter at a time; stop at the first that returns splits; record every attempt.
- **Fan-out dimensions:** `sit_codes` from `ref_situation_codes`, `metrics` from `ref_metrics`; `requests_for` yields one request per value and adds the value as an injected column (`sit_code`, `metric`), so the existing per-request key check and `extra` mechanism apply.
- **Sizes:** 602 situation codes x 3 split types x groups is large; the discovery pass first checks whether one request can carry many codes (`sitCodes=a,b,c`) like `leaderCategories`, and only then falls back to one request per code.
- **Audit integration:** a stat type counts as accounted for when it has combinations or an `unsupported` entry with evidence.
- **Risk:** some matchup types need a real opposing id; only documented aggregates are in scope.

## As built (2026-10-27)
- Metric and matchup families are opt-in (`families=("metrics","matchups")`); matchups require opposing ids.
- Added `PROVIDER_ERRORS` (endpoints.py) for requests the provider answers with HTTP 500 for every subject, with evidence; found by the live check (`metricAverages` + pitching + `barreledBall`).
- Decisions: ADR 38. Combination and unsupported counts are generated (`stat_combos.py`), not restated here.
