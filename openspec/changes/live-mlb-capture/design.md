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

## 5. The one decision (owner): where do live rows land?
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
queue stalls polling), Final hand-off row for row equal to a batch ingest of the same game. One in-season live check
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
