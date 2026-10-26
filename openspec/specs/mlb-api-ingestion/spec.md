# MLB Stats API Ingestion Specification

## 1. Overview
The MLB Stats API Ingestion Engine extracts, parses, caches, and normalizes official Major League Baseball datasets from `https://statsapi.mlb.com/api` into strongly-typed PyArrow Tables and adaptive multi-target sinks.

---

## 2. Endpoints Covered
1. **Schedule & Calendar (`/v1/schedule`):**
   - Game Pk primary numeric keys, scheduled dates, doubleheaders, game type classifications (`R`, `P`, `S`), lifecycle statuses (`S`, `I`, `F`, `D`), home/away teams, and venues.
2. **Official Boxscores (`/v1/game/{game_pk}/boxscore`):**
   - Game-by-game batting and pitching box scores with full individual stat lines.
3. **Standings & Rankings (`/v1/standings`):**
   - Division and wild card standings, wins, losses, winning %, games back, run differential, and streaks.
4. **Teams & Rosters (`/v1/teams`, `/v1/teams/{team_id}/roster`):**
   - Active MLB franchises, minor league circuits, active 26-man and 40-man rosters, and injured list designations.
5. **Transactions (`/v1/transactions`):**
   - Roster moves, options, outright waivers, trades, and injured list transactions.
6. **First-Year Player Draft (`/v1/draft/{year}`):**
   - Draft rounds, picks, players, signing bonuses, and school origins.
7. **Venues (`/v1/venues`):**
   - Ballpark dimensions, capacities, turf types, and roof configurations.

---

## 3. Concurrency, Rate Limiting & Network Pooling
- Host rate limit: 8.0 requests/second enforced via `aiolimiter.AsyncLimiter`.
- Persistent connection pooling with HTTP/2 enabled (`httpx.AsyncClient(http2=True)`).
- Exponential jitter backoff via `tenacity` on transient HTTP failures.

---

## 4. Two-Phase Atomic Caching
- All Parquet datasets write through `atomic_write_parquet()` under `~/.baseballpy/cache/mlb_api/`.
- Manifest tracks partition status via `manifest.json`.
