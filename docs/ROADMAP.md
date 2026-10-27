# Strategic Innovations & Capability Roadmap

This document outlines the strategic engineering roadmap for `baseballpy`, establishing 18 high-value capability pillars designed to make `baseballpy` the foundational data engineering and sabermetric computing library in Python—far surpassing legacy packages (`pybaseball`, `baseballr`, `mlbstatsapi`) in speed, type safety, coverage, and AI-native workflows.

> **Status 2026-10-27.** Pillar 1 item 1 (Lahman) is delivered (27 strict tables, `cbwinslow/lahman-database-csv` only). Item 5 (MiLB Statcast) is delivered for pitch search (`StatcastQuery(minors=True)`, dataset `pitches_minors`, 2021 onwards) and minor-league *MLB Stats API* data (all sports/levels) is ingested. The other pillars are not started. Coverage numbers live in the generated docs and probes (`docs/*_probe.json`), not here.

---

## Pillar Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        baseballpy Core Platform                        │
├───────────────────┬───────────────────┬────────────────────────────────┤
│ 1. Deep Sources   │ 2. Spatial/Phys   │ 3. Sabermetric Engines         │
│  - Lahman SQLite  │  - Hawkeye 3D Bio │  - Local Feature Store         │
│  - FanGraphs Proj │  - Ballpark Geo   │  - Live Win Prob / RE24        │
│  - B-Ref WAR Xwalk│  - Weather Sync   │  - Rule Era Invariant Matrices │
│  - MiLB / Foreign │  - Bat Tracking   │  - Stuff+ & Pitch Modeling     │
├───────────────────┴───────────────────┴────────────────────────────────┤
│ 4. AI & Agent Interfaces              │ 5. Performance & UX            │
│  - Baseballpy MCP Server (AI Agents)   │  - Rust / Arrow Accelerators   │
│  - Natural Language Text-to-DuckDB     │  - Rich TUI Live Gameday App   │
└───────────────────────────────────────┴────────────────────────────────┘
```

---

## 1. Deep Data Source Expansions

### 1. Lahman Complete Baseball Database Async Ingestion (1871–2024)
- **Problem:** Existing tools require manual CSV extraction or out-of-date Lahman mirrors.
- **Solution:** Direct zero-configuration download of the latest Lahman release into an embedded DuckDB/SQLite database and strongly-typed Parquet partitions (`batting`, `pitching`, `fielding`, `allstar_full`, `hall_of_fame`, `salaries`, `awards_players`).
- **Target Module:** `baseballpy.sources.lahman`

### 2. Hawkeye 3D Biomechanics & Skeletal Pose Tracking
- **Problem:** MLB provides full 3D skeletal tracking (18 distinct joint coordinates at 300 fps for pitcher delivery and batter swing mechanics), yet no open-source Python tool ingests and normalizes this high-frequency stream.
- **Solution:** Ingest Hawkeye optical tracking JSON/binary feeds, converting 3D Cartesian coordinates $(x, y, z)$ into columnar PyArrow nested structures (`list<struct<joint: string, x: float32, y: float32, z: float32, timestamp: timestamp_us>>`).
- **Target Module:** `baseballpy.sources.statcast.biomechanics`

### 3. FanGraphs Sabermetric Projections & Auction Calculators
- **Problem:** Steamer, ZiPS, ATC, and THE BAT projections are scattered across web tables without programmatic typed feeds.
- **Solution:** Clean extractor for FanGraphs consensus projections, rest-of-season forecasts, and customized z-score auction values across rotisserie and points leagues.
- **Target Module:** `baseballpy.sources.fangraphs`

### 4. Baseball-Reference Historical WAR Crosswalk
- **Problem:** bWAR (Baseball-Reference) and fWAR (FanGraphs) calculate replacement level, defensive runs saved, and positional adjustments differently.
- **Solution:** Ingest daily and seasonal bWAR tables directly from Baseball-Reference's raw database exports, unifying them with the Chadwick Register to allow side-by-side bWAR vs. fWAR comparisons.
- **Target Module:** `baseballpy.sources.bref`

### 5. Minor League (MiLB) Triple-A & Double-A Statcast Ingestion
- **Problem:** Full Statcast Hawkeye cameras are now active across all 30 Triple-A ballparks and selected Double-A stadiums, but fetching prospect pitch-by-pitch data requires custom endpoint hacking.
- **Solution:** Extend `StatcastExtractor` with `sport_id` and `league_id` parameters to seamlessly download minor league tracking data for prospects.
- **Target Module:** `baseballpy.sources.statcast.milb`

### 6. International Leagues (NPB, KBO, CPBL, LIDOM)
- **Problem:** Cross-league scouting of international stars (e.g. Japanese NPB, Korean KBO) requires disparate web scrapers with irregular character encodings.
- **Solution:** Dedicated extractors normalizing foreign league play-by-play and player statistics into the canonical PyArrow schema with UTF-8 transliteration.
- **Target Module:** `baseballpy.sources.international`

### 7. Amateur Draft & College Baseball Trackman Ingestion
- **Problem:** College baseball Trackman metrics (NCAA Division I, Cape Cod League) are vital for modern draft analytics but completely absent from existing libraries.
- **Solution:** Ingest CSV and Trackman v3 format feeds from collegiate summer leagues and NCAA public feeds.
- **Target Module:** `baseballpy.sources.amateur`

---

## 2. Spatial, Physics & Biomechanical Computing

### 8. 3D Ballpark Boundary Polygons & GeoParquet Overlay
- **Problem:** Wall dimensions, fence heights, and foul territory geometry vary radically by ballpark, yet existing libraries treat field coordinates as abstract points without geometry.
- **Solution:** Provide exact 3D polygon GeoParquet geometries for all 30 active MLB ballparks (and historical ballparks like Polo Grounds, Tiger Stadium). Enable spatial intersection queries (e.g., "Would this 385 ft flyout with 28° launch angle be a home run in Fenway Park?").
- **Target Module:** `baseballpy.spatial.ballparks`

### 9. Statcast Bat & Arm Tracking Physics Engine
- **Problem:** Raw bat tracking metrics (`bat_speed`, `swing_length`, `arm_angle`) require physical trajectory modeling to compute sweet-spot contact percentages and squared-up ball rates.
- **Solution:** Implement vector physical calculators in Polars/NumPy computing impact momentum, angular velocity at point of contact, and effective sweet-spot deviation.
- **Target Module:** `baseballpy.analytics.physics`

### 10. Historical Weather & Atmospheric Adjustments (Open-Meteo)
- **Problem:** Temperature, relative humidity, air density, and wind vectors heavily alter baseball aerodynamics (e.g. Coors Field effect vs. April in Cleveland).
- **Solution:** Integrate with Open-Meteo historical reanalysis API, querying exact temperature, wind direction, and barometric pressure at the scheduled game time and venue coordinates, adding drag coefficient adjustments to pitch trajectories.
- **Target Module:** `baseballpy.environmental.weather`

---

## 3. Sabermetric Engines & Local Feature Store

### 11. Local Sabermetrics Feature Store (Rolling xwOBA, Stuff+, Location+)
- **Problem:** Training machine learning models on baseball data requires repeating complex window aggregations (e.g., rolling 50-PA xwOBA, trailing 100-pitch Stuff+).
- **Solution:** Build a zero-copy local feature store on top of DuckDB and Polars that automatically computes rolling physical features (seam-shifted wake, release point deviation, velocity differential).
- **Target Module:** `baseballpy.analytics.features`

### 12. Era-Invariant Transition Matrices & Rule Variation Adapters
- **Problem:** 7-inning doubleheaders (2020–2021), the ghost runner on second base in extra innings (2020+), pitch clocks (2023+), and defensive shift limits (2023+) distort run expectancy tables across eras.
- **Solution:** Dynamic Run Expectancy (RE24) and Win Probability (WE) engines that automatically calibrate base state transition matrices depending on the game date and rule set in effect.
- **Target Module:** `baseballpy.analytics.expectancy`

### 13. Microsecond Live Game Win Probability & Run Expectancy Ingestion
- **Problem:** Real-time game streaming currently captures raw plays but does not compute instantaneous win probability leverage indexes (LI).
- **Solution:** Couple `baseballpy.sources.mlb_api.stream` with a vector lookup table computing post-pitch Win Expectancy (WE) and Championship Win Probability Added (cWPA) on every event.
- **Target Module:** `baseballpy.analytics.live_models`

---

## 4. AI & Agentic Tooling

### 14. Model Context Protocol (MCP) Server for LLM Agents
- **Problem:** AI coding and analysis agents (Claude, Gemini, Antigravity) cannot interact directly with baseball databases without writing custom shell scripts or SQL.
- **Solution:** Ship an official, high-performance MCP server (`baseballpy-mcp`) exposing tools:
  - `query_pitches(filter_criteria)`
  - `get_player_bio(name_or_id)`
  - `stream_active_game(game_pk)`
  - `get_leaderboard(metric, year)`
- **Target Module:** `baseballpy.mcp`

### 15. Natural Language Text-to-DuckDB Query Engine
- **Problem:** Analysts often want quick answers (e.g., "Show me Aaron Judge's exit velocity against 95+ mph four-seamers with two strikes") without manually typing complex SQL.
- **Solution:** Lightweight text-to-SQL layer mapping natural language prompts directly to optimized DuckDB SQL queries over local Parquet cache files.
- **Target Module:** `baseballpy.ai.text2sql`

---

## 5. High-Performance Infrastructure & UX

### 16. Rust / Arrow Native Computational Accelerators
- **Problem:** Python parsing loops for multi-gigabyte Retrosheet DiamondWare files or custom regex event codes can become CPU-bound.
- **Solution:** Provide optional compiled PyO3/Rust accelerators for ultra-fast parsing, pitch trajectory integration (Euler/Runge-Kutta 9-parameter flight models), and event sequence encoding.
- **Target Module:** `baseballpy_rust`

### 17. Terminal User Interface (TUI) Live Gameday App (`baseballpy tui`)
- **Problem:** Fans and analysts need a fast, low-overhead way to monitor live games directly in the developer terminal.
- **Solution:** A rich interactive terminal application powered by `textual` or `rich` rendering:
  - Real-time animated strike zone with pitch coordinate plots.
  - Live box score and win probability chart.
  - Active runner base paths and defensive shift visualization.
- **Target Module:** `baseballpy.cli.tui`

### 18. Distributed Partition Loaders (Dask & Ray)
- **Problem:** Multi-decade Statcast queries (2015–2024, ~7.5 million pitches) require cluster-scale distributed computing for large ML research teams.
- **Solution:** Native `to_dask()` and `to_ray()` converters reading partitioned Parquet datasets directly with predicate pushdown and column projection.
- **Target Module:** `baseballpy.sinks.distributed`
