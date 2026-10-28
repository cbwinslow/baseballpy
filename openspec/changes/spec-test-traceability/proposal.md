# Proposal: Every spec scenario names the test that proves it

## Why
`openspec validate --specs` checks that each requirement has a scenario, and `tests/test_spec_scenarios.py` checks that cited tests exist, but nothing requires a scenario to cite one. On 2026-10-28, 39 of 89 scenarios (in 12 of 14 specs; `core-protocols` and `real-time-streaming` cite none) had no "Verified by" line, so a spec could claim behaviour no test checks.

## What changes
- Every scenario ends with `- Verified by `tests/<file>.py::<test>``, naming a test that fails if the behaviour breaks. Where no test exists, write the test first (mocked, no network); where the behaviour is only checkable live, cite the `tests/live/` test; if neither is possible, remove the claim from the spec.
- `tests/test_spec_scenarios.py` fails for any scenario without a citation.

## Not in scope
New requirements or behaviour: this only aligns the specs with what is tested.
