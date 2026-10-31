# Proposal: An audit event for every MLB Stats API download and ingest

## Why

The telemetry workflow (ADR 22, AGENTS.md 6.1) says every operation that lists, downloads or stores
data writes one structured event to `logs/audit.jsonl`, and a test reads the events back. Retrosheet
(`tests/test_retrosheet_audit.py`) and Statcast
(`tests/test_statcast_coverage.py::test_game_feed_fetches_and_season_ingests_are_audit_logged`) have
that test and a spec requirement. The MLB Stats API has the calls in place — `mlb_api_fetch`,
`mlb_api_cache_read`, `mlb_<endpoint>`, `mlb_snapshot`, `mlb_snapshot_bytes`, `mlb_stream` — but only
two of them are asserted (`mlb_api_cache_read` in `test_sources_hardening.py`, and `mlb_stream` only in
its failure case). A declarative endpoint ingest, the hydrate pool fallback and the projected snapshot
can regress to silent work without any test noticing, and nothing in the docs names the operations a
user should see in `baseballpy audit summary`.

This is a verification and documentation gap, not a behaviour change: the code already tracks every
path (checked call site by call site in `design.md` 1).

## What

- One test module (`tests/test_mlb_audit.py`) that reads the audit log back after each path and asserts
  the operation name, source, records, cache flag, endpoint and destination.
- A spec requirement in `mlb-api-ingestion` mirroring the Retrosheet and Statcast ones, with the test as
  its `Verified by`.
- A short "Telemetry" section in `docs/sources/mlb_api.md` listing the operations, what each records,
  and the CLI commands that read them.

## Out of scope

- Changing what is logged (no new fields, no new operation names unless a path is found untracked; if
  one is, the change records it in `design.md` "As built" before the test asserts it).
- Statcast, Lahman, Chadwick and the sinks; their requirements and tests already exist.
