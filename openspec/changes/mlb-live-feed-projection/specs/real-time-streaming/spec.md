## ADDED Requirements

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
