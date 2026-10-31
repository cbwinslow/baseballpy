# Proposal: A projected live-feed snapshot (the provider's `fields=` parameter)

## Why

The live Gameday feed (`/api/v1.1/game/{game_pk}/feed/live`) answers 200 but its full document is
**663,043 bytes in 0.33 s** (measured 2026-10-31, game 745000). Our streamer already avoids re-reading
it: `timestamps` (6,913 B) plus a one-step `diffPatch` (~6 KB) brings an update in under a second
(`real-time-streaming` spec, ADR 29).

Two gaps remain for in-game use:

1. **A one-shot read is expensive.** Anything that wants "the score right now" (a dashboard, a model
   feature build, a health check) pays the whole 663 KB, because we always request the complete feed.
2. **The provider has a projection parameter we never use.** `fields=` selects which keys the answer
   carries. Measured on the same feed: **663,043 B → 368 B** for the shipped score set and **141 B** for
   the game state alone. That is the cheapest capability in the provider and we do not expose it.

The obvious idea — add `fields=` to the streaming loop — was tested and is **wrong** (see
`design.md`): `diffPatch` ignores `fields` and its operations address paths such as
`/liveData/plays/allPlays/62/about/endTime` and `/metaData/timeStamp`, which a projected baseline does
not contain. Applying such a patch to a projected document fails and drops the stream back to full
feeds on every poll, which is slower than what we have. So the projection is added as its **own**
ability with its own contract, and the patch path is left alone.

## What

- A declarative field-set table (data, not code) of five named projections (`state`, `score`, `pitch`,
  `boxscore`, `decisions`), each a tuple of dotted paths; the code expands every path to the parent keys
  the provider requires and keeps the set addressed by name.
- `GamedayLiveStreamer.snapshot(game_pk, fields=..., timecode=...)` returning the decoded document,
  plus `snapshot_bytes()` for callers that keep raw upstream bytes.
- A hard rule in the contract: a projection is **never** combined with patch polling
  (`stream_live_events` refuses a projection rather than silently degrading).
- A guard: a projected answer that lacks its container raises, so nobody gets an empty snapshot
  believing it is the game state.
- Live verification of every named set, with the measured bytes recorded in `design.md`.

## Out of scope

- Changing the streaming/patch algorithm (it is already the fast path).
- Re-fetching or re-typing the historical feed (`game_play_by_play`, `game_linescore`).
- Borrowing request headers or retry logic from MLB-StatsAPI: that library sends no headers at all and
  has no retry; `fields=` is the one thing in it we did not already have.
