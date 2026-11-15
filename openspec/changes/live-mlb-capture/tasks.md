# Tasks: live-mlb-capture

Order: 0.1 first (owner decision), then slices 1 to 4 in order. Each slice is useful alone.

- [x] 0.1 Owner decision (2026-11-15): live rows in a separate dataset, the regular ingest stores the game later; ADR 137.
  Done: ADR 137 and design section 5.
- [x] 1.1 Tests first: `tests/test_live_journal.py` (every poll answer is on disk before it is used; a replay gives
  the same events; a torn last record is cut safely; a restart never repeats an event).
  Done when the tests fail for the missing journal.
- [x] 1.2 `sources/mlb_api/live/journal.py` and wiring in the streamer; spec delta with `Verified by`.
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
- [ ] 4.1 Tests first: `tests/test_live_open_view.py` (the view `mlb_live_events_open` never shows a game that is in
  `game_feed_plays`; a game stored a moment after its live rows still counts once; a crash before the game is stored
  leaves it in the open view; a prune of stored games older than N days changes no query result).
- [ ] 4.2 The view, the optional prune, the optional automatic call of `ingest_game_segments` for a game at Final,
  and the JSONL tail broadcast; ADR for any websocket or SSE library, if wanted.
  Done when 4.1 passes and the workflow (live, then the regular ingest) is documented in `docs/QUICKSTART.md`.
