# Design: live-mlb-capture

## 1. Is it possible, and how fast? (research, 2026-11-15)
- MLB serves the live game at `statsapi.mlb.com/api/v1.1/game/{pk}/feed/live`, with `/timestamps` (tiny: "did it
  change?") and `/diffPatch?startTimecode=` (a JSON patch between two timestamps). `stream.py` already polls this way
  (ADR 54). Community tools poll about every 3 s; a source warns that one request per second from many clients gets
  public endpoints closed.
- Community Go tools also open a websocket at `ws.statsapi.mlb.com` (a "gameday push") and use each push only as a
  signal to call diffPatch; they reconnect on unexpected close. This is UNVERIFIED (no official documentation; the
  path and message fields were not seen). Plan: try it in season, as an optional wake-up; polling stays the floor.
- Betting-data companies (Sportradar, Genius Sports) sell licensed push feeds (WebSocket or gRPC, claimed under one
  second) produced by scouts and tracking at the stadium. Industry guides describe push for live events, pull for
  the rest, bounded queues and an automatic "suspend markets" step. We cannot buy that here and do not need it.
- Honest promise for the public feed: the official scorer's data about 2 to 10 seconds after the play (two reviewers
  disagreed on the number: measure it in season, task 3.3). Every pitch, play, count, runner, coordinate and status
  change in the feed is captured; the 300 fps optical tracking is not on public endpoints.

## 2. Load
15 MLB games at once, one `timestamps` call each every 3 s, plus a `diffPatch` when something changed: about 5 to 10
requests per second at peak, under 50 KB/s. Minor-league levels (about 5 times more games) are opt-in with a longer
interval. `HttpClient` already has a per-host token bucket, an in-flight gate, a 429/503 host pause and `Retry-After`.

## 3. Shape (one process, no new service)

    schedule watcher (every 60 s: schedule_hydrated for today)
            | game about to start
            v
    supervisor --one asyncio task per live game--> GamedayLiveStreamer (exists)
       | restart / stale-feed stop / Final / shutdown     | poll answers
       |                                                  v
       |                          live journal (append + fsync, crc framed)      [slice 1]
       |                                                  | events
       |                                                  v
       |              bounded queue (about 50: a slow disk slows polling, memory stays flat)
       |                                                  v
       |              live segment writer: commit every N seconds -> game_live_events   [slice 2]
       v                                                  |
    MemoryGovernor gate                                   +--> JSONL tail file (broadcast v1)   [slice 4]
                                                          +--> optional SSE / websocket (needs an ADR)
    at Final: ingest_game_segments([pk]) stores the authoritative game; live rows of pk are dropped   [slice 4]

Rules kept: sources meet the rest only through `IngestAdapter` and `SinkProtocol`; the table, view and docs come from
the dataset registry; atomic write then one commit line; an audit record per poll; no swallowed exceptions.

## 4. Build or buy
No broker. NATS, Redis Streams and Kafka add fan-out, retention and cross-machine scale; we have one writer, one
machine, tens of events per second, and the lake is the durable store. A broker would be a service every PyPI user
must install. Revisit only if someone needs many remote subscribers.

## 5. DECIDED (owner, 2026-11-15, ADR 137): live rows land in a separate table; the normal ingest stores the game later

The owner chose option A and asked for no complex stop measure. Thought through:

- **Same schema, separate table (corrected 2026-11-15).** `to_arrow` already gives a live pitch or action event the
  exact schema of `game_feed_play_events` (the historical flattener runs on the live play); `play_result` and
  `game_status` events have no row there. So `game_live_events` uses that schema and a model can `UNION ALL BY NAME`
  history and `mlb_live_events_open`. The first draft of this section said the shapes differ; that was wrong for pitch
  and action events and the decision does not depend on it. Separate tables stay because of the next point and
  because a half game must never sit in a table models read.
- **No double count without deleting anything.** The finished-game ingest stores a game completely or not at all (a
  game counts as stored only when its line is in `segments.json`, ADR 95). So "is this game in the long-term table?" is
  an exact yes or no. The view `mlb_live_events_open` is the live table minus games already in `game_feed_plays`
  (an anti-join on `game_pk`). A model reads history from the long-term tables and in-progress games from the open
  view; the two never overlap, whatever the timing, a crash or a late ingest. Nothing has to be dropped for the numbers
  to be right.
- **Housekeeping, not correctness.** `baseballpy live` may prune live rows of games that are already stored and older
  than a few days (default 7). Skipping the prune changes nothing but disk. The raw journal is never pruned.
- **The ingestor stays the one source of truth for finished games.** Nothing new stores long-term data. After a game,
  the regular `baseballpy ingest mlb_api -d season,games` (or the optional automatic call of the same
  `ingest_game_segments` for that game_pk once the status is Final) stores it. If `live` is not running, or crashes, the
  next regular ingest catches up; it is idempotent.
- **Known limit, same as today:** a game is stored once when it is Final; later scoring corrections need the usual
  `--refresh`. Live capture does not change that.
- **Statcast pitch rows are separate.** The live table is MLB API data; Statcast pitches reach the lake through
  `ingest statcast` later, as now.

Alternative B (straight into the canonical table) rejected: different shapes, replacing rows the writer did not write,
half games after a crash.

### 5.1 Earlier text of this section (options)
- **A. Separate live dataset.** Pro: the canonical tables never hold half a game; easy to explain and roll back.
- **B. Straight into `game_feed_play_events`.** Pro: one table. Con: see above.
- **A. Separate live dataset (recommended).** `game_live_events` and its own view; dropped per game when the final
  game is stored. Pro: the canonical tables never hold half a game; no double count; easy to explain and to roll
  back. Con: a model that wants "live plus history" in one query unions two views (we ship a helper view).
- **B. Straight into the canonical `game_feed_play_events`.** Pro: one table. Con: the finished-game path must then
  replace rows it did not write, a crash can leave half a game in the canonical table, and "same results for every
  user" is harder to prove.

## 6. Broadcast
First a JSONL tail file (no dependency; any language can follow it). SSE or a websocket server next: `websockets`,
FastAPI and Starlette are not on the approved list of `docs/agents/TOOLING.md`, so that needs an ADR with the reuse
check. Local only by default (127.0.0.1).

## 7. Tests (no live games needed)
Replay recorded feeds and the real patch fixtures of `tests/fixtures/mlb/` against a fake clock: two games at once, a
restart in the middle (no duplicate and no gap), a stale feed, a rain delay, a torn journal record, a slow sink (the
queue stalls polling), the open view never shows a stored game. One in-season live check
per slice (owner's machine, real games).

## 8. Open questions
- The websocket path and messages (probe once in season).
- Whether Baseball Savant's `gf` feed is allowed and worth using (terms unknown; not planned).

## 9. Second opinions (2026-11-15)
Gemini (`gemini-3.8-flash-medium`) and OpenCode (`glm-5.3-flash-free`) both read the code and agreed on: no broker, one
asyncio loop with a task per game on the shared `HttpClient`, a durable journal first, a live segment the lake can
read mid-game, hand-off to the finished-game path at Final, JSONL tail before any websocket. They differ on latency
(2 to 4 s versus 5 to 10 s) and both put the same single question to the owner (section 5). Claude Opus was not used
(usage budget).

## 10. Evidence (filled in as tasks land)

### 10.1 Slice 1, the live journal (tasks 1.1 and 1.2, 2026-11-15)
`tests/test_live_journal.py` (8 tests, written before the code) pass: each decoded answer is already in the journal; a
replay gives the same events as the live run, also with a refused status; a torn last record is cut, logged and new
records follow whole ones; a restart continues one journal with no gap and no repeated event; a replay leaves the resume
state untouched; the audit record names the journal and the replay logs as `mlb_stream_replay`; the layout audit ignores
the folder. `tests/test_mlb_stream.py` (existing streamer tests) still passes. Reuse check: `core/responselog.py` record
format and `read_journal` (torn-tail rule), `HttpClient` (rate limit, retries, gate), `msgspec` (existing events),
`pydantic-settings` (`StreamingConfig.journal`), `core/audit.py`. Custom code: the per-answer wrapper and the replay
client, because no existing helper journals HTTP answers per game. As built: the replay client raises
`JournalExhaustedError` at the end of a journal that stopped before the game ended; a cut journal therefore logs one audit
`FAILURE` for the replay operation. Not verified: a real live game (off-season); the journal write cost with 15 games at
once (task 3.3).

### 10.2 Slice 2, the live dataset (tasks 2.1 and 2.2, 2026-11-15)
`tests/test_live_segments.py` (10 tests, written first; the module was missing so they failed at collection) pass:
registered with the history schema and keys; readable through a DuckDB view and `baseballpy.read` mid-game; a restart
that sends events again does not double count; one file per game and a rewrite leaves the others byte-identical; the file
has exactly the registered columns; a failed write leaves the old file and no `.part`; non-row events add nothing; fifteen
live files give a clean `catalog layout`; an empty write creates no file. As built: the layout audit skips `live-*` files
for the tiny-file and row-group rules (ADR 139); the open-games view is task 4.2. Reuse check: `atomic_write_parquet`
(atomic replace with a footer check), `to_arrow` (the historical flattener), the dataset registry and generated docs,
pyarrow `group_by` (one row per key). Custom code: `last_row_per_key` and the per-game sink, because no store merges
rewritten per-game files. Not verified: write cost and file counts over a season (task 3.3).

### 10.3 Slice 3, the supervisor and `baseballpy live` (tasks 3.1 and 3.2, 2026-11-15)
Tests (written first; the modules were missing so they failed at collection): `tests/test_live_supervisor.py` (11),
`tests/test_live_schedule.py` (3), `tests/test_live_cli.py` (3) and `tests/test_live_e2e.py` (1: two fixture games through the
real streamer with the journal on, the supervisor, the sink and a DuckDB query, then replay from the journals). Found by the
tests: the first draft of the writer drained the queue into unbounded buffers while the sink was stuck, so polling did not
stall; the writer now also flushes when a game's buffer reaches `queue_size`. Found by the end-to-end test: with the real
`HttpClient` (it runs requests on its own loop thread) a run that stops before the games finish cancels them, as designed;
the test stops only when both games are done. Reuse check: `HttpClient` (rate limit, retries, gate), `MemoryGovernor`
(ADR 114), `StreamingConfig` (pydantic-settings), `core/audit.py`, `LiveGameSink`, click and rich. Custom code: the
supervisor loop and the schedule parser (nothing in the repository watches a schedule and follows games). Not verified:
real games, real request rate and latency, the websocket probe (task 3.3, in season).
