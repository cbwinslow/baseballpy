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
- Verified by `tests/test_mlb_stream.py::test_patch_that_misses_the_announced_timestamp_falls_back_to_the_full_feed`.

#### Scenario: Missing diffPatch endpoint
- **WHEN** `feed/live/diffPatch` is unavailable
- **THEN** the stream falls back to the full feed.
- Verified by `tests/test_mlb_stream.py::test_missing_diff_patch_endpoint_falls_back`.

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
- Verified by `tests/test_mlb_stream.py::test_third_out_emits_a_half_inning_end_once`.

---

### Requirement: Lifecycle
The streamer MUST follow the game status as follows.
- Waiting states (`Preview`, `Warmup`, ...) poll until `max_inactivity_minutes`; `Delayed` backs off to 30 s.
- `Suspended`, `Postponed`, `Cancelled`, `Final` and `Game Over` emit a `game_status` event and end the stream; a resumed suspended game continues from the watermark.

#### Scenario: Suspended game
- **WHEN** the game status becomes `Suspended`
- **THEN** a `game_status` event is emitted and the stream ends
- **AND** a later stream of the same game emits only events beyond the stored watermark.
- Verified by `tests/test_mlb_stream.py::test_suspended_game_is_emitted_ends_and_resumes_from_the_watermark`.

#### Scenario: Delayed game
- **WHEN** the status is `Delayed`
- **THEN** polling backs off to 30 seconds.
- Verified by `tests/test_mlb_stream.py::test_delayed_game_backs_off_and_waiting_states_are_bounded`.


### Requirement: Projected Snapshot of a Game
`GamedayLiveStreamer.snapshot(game_pk, fields=None, timecode=None)` MUST perform exactly one request
against `the game's feed/live` and return the decoded document; it MUST NOT read or write the stream
watermark. `snapshot_bytes()` MUST return the upstream bytes of the same request. `fields=None` MUST
request the complete document. A `timecode` MUST be sent unchanged and MUST match `YYYYMMDD_HHMMSS`
before the request is made.

#### Scenario: A score snapshot
- **WHEN** `snapshot(game_pk, fields="score")` is called for a game
- **THEN** one request answers 200 and the document carries the game status and both teams' runs
- **AND** no stream watermark file is created or read
- Verified by `tests/test_mlb_stream.py::test_snapshot_returns_the_projected_score_in_one_request`.

#### Scenario: A snapshot at a timecode
- **WHEN** `snapshot(game_pk, fields="score", timecode="20240623_183855")` is called
- **THEN** the request carries `timecode=20240623_183855` and the decoded document is returned
- Verified by `tests/test_mlb_stream.py::test_snapshot_with_a_timecode_reads_the_historical_feed`.

#### Scenario: A malformed timecode
- **WHEN** `snapshot(game_pk, timecode="yesterday")` is called
- **THEN** `SnapshotError` is raised before any request is sent
- Verified by `tests/test_mlb_stream.py::test_a_malformed_timecode_is_refused_before_the_request`.

### Requirement: Field Sets Are Registry Data
Named projections MUST come from the declarative `LIVE_FIELD_SETS` table of dotted paths, not from
code branches. A bare string MUST be resolved as a set name; an unknown set name MUST raise an error
that lists the valid names. A sequence of keys or a comma/dotted string MUST be accepted as a raw
projection. Every dotted path MUST expand to all of its parent key names, because the provider only
descends into a branch whose parent is named, and the wire format MUST be a flat list of key names.

#### Scenario: A named set expands to every parent key
- **WHEN** the `score` set is resolved
- **THEN** the wire projection contains `gameData`, `liveData`, `linescore`, `teams`, `away`, `home`
  and `runs`, and contains each key once
- Verified by `tests/test_mlb_stream.py::test_named_field_sets_expand_to_every_parent_key`.

#### Scenario: An unknown set name
- **WHEN** `fields="scroe"` is passed
- **THEN** the error lists `state`, `score`, `pitch`, `boxscore` and `decisions`
- Verified by `tests/test_mlb_stream.py::test_an_unknown_field_set_lists_the_valid_names`.

### Requirement: A Projection Is Never Patched
The streaming path MUST keep complete documents so `diffPatch` operations always address existing
paths. Requesting a projection from `stream_live_events` or `stream_events` MUST raise `ValueError`
that names the reason and points at `snapshot()`; it MUST NOT be silently ignored and MUST NOT degrade
the stream to a full feed on every poll.

#### Scenario: A projection on the stream
- **WHEN** `stream_live_events(game_pk, fields="score")` is consumed
- **THEN** `ValueError` is raised before the first request, naming `diffPatch` and `snapshot`
- Verified by `tests/test_mlb_stream.py::test_streaming_refuses_a_projection_instead_of_degrading`.

### Requirement: An Empty Projection Is a Failure
A decoded snapshot MUST contain every document container its projection names (`gameData`, `liveData`
or `metaData`). A payload that does not decode, is not an object, or lacks a required container MUST
raise `SnapshotError` and MUST be written to quarantine with the game id; it MUST NOT be returned as
an empty or partial snapshot.

#### Scenario: A projection without its container
- **WHEN** the provider answers a projected request with only `gamePk`
- **THEN** `SnapshotError` names the missing container and the raw bytes are quarantined
- Verified by `tests/test_mlb_stream.py::test_a_projection_that_lacks_its_container_raises_and_is_quarantined`.
