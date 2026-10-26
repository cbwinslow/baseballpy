# Retrosheet Ingestion Specification

## 1. Overview
The Retrosheet Ingestion Engine extracts, parses, caches, and normalizes historical play-by-play events, box scores, daily player lines, substitutions, game logs, and reference databases from the Chadwick Baseball Bureau GitHub mirror (`https://github.com/chadwickbureau/retrosheet`).

All parsing is performed in memory via `chadwickpy` (pure Python port of the Chadwick C suite) with zero dependencies on external C binaries or scrapers.

---

## 2. Partitioning & Directory Layout
Enforces two-tier raw/processed separation under `~/.baseballpy/cache/retrosheet/`:
- `raw/seasons/{year}/`: Raw DiamondWare `.EVA`, `.EVN`, `.EVE` event files and `.ROS` rosters.
- `raw/gamelogs/`: Raw `gl{year}.txt` and postseason logs (`GLWC.TXT`, `GLDV.TXT`, `GLLC.TXT`, `GLWS.TXT`, `GLAS.TXT`).
- `raw/reference/`: Raw reference CSVs (`ballparks.csv`, `teams.csv`, `ejections.csv`, `coaches.csv`, `relatives.csv`, `biofile.csv`).
- `processed/events/season={year}/`: Strongly-typed Parquet for 97-field play-by-play events.
- `processed/boxscores_batting/season={year}/`: Strongly-typed Parquet for batting box scores.
- `processed/boxscores_pitching/season={year}/`: Strongly-typed Parquet for pitching box scores.
- `processed/daily_splits/season={year}/`: Strongly-typed Parquet for daily player lines (154 fields).
- `processed/substitutions/season={year}/`: Strongly-typed Parquet for player substitutions.
- `processed/gamelogs/`: 161-column historical game logs.
- `processed/reference/`: Standardized reference tables.

---

## 3. Schemas & Coercion Invariants
1. **No String Dumps:**
   - Numerical metrics (at-bats, hits, strikeouts, runs, outs) must be physical integers (`int16`, `int8`, `int32`).
   - Dates must be ISO 8601 strings or PyArrow `date32()`.
   - Flags must be `pa.bool_()`.
2. **Atomic Writes:**
   - Writing directly to final cache filenames is prohibited. All writes route through `atomic_write()` or `atomic_write_parquet()` via `.part` files.
3. **Manifest Tracking:**
   - `manifest.json` tracks chunk completion with records count and hashes to enable instant resumption.
