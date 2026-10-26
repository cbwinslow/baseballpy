# Change Proposal: MLB Stats API Complete Suite & Real-Time Streaming

## Why
Major League Baseball's official Stats API (`https://statsapi.mlb.com`) is the authoritative source for official schedules, real-time live game state, box scores, standings, rosters, player profiles, transactions, draft, and ballparks.

Existing packages in Python either rely on slow JSON parsing, lack live streaming diffing, or drop key metadata attributes.
To meet our mandates in `AGENTS.md` (ADR 8: Real-Time Gameday Streaming & State Diffing, ADR 12: High-Performance JSON Parsing via `msgspec`, and ADR 15: Full Data Preservation), `baseballpy` must provide an exhaustive, decoupled, and strongly typed client suite for the MLB Stats API.

## What Changes
1. **Exhaustive Endpoint Cataloging:** Document all endpoints, parameters, responses, and physical PyArrow schemas in `docs/sources/mlb_api.md`.
2. **High-Speed Deserialization (`msgspec`):** Define `msgspec.Struct` models in `src/baseballpy/sources/mlb_api/models.py` for C-speed decoding of game feeds and schedule JSON.
3. **Low-Latency Live Streaming (`stream.py`):**
   - Polls `/api/v1.1/game/{game_pk}/feed/live` with conditional HTTP headers (`If-None-Match` / `ETag`).
   - Tracks monotonic watermarks `(atBatIndex, eventIndex)` to emit only new play deltas without redundant parsing.
   - Yields lightweight events (pitches, pickoffs, at-bat outcomes) via async generator.
4. **Exhaustive API Suite (`extractor.py`, `normalizer.py`, `api.py`):**
   - Schedule & Calendar (`/api/v1/schedule`)
   - Official Boxscore (`/api/v1/game/{game_pk}/boxscore`)
   - Game Linescore (`/api/v1/game/{game_pk}/linescore`)
   - Standings & Wild Card (`/api/v1/standings`)
   - Teams & Rosters (`/api/v1/teams`, `/api/v1/teams/{team_id}/roster`)
   - Transactions (`/api/v1/transactions`)
   - Draft (`/api/v1/draft/{year}`)
   - Venues (`/api/v1/venues`)
5. **Multi-Target Sinks (`src/baseballpy/sinks/`):**
   - `PolarsSink`: Eager DataFrame or LazyFrame output.
   - `DltSink`: Adapter yielding Arrow tables as `dlt.resource` for Postgres/Snowflake/BigQuery.
6. **Unified Top-Level Facade:** Expose `bb.mlb.*` and sinks under `baseballpy`.
7. **Testing & Verification:** Comprehensive unit tests in `tests/test_mlb_api.py` and `tests/test_sinks.py`.
