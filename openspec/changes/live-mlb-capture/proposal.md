# Proposal: live-mlb-capture

## Why
- The owner wants baseballpy to capture, by itself, every piece of data of every MLB game while it is played, keep it
  in the same global lake as everything else, and let other programs (models) read or follow it live.
- Today `baseballpy stream` follows one game at a time and writes to stdout, a JSONL file or a separate DuckDB file.
  Nothing starts games by itself, nothing watches many games, nothing writes into the lake, and nothing is broadcast.
  A finished game reaches the lake only when someone runs `ingest -d games`.

## What changes (four independent slices)
1. **Durable live journal.** Every poll answer (timestamps, diffPatch, full feed) of a live game is appended and
   flushed to a per-game journal in the lake before it is used, so a crash loses nothing and a replay gives the same
   events (same idea as the response log of ADR 95).
2. **Live dataset in the lake.** A new dataset `mlb_api.game_live_events` (own schema from `LiveEvent`, its own view
   `mlb_live_play_events`) written as committed segments while the game runs, readable by DuckDB and
   `baseballpy.read` at once. The canonical game datasets are not touched while the game is live.
3. **`baseballpy live`.** One process, one event loop: a schedule watcher finds games about to start, one task per
   live game shares the HTTP client (rate limit, in-flight gate), a supervisor restarts or stops tasks (stale feed,
   delay, Final), the memory governor gates work, `Ctrl-C` stops cleanly.
4. **Hand-off and broadcast.** At Final the finished-game segment path stores the authoritative game and the live
   rows of that game are dropped from the live dataset (no double count, proved by a test). Local broadcast: a JSONL
   tail file first; Server-Sent Events or a websocket server only after an ADR approves the library.

## Not in this change
- A message broker (NATS, Redis, Kafka): one machine and about 15 games do not need one (design section 4).
- Licensed push feeds of betting-data companies, and the undocumented Baseball Savant `gf` feed.
- Sub-second latency. We promise seconds, not milliseconds.

## Impact
- Specs: `mlb-api-ingestion` (live capture), `lake-access` (the live dataset and its view), `cli-and-ingest`
  (`baseballpy live`). ADRs for the live dataset and for any broadcast library.
- Code: `sources/mlb_api/live/` (supervisor, journal, sink), a `DatasetSpec` for the live table, `cli_live.py`.
- Rollback: the live dataset and command are additive; remove them and nothing else changes.
