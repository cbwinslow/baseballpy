# Design: Statcast Pitch-Level Ingestion Engine

## 1. Concurrency & Chunking Topology

```text
User Request: start_dt="2024-04-01", end_dt="2024-04-28" (28 days)
                             │
                             ▼
              Date Range Chunking Engine
   [2024-04-01..2024-04-07], [2024-04-08..2024-04-14],
   [2024-04-15..2024-04-21], [2024-04-22..2024-04-28]
                             │
                             ▼
              Async Worker Pool (Semaphore=4)
                             │
                             ▼
              aiolimiter (2.5 requests/sec)
                             │
                             ▼
              httpx.AsyncClient (HTTP/2 pool)
                             │
                             ▼
              Audit Telemetry & Local Cache
       (~/.baseballpy/cache/statcast/YYYY-MM-DD_YYYY-MM-DD.parquet)
                             │
                             ▼
               StatcastNormalizer (PyArrow)
                             │
                             ▼
              Sink (DuckDB / Parquet / Polars)
```

## 2. Exhaustive Schema Fields (Preserving ALL Attributes per ADR 15)
- Pitch Characteristics: `pitch_type`, `release_speed`, `release_pos_x`, `release_pos_z`, `release_pos_y`, `spin_axis`, `release_spin_rate`, `release_extension`, `arm_angle`
- Game & Play Context: `game_date`, `game_pk`, `game_year`, `game_type`, `home_team`, `away_team`, `inning`, `inning_topbot`, `at_bat_number`, `pitch_number`, `balls`, `strikes`, `outs_when_up`
- Batted Ball & Tracking: `launch_speed`, `launch_angle`, `effective_speed`, `launch_speed_angle`, `hc_x`, `hc_y`, `hit_distance_sc`, `hit_location`, `bb_type`, `events`, `description`
- Trajectory Physics: `vx0`, `vy0`, `vz0`, `ax`, `ay`, `az`, `sz_top`, `sz_bot`, `plate_x`, `plate_z`, `pfx_x`, `pfx_z`
- Expected & Sabermetric Metrics: `estimated_ba_using_speedangle`, `estimated_woba_using_speedangle`, `woba_value`, `woba_denom`, `babip_value`, `iso_value`
- Bat Tracking (2024+): `bat_speed`, `swing_length`
- Runners & Base State: `on_1b`, `on_2b`, `on_3b`
- Defense & Fielders: `fielder_2` through `fielder_9`, `if_fielding_alignment`, `of_fielding_alignment`
- Pitcher & Batter: `pitcher`, `batter`, `stand`, `p_throws`
- Win Probability: `home_score`, `away_score`, `post_home_score`, `post_away_score`, `bat_score`, `fld_score`, `delta_home_win_exp`, `delta_run_exp`
- Descriptors: `des`

## 3. Storage Sinks
- `DuckDBSink`:
  Uses DuckDB's zero-copy Arrow interface:
  `con.register("arrow_batch", table); con.execute("INSERT INTO pitches SELECT * FROM arrow_batch")`
- `ParquetSink`:
  Uses `pyarrow.parquet.write_table` with Snappy compression.
