# Tasks: mlb-api-audit-trail

Order: 3.1 -> 3.2 -> 3.3.

## 1. Verify and pin

- [x] 3.1 `tests/test_mlb_audit.py`: one test per path of `design.md` 2 (declarative endpoint cold and
  cached, hydrate pool fallback, projected snapshot and snapshot bytes, stream success, refused request).
  Done when every test reads the events back with `get_audit_logger().read_events(source="mlb_api")`
  and asserts operation, records, cache flag and status.

- [x] 3.2 `docs/sources/mlb_api.md`: a "Telemetry" section with the operation table and the reader
  commands (`baseballpy audit summary|tail|stats`).
  Done when every operation the code emits is listed once, with what it records.

## 2. Close the change

- [x] 3.3 Merge the delta into `openspec/specs/mlb-api-ingestion/spec.md`, tick the BACKLOG rows, run
  the gates, and move the change to `openspec/changes/archive/<date>-mlb-api-audit-trail/`.
  Done when `openspec validate --specs`, `docs generate --check`, `pytest`, `ruff`, `mypy` are green.
