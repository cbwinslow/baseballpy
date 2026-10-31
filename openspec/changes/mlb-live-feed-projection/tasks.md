# Tasks: mlb-live-feed-projection

Order: 1.1 -> 1.2 -> 1.3 can land together; 1.4 needs 1.1 and 1.2; 1.5 closes the change.

## 1. The projection ability

- [ ] 1.1 `sources/mlb_api/field_sets.py`: `LIVE_FIELD_SETS` (the five measured sets of dotted
  paths), `DOCUMENT_CONTAINERS`, `set_name()`/`expand_fields()` and `required_containers()`.
  A bare string is a set name (unknown -> `ValueError` listing the valid names); a sequence or a
  comma/dotted string is a raw projection; every parent segment is added once, in order.
  Tests in `tests/test_mlb_stream.py`:
  `test_named_field_sets_expand_to_every_parent_key`,
  `test_an_unknown_field_set_lists_the_valid_names`,
  `test_a_raw_projection_is_accepted_as_a_sequence_or_a_comma_string`.
  Done when the tests pass and every shipped set expands to the key names measured in `design.md`.

- [ ] 1.2 `GamedayLiveStreamer.snapshot(game_pk, fields=None, *, timecode=None)` and
  `snapshot_bytes(...)`: one request, no watermark read/write, `fields=None` = the complete feed,
  `timecode` validated as `YYYYMMDD_HHMMSS`, audit event with the projection name and elapsed seconds,
  `SnapshotError` + quarantine when the payload does not decode or lacks a required container.
  Tests: `test_snapshot_returns_the_projected_score_in_one_request`,
  `test_snapshot_with_a_timecode_reads_the_historical_feed`,
  `test_snapshot_bytes_returns_the_upstream_bytes`,
  `test_a_projection_that_lacks_its_container_raises_and_is_quarantined`,
  `test_a_malformed_timecode_is_refused_before_the_request`.
  Done when the tests pass with a recorded fixture and no test makes a network call.

- [ ] 1.3 `stream_live_events(..., fields=...)` and `stream_events(..., fields=...)` MUST raise
  `ValueError` naming the reason and pointing at `snapshot()`; the error is never swallowed.
  Test: `test_streaming_refuses_a_projection_instead_of_degrading`.
  Done when the test passes and the message names `diffPatch` and `snapshot`.

- [ ] 1.4 Live check of all five sets on a final game (game 745000 is the reference): status, bytes and
  the values of the keys the set promises (status text, both teams' runs, current-play pitch speed,
  decisions ids). Record the numbers under "As built" in `design.md`; a set the provider answers empty
  is removed or fixed before the change closes.
  Done when every set is 200, smaller than the complete feed, and its promised keys are populated.

## 2. Close the change

- [ ] 1.5 Docs and close-out: a "Projected snapshots" section in `docs/sources/mlb_api.md` (the five
  sets, the measured bytes, the rule that a projection is never patched); ADR 54 (written 2026-10-31);
  merge this delta into `openspec/specs/real-time-streaming/spec.md`; move the change to
  `openspec/changes/archive/<date>-mlb-live-feed-projection/`; update the BACKLOG rows.
  Done when `openspec validate --specs`, `docs generate --check` and the four gates are green and the
  change is archived.
