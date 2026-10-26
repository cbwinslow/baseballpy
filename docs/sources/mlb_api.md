# MLB Stats API Endpoint Catalog

## Upstream Overview
- **Provider:** Major League Baseball Advanced Media (MLBAM)
- **Base Endpoint URL:** `https://statsapi.mlb.com`
- **Method:** `GET`
- **Response Format:** JSON
- **Rate Limit Policy:** Max 8.0 requests/second
- **Optimization Strategy:** HTTP/2 persistent connection pooling, client-side conditional caching with `ETag` and `timecode`.

---

## Core Endpoints

### 1. Schedule & Game Index
- **Endpoint:** `/api/v1/schedule`
- **Parameters:**
  - `sportId=1` (Major League Baseball)
  - `startDate=YYYY-MM-DD`
  - `endDate=YYYY-MM-DD`
  - `hydrate=team,probablePitcher,lineups`
- **Output:** Games schedule, official `game_pk` IDs, venue details, game status lifecycle (`Preview`, `In Progress`, `Final`).

### 2. Live Gameday Feed & Play-by-Play
- **Endpoint:** `/api/v1.1/game/{game_pk}/feed/live`
- **Parameters:**
  - `timecode=YYYYMMDD_HHMMSS` (Optional delta query parameter)
- **Output:** Deeply nested JSON tree containing `liveData.plays.allPlays`, current play events, pitches, trajectories, and box score state.

### 3. Boxscores
- **Endpoint:** `/api/v1/game/{game_pk}/boxscore`
- **Output:** Official game box score with full player stat lines (batting, pitching, fielding).

### 4. Team Rosters & Transactions
- **Endpoint:** `/api/v1/teams/{team_id}/roster`
- **Endpoint:** `/api/v1/transactions`
- **Output:** 40-man and active 26-man rosters, injured list moves, options, waivers, and trades.
