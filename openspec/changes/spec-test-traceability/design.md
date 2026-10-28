# Design: spec-test-traceability

Method: for each scenario, search `tests/` for the test that exercises the behaviour (grep the function names and fixtures the scenario mentions), read it to confirm it asserts the THEN clause, and cite it. A test that only touches the code path without asserting the outcome does not count: strengthen it or write a new one. The enforcement test parses scenario blocks the same way `scripts/project_map.py` does.

## Findings
(none yet)
