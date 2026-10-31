# Design: mlb-live-feed-projection

All numbers below were measured live on 2026-10-31 from this PC with `curl.exe` (the project's user
agent, ADR 40) against game `745000` (a final game, so the whole document is stable and comparable).
The commands are in section 5.

## 1. What the provider does with `fields=`

| Request | Status | Bytes | Time |
|---|---|---|---|
| `feed/live` (complete document) | 200 | 663,043 | 0.33 s |
| `fields=<state set>` (7 key names) | 200 | **141** | 0.19 s |
| `fields=<score set>` (20 key names) | 200 | **368** | 0.17 s |
| `fields=<pitch set>` (40 key names, the current play) | 200 | **4,377** | 0.20 s |
| `fields=<boxscore set>` (12 key names) | 200 | **12,500** | 0.18 s |
| `fields=<decisions set>` (6 key names) | 200 | **94** | 0.20 s |
| `fields=gameData.status.detailedState` (dotted path) | 200 | **2** | – |
| `fields=status,detailedState,linescore,runs` (no parent keys) | 200 | **17** | – |
| `feed/live/timestamps` | 200 | 6,913 | 0.18 s |
| `feed/live/diffPatch` (one step, nothing changed) | 200 | 13 | – |
| `feed/live/diffPatch` (one step, changed) | 200 | ~6,018 | 0.7–1.8 s |
| `feed/live/diffPatch` (wide window, 3 steps) | 200 | 38,541 | 1.7 s |

Four behaviours the design must respect, all measured:

1. **A projection needs every parent key.** `fields=status,detailedState,linescore,runs` returned
   `{"gamePk": ...}` in **17 bytes**: the provider only descends into a branch whose *parent* key is
   also named. Adding `gameData` and `liveData` produced a correct answer; the shipped sets name the
   complete ancestor chain of every path, and the code does the expansion so a caller never has to.
2. **Dotted paths are not a filter.** `fields=gameData.status.detailedState` answered **2 bytes**
   (`{}`). The wire format is a flat list of key names; a dotted path is documentation.
3. **Names match globally, not by path.** A name in the list is emitted wherever that key occurs. This
   is why there is no `plays` set: naming `allPlays` together with `result`/`description` produced
   **144,027 bytes**, only 4.6 times smaller than the complete feed and less useful than the stored
   `game_play_by_play` dataset. The shipped sets are chosen so the names they add cannot pull in a
   whole document branch.
4. **`fields=` is ignored on `diffPatch`.** The same patch answers 38,541 bytes with and without
   `fields`, and its operations address paths outside any plausible projection:
   `/metaData/timeStamp`, `/metaData/logicalEvents/1`, `/liveData/plays/allPlays/62/about/endTime`.
   A projected baseline + unprojected patch is therefore **unsound**: `apply_patch` would raise
   `PatchError` on the first missing path and fall back to the full feed on every poll — strictly
   slower than today's path. This is why the projection is not wired into the stream.

## 2. Field sets as shipped (measured bytes on game 745000)

| Set | Intent | Dotted paths | Key names after expansion | Bytes |
|---|---|---|---|---|
| `state` | is the game live/final, and what is the feed timestamp | 4 | 7 | 141 |
| `score` | inning, half, count, outs and both teams' line for the current game | 17 | 20 | 368 |
| `pitch` | the current plate appearance and its pitch events, including pitch speed, location, breaks and batted-ball data | 27 | 40 | 4,377 |
| `boxscore` | team ids plus both teams' batting runs/hits/home runs (the name match also carries each player's line) | 8 | 12 | 12,500 |
| `decisions` | winner, loser and save pitcher ids | 3 | 6 | 94 |

A set is a tuple of dotted paths in `sources/mlb_api/field_sets.py`; `expand_fields()` walks each path
and adds every parent segment once, preserving order. `gamePk` is added by the provider itself and is
not part of a set.

## 3. Decisions

**D1 — The projection is a snapshot ability, not a streaming mode.** `snapshot()` performs exactly
one request against `feed/live` (optionally at a `timecode`), does not read or write the stream
watermark, and returns the decoded document; `snapshot_bytes()` returns the same response undecoded.
The streaming path keeps complete documents so patches always address existing paths.
`stream_live_events(..., fields=...)` raises `ValueError` naming the reason (ADR 54).

**D2 — Field sets are a table of dotted paths; a bare string is a set name.** `LIVE_FIELD_SETS` is a
`Mapping[str, tuple[str, ...]]` of dotted paths; `DOCUMENT_CONTAINERS = ("gameData", "liveData",
"metaData")` names the branches the guard checks. Resolution rules:

- a `str` with no comma and no dot is a **set name**; an unknown name raises and lists the valid ones
  (the same rule `sources/mlb_api.table()` follows for dataset names, `AGENTS.md` 13.2 and 14.2.3);
- a sequence of strings, or a string containing a comma or a dot, is a **raw projection**;
- to pass one raw key, pass a sequence (or a dotted path), never a bare string.

**D3 — An empty projection is a failure, not a result.** The decoded answer MUST contain every
document container the set names (a `state` set needs `gameData` and `metaData`; a `score` set needs
`gameData` and `liveData`). A missing container raises `SnapshotError`, and the raw bytes go to
quarantine. Silent empty snapshots are exactly the class of bug `AGENTS.md` 7.1 forbids.

**D4 — `timecode` makes the same ability historical.** `feed/live?timecode=` is the provider's own
call; the snapshot sends it unchanged, so a post-game review reads the same shapes as live. A
malformed timecode (not `YYYYMMDD_HHMMSS`) raises before the request.

**D5 — Raw bytes and evidence.** `snapshot_bytes()` returns the undecoded payload. The snapshot is
audit-logged with the projection name (as the destination label) and the elapsed seconds; the byte
counts above are asserted by the live check and recorded here. The audit record has no byte field
today; adding one is a separate change, not a reason to abuse `records_count`.

**D6 — What we take from the other libraries, and what we do not.** MLB-StatsAPI builds
`requests.get(url)` with **no headers and no retry** (read 2026-10-31, `statsapi/__init__.py`,
`def get`); the only idea worth taking is `fields=`. pybaseball does not call this route at all (its
dataset list has no statsapi module; `pybaseball/utils.py` contains no statsapi call), so there is
nothing to borrow for the 406 or the feed.

## 4. As built

Shipped 2026-10-31 in `sources/mlb_api/field_sets.py` (table + `expand_fields`/`required_containers`)
and `GamedayLiveStreamer.snapshot`/`snapshot_bytes` (one request, no watermark, audited as
`mlb_snapshot`/`mlb_snapshot_bytes` with the set name as the destination).

Live check of every set through the shipped API (game 745000, 2026-10-31, one request each, `uv run
python` against the package):

| Set | Status | Bytes | Seconds | Keys returned | Promised values found |
|---|---|---|---|---|---|
| (complete) | 200 | 663,043 | – | `copyright, gamePk, link, metaData, gameData, liveData` | – |
| `state` | 200 | 141 | 0.089 | `gameData, metaData` | `Final`/`Final`/`F`, timestamp `20240623_204225` |
| `score` | 200 | 368 | 0.082 | `gameData, liveData` | inning 9 Top, away 0, home 4 |
| `pitch` | 200 | 4,377 | 0.108 | `liveData` | at-bat 64, batter Nick Loftin, 5 pitches, last CH 88.3 mph at pX −0.289 / pZ 1.639 |
| `boxscore` | 200 | 12,500 | 0.071 | `liveData` | away team 118: 0 runs, 2 hits; home team 140: 4 runs, 10 hits |
| `decisions` | 200 | 94 | 0.082 | `liveData` | winner 453286, loser 679525, save 570632 |

Every set is smaller than the complete document and carries the values it promises; the measured byte
counts are identical to section 1, so the shipped table and the measurement agree. The key counts after
expansion (7 / 20 / 40 / 12 / 6) are asserted in `test_named_field_sets_expand_to_every_parent_key`.

## 5. Reproduction

```
curl.exe -s -o NUL -w "%{http_code} %{size_download} %{time_total}" \
  -A "python-requests/2.32.3" "https://statsapi.mlb.com/api/v1.1/game/745000/feed/live"
curl.exe -s -o NUL -w "%{http_code} %{size_download}" -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1.1/game/745000/feed/live?fields=gameData,status,abstractGameState,detailedState,codedGameState,metaData,timeStamp"
curl.exe -s -o NUL -w "%{http_code} %{size_download}" -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1.1/game/745000/feed/live?fields=gameData.status.detailedState"
curl.exe -s -o NUL -w "%{http_code} %{size_download}" -A "python-requests/2.32.3" \
  "https://statsapi.mlb.com/api/v1.1/game/745000/feed/live/diffPatch?startTimecode=20240623_203942&endTimecode=20240623_204044&fields=gamePk,liveData"
```

## 6. Risks

- A field set can rot when the provider renames keys; the live check in task 1.5 and the
  `SnapshotError` guard turn that into a loud failure, not a quiet empty answer.
- A name that is common in the document (for example `description` or `name`) can pull in a large
  branch; every set is measured, and a set whose answer is not clearly smaller than the full feed is
  not shipped (the `plays` set was dropped for this reason).
- Projections are not cached: the snapshot is a live read. Caching a 368-byte answer per second would
  serve stale scores, which is worse than the request.
