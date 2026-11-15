# Tasks: live-mlb-capture

Order: 0.1 first (owner decision), then slices 1 to 4 in order. Each slice is useful alone.

- [ ] 0.1 Owner decision: live rows in a separate dataset (A, recommended) or in the canonical table (B); ADR recorded.
  Done when the ADR exists and design section 5 says which.
- [ ] 1.1 Tests first: `tests/test_live_journal.py` (every poll answer is on disk before it is used; a replay gives
  the same events; a torn last record is cut safely; a restart never repeats an event).
  Done when the tests fail for the missing journal.
- [ ] 1.2 `sources/mlb_api/live/journal.py` and wiring in the streamer; spec delta with `Verified by`.
  Done when 1.1 passes and `tests/test_mlb_stream.py` still passes.
- [ ] 2.1 Tests first: `tests/test_live_segments.py` (a DuckDB query sees rows mid-game; no double count after a
  crash and restart; schema equals the registered one; the view and docs come from the registry).
- [ ] 2.2 Register `mlb_api.game_live_events`, the live segment writer, the view `mlb_live_play_events`, generated
  docs. Done when 2.1 passes, `docs generate --check` and `openspec validate --specs` pass.
- [ ] 3.1 Tests first: `tests/test_live_supervisor.py` (two fixture games on a fake clock, a restart in the middle,
  a stale feed stops, a rain delay backs off, a slow sink stalls polling, Ctrl-C stops cleanly).
- [ ] 3.2 `baseballpy live` (schedule watcher, task per game, supervisor, memory gate, audit records).
  Done when 3.1 passes and `docs/CLI.md` is regenerated.
- [ ] 3.3 In-season check on real games (owner machine): latency measured, request rate, no 429; the numbers go
  into design section 1; the websocket probe result is recorded.
- [ ] 4.1 Tests first: `tests/test_live_handoff.py` (after Final the game equals a batch ingest of the same game
  row for row; live rows of that game are gone; a crash during hand-off is repaired on restart).
- [ ] 4.2 Hand-off at Final and the JSONL tail broadcast; ADR for any websocket or SSE library, if wanted.
  Done when 4.1 passes and the broadcast is documented in `docs/QUICKSTART.md`.
