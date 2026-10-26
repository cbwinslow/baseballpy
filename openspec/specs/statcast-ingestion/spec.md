# Statcast Ingestion Specification

## 1. Overview
The Statcast Ingestion Engine extracts, chunks, normalizes, and caches pitch-by-pitch tracking datasets and 11 analytical leaderboards from Baseball Savant (`https://baseballsavant.mlb.com`).

---

## 2. Ingestion Modes
1. **Granular Pitch Tracking (`/statcast_search/csv`):**
   - Ingests all 94 available fields per pitch, including exit velocity, launch angle, trajectory coordinates, spin rates, and 2024+ bat tracking metrics (`bat_speed`, `swing_length`).
   - Automatically splits date intervals into consecutive windows of at most 5 days (`split_date_range`).
2. **Analytical Leaderboards (`/leaderboard/*`):**
   - `expected_statistics` (xBA, xSLG, xwOBA, xOBP)
   - `statcast` (Exit Velocity & Barrels)
   - `sprint_speed` (Sprint Speed & 90-ft splits)
   - `bat-tracking` (Bat Speed, Swing Length, Squared Up %, Blasts)
   - `outs_above_average` (OAA & Defensive Runs Prevented)
   - `arm-strength` (Max and average throwing velocity)
   - `poptime` (Catcher Pop Time & Exchange Time)
   - `catcher-framing` (Runs Extra Strikes & Shadow Zone Strike Rate)
   - `pitch-arsenals` (Pitch mix & average velocities)
   - `pitch-movement` (Horizontal and vertical break)
   - `abs-challenges` (Automated ball-strike challenge results)

---

## 3. Rate Limiting & Concurrency
- Outbound requests to `baseballsavant.mlb.com` route through an `aiolimiter.AsyncLimiter` strictly bounded to at most 2.5 requests/second.
- Concurrency bounded via `asyncio.Semaphore` (default 4 workers).
- Transient errors (HTTP 429, 500, 502, 503, 504, timeouts) wrapped in jittered exponential backoff via `tenacity`.

---

## 4. Two-Phase Atomic Writes & Checkpointing
- All Parquet writes execute via `atomic_write_parquet()` writing to `.part` files and renaming atomically.
- Partition chunk status recorded in `manifest.json`.
