# Change Proposal: Consolidated Multi-Season DuckDB Catalog and Partition Organization

## Context & Motivation
Researchers and analysts working with baseball data frequently download data across multiple seasons in separate sessions (e.g. downloading 2023 today, 2024 next week, and comparing against historical Lahman 1871–2025 tables). Users coming from relational databases (PostgreSQL, MySQL) expect unified single-table queries (`SELECT * FROM statcast_pitches WHERE season = 2024`) without manual file merging, clobbering, or managing fragmented folder paths.

Furthermore, analysts need to cross-join distinct data systems (joining Statcast pitch metrics with Chadwick register keys, Lahman biographical records, and Retrosheet boxscores) seamlessly via SQL without copying multi-gigabyte datasets into RAM.

## Proposed Changes
1. **Statcast Hive-Partition Alignment:**
   - Standardize `StatcastExtractor` cache storage to use `season=YYYY/` Hive partitions (`statcast/processed/season=YYYY/*.parquet`).
   - Maintain 100% backward compatibility to read legacy flat parquet chunk files if present.
2. **Consolidated DuckDB Database Catalog (`baseballpy.database`):**
   - Provide `BaseballDatabase` and top-level helpers `connect_db()` and `sync_database()`.
   - Automatically register consolidated DuckDB SQL views with `hive_partitioning = true` and `union_by_name = true` over all cached Parquet datasets (`statcast_pitches`, `retrosheet_events`, `retrosheet_boxscores_batting`, `retrosheet_boxscores_pitching`, `retrosheet_gamelogs`, `lahman_*`, `chadwick_register`).
   - Enable cross-source SQL joins using Chadwick crosswalk keys (`key_mlbam`, `key_retro`, `key_bbref`, `key_fangraphs`).
3. **Verification of 2025 Dataset Availability:**
   - Verify that all data providers support the 2025 season (Lahman 1871–2025, Statcast 2025, MLB Stats API 2025, Chadwick 2025/2026 active player crosswalk).
4. **Documentation & ADR Sync:**
   - Record ADR 21 in `docs/DECISIONS.md`.
   - Update `docs/QUICKSTART.md` with multi-season DuckDB join workflows.
