# Real-Time Gameday Streaming Specification

## Purpose
The streaming engine (`sources/mlb_api/stream.py`, `GamedayLiveStreamer`) follows an active game through `https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live` and emits discrete, immutable `LiveEvent`s for dashboards and live model inference. It implements `StreamExtractorProtocol` (`stream_events(game_pk, ...)`); the constructor does not own a game. `stream_live_events(game_pk)` yields `LiveEvent`s, `stream_events(game_pk)` yields the same as dicts. See ADR 29.

---

## Requirements

### Requirement: Polling
The streamer MUST poll as follows.
- Baseline: one full `feed/live` fetch.
- Afterwards: `feed/live/timestamps` (change codes); when the newest code differs from the local copy's `metaData.timeStamp`, `feed/live/diffPatch?startTimecode=<last>&endTimecode=<newest>` is applied to a local copy as an RFC 6902 patch (`add/remove/replace/move/copy/test`). For wide windows the server returns the complete feed document, which replaces the local copy.
- The full feed (ETag / `metaData.timeStamp` comparison, HTTP 304 skips parsing) is the fallback when `timestamps`/`diffPatch` are unavailable, the patch cannot be applied, or the patched copy does not reach the announced timestamp.
- JSON is decoded with `msgspec`; undecodable payloads are quarantined and polling continues; network failures are retried by the shared `HttpClient` and then raised (audit status `FAILURE`).

#### Scenario: Patch misses the announced timestamp
- **GIVEN** a diff patch whose result does not reach the newest announced timestamp
- **WHEN** the stream applies it
- **THEN** the full feed is fetched instead and no event is lost or repeated.

#### Scenario: Missing diffPatch endpoint
- **WHEN** `feed/live/diffPatch` is unavailable
- **THEN** the stream falls back to the full feed.

---

### Requirement: Events and Watermark
The streamer MUST emit events and persist the watermark as follows.
- Key `(game_pk, at_bat_index, event_index)`; `event_kind` is `pitch`, `pickoff`, `stolen_base`, `substitution`, `action`, `play_result` (once per completed plate appearance, `event_index = -1`), `half_inning_end` (once, on the third out, `event_index = -2`) or `game_status` (`at_bat_index = -1`, `event_index` = status sequence).
- Typed fields: pitch (type, speeds, strike zone, plate location, zone, spin, breaks, plate time, extension), hit (launch speed/angle, distance, trajectory, hardness, location), count, batter/pitcher ids, result text, `ts_utc` and `received_utc` as microseconds since the epoch (UTC); the raw play/event payloads ride along for `to_arrow`.
- `to_arrow(events)` maps events onto the strict `game_feed_play_events` schema through the same flattener as historical ingestion, so live and historical rows share one table and can be upserted.
- A monotonic watermark `{at_bat, event, results_through, status, status_seq, timestamp}` is persisted to `cache/stream/<game_pk>.json` after each change; a later stream of the same game emits only newer events (`resume=False` replays).

#### Scenario: Third out
- **WHEN** a plate appearance records the third out
- **THEN** exactly one `half_inning_end` event is emitted for it.

---

### Requirement: Lifecycle
The streamer MUST follow the game status as follows.
- Waiting states (`Preview`, `Warmup`, ...) poll until `max_inactivity_minutes`; `Delayed` backs off to 30 s.
- `Suspended`, `Postponed`, `Cancelled`, `Final` and `Game Over` emit a `game_status` event and end the stream; a resumed suspended game continues from the watermark.

#### Scenario: Suspended game
- **WHEN** the game status becomes `Suspended`
- **THEN** a `game_status` event is emitted and the stream ends
- **AND** a later stream of the same game emits only events beyond the stored watermark.

#### Scenario: Delayed game
- **WHEN** the status is `Delayed`
- **THEN** polling backs off to 30 seconds.
