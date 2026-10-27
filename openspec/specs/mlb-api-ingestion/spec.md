# MLB Stats API Ingestion Specification

## 1. Overview
The MLB Stats API Ingestion Engine extracts, parses, caches, and normalizes official Major League Baseball datasets from `https://statsapi.mlb.com/api` into strongly-typed PyArrow Tables and adaptive multi-target sinks.

---

## 2. Endpoints Covered
The nine hand-written datasets below keep their selected-field schemas; every other endpoint is in the declarative registry (see "Declarative Coverage" at the end), including complete-field twins of these nine.
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
- Raw JSON (with sha256) is stored under `raw/mlb_api/<dataset>/[season=YYYY/]` and typed Parquet under `processed/mlb_api/<dataset>/[season=YYYY/]` (lake layout v2); each part is written atomically and recorded in the dataset manifest, which drives resume.

---

## Declarative Coverage (complete-source-coverage, verified live 2026-10-27)

### Requirement: Endpoint Coverage
Every MLB endpoint MUST be a `MlbEndpoint` (path/params template, record path, fan-out scope, key) with a strict schema generated from live responses (`scripts/gen_mlb_schemas.py`). Reference lists, seasons/sports/leagues/divisions/teams, team affiliates/history/coaches/personnel/alumni, rosters of every roster type, players, free agents, jobs, draft prospects, postseason schedules, hydrated schedules, standings of every standings type, league leaders, league-wide player and team stats for every stat type x group that returns data, and per-game linescore, win probability, play-by-play and live-feed plays/pitch events/linescore/officials MUST be ingestible. Routes that do not respond MUST stay registered as `unsupported` with the probe reason; routes that answer 200 with no records MUST be listed as `empty` in `docs/mlb_probe.json`.

#### Scenario: Pitch events of a final game
- **GIVEN** a final `game_pk`
- **WHEN** `game_feed_play_events` is ingested
- **THEN** each event row carries its plate appearance's context plus `pitch_data_*` (speed, coordinates, breaks, spin, zone) and, for batted balls, `hit_data_*`.

### Requirement: No Field Loss
Nested objects MUST be flattened to dotted keys, arrays kept as JSON text, unknown fields preserved in `_extras` with a one-time drift warning, uncastable cells quarantined, and a payload whose shape contradicts the record path MUST raise.

### Requirement: Bounded Downloads
Paginated stat requests MUST use `limit`/`offset` pages; a request announcing more than 20,000 rows MUST be refused after its first page unless history ingestion is explicitly allowed (all-time stat types ignore the season: `statsSingleSeason fielding` is 191,958 rows). `ingest_season` MUST skip such endpoints by default.

### Requirement: Standings Sentinels
`-` in `gamesBack`/`wildCardGamesBack` is 0 games; `eliminationNumber` `E` is 0 and `-` is NULL; none of these may be quarantined.

### Requirement: Live Streaming (implemented)
The streamer MUST implement `StreamExtractorProtocol` (`stream_events(game_pk, ...)`; the constructor does not own a game), poll `feed/live/timestamps` and apply `feed/live/diffPatch` (RFC 6902) to a local copy of the feed, fall back to the full feed when a patch is unavailable or does not reach the announced timestamp, and accept a full feed document where the server answers a wide window with one. It MUST emit `LiveEvent`s keyed `(game_pk, at_bat_index, event_index)` with microsecond UTC timestamps, emit `game_status` events and end cleanly on `Suspended`, `Postponed`, `Cancelled` and `Final`, back off on `Delayed`, persist a watermark so a later stream of the same game emits only new events, retry network failures through `HttpClient` and then raise (never swallow), quarantine undecodable payloads, and map events onto the `game_feed_play_events` schema (`to_arrow`).

#### Scenario: Suspended game
- **WHEN** the game status becomes `Suspended`
- **THEN** a `game_status` event is emitted and the stream ends
- **AND** a later stream for the same `game_pk` emits only events beyond the stored watermark.

### Requirement: People, Awards and Incremental Endpoints
Per-person stats (`people_stats_<type>_<group>`), award recipients (a 404 for one award MUST be recorded as an empty part and counted, never retried forever and never hidden), `people_changes`/`game_changes` (append-only `updatedSince` logs) and `people_search` MUST be ingestible through the declarative registry.

### Requirement: Completeness
Every stat group listed by `/v1/statGroups`, every sport/level listed by `/v1/sports` (the default of `ingest_season`), every standings type, roster type and game-level resource MUST be ingestible; hand-written datasets that select fields MUST have complete-field twins (`transactions_season`, `draft_picks`, `venues_hydrated`, `game_boxscore_*`). Boxscore players (a dict keyed by player id) MUST be ingested one row per player with their team context. Endpoints for which the generation probe found no records MUST still keep every response as raw JSON, and a later schema generation types them.

### Requirement: All-Time Stat Pools
All-time stat types ignore the season: `ingest_season` MUST skip them, `ingest_history` MUST fetch them once (stored under the run's season), and any paginated request announcing more than 20,000 rows MUST be refused unless explicitly allowed.

### Requirement: Half-Inning Ends
The streamer MUST emit a `half_inning_end` event (once) when a completed plate appearance records the third out (AGENTS.md section 5).

