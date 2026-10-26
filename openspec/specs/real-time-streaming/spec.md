# Real-Time Gameday Streaming Specification

## 1. Overview
The Real-Time Gameday Streaming Engine polls active game feeds from `https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live` and emits discrete, immutable play and pitch events for live analytics, dashboard consumption, and real-time model inference.

---

## 2. Monotonic State Diffing
- Maintains an in-memory watermark `(atBatIndex, eventIndex)`.
- Re-evaluates live feeds on each poll interval, bypassing all already-emitted play events.
- Never emits duplicate pitch or play records.
- Automatically breaks streaming loop when `gameData.status.abstractGameState == "Final"`.

---

## 3. Bandwidth Optimization & Conditional HTTP Headers
- Evaluates `metaData.timeStamp` and HTTP `ETag` (`If-None-Match`).
- When upstream returns `HTTP 304 Not Modified`, skips JSON deserialization and waits for the next poll cycle.
- Deserializes JSON via `msgspec.json.decode()` for single-pass C-speed parsing.

---

## 4. Downstream Event Format
Emits discrete event dictionaries and Arrow record batches containing:
- `game_pk`: Numeric Game ID
- `at_bat_index`, `event_index`: Monotonic sequencing keys
- `is_pitch`: Boolean flag
- `pitch_type`, `start_speed`, `end_speed`: Pitch dynamics
- `sz_top`, `sz_bottom`, `px`, `pz`: Strike zone and trajectory coordinates
- `x`, `y`: Video-space coordinates
- `description`, `call_code`, `event`, `event_type`: Outcome semantics
- `batter_id`, `pitcher_id`, `inning`, `is_top_inning`, `outs`, `balls`, `strikes`: Game state context
- `timestamp`: UTC microsecond timestamp
