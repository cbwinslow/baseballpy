# Retrosheet Ingestion Specification

## 1. Overview
The Retrosheet Ingestion Engine extracts, parses, caches, and normalizes historical play-by-play events, box scores, daily player lines, substitutions, game logs, and reference databases from the Chadwick Baseball Bureau GitHub mirror (`https://github.com/chadwickbureau/retrosheet`).

All parsing is performed in memory via `chadwickpy` (pure Python port of the Chadwick C suite) with zero dependencies on external C binaries or scrapers.

---

## 2. Partitioning & Directory Layout
Raw event, roster, gamelog and reference files MUST be stored under `raw/retrosheet/<dataset>/[season=YYYY/]`; parsed output under `processed/retrosheet/<dataset>/[season=YYYY/]part-<chunk>.parquet`. Regular-season and postseason events MUST be separate datasets (`events`, `events_postseason`).
- `raw/retrosheet/event_files/season={year}/`: `TEAM{year}` and the `.EVA`, `.EVN`, `.EVE` event files.
- `raw/retrosheet/rosters/season={year}/`: `.ROS` rosters.
- `raw/retrosheet/gamelogs/`: raw `gl{year}.txt` and postseason logs (`GLWC.TXT`, `GLDV.TXT`, `GLLC.TXT`, `GLWS.TXT`, `GLAS.TXT`).
- `raw/retrosheet/reference_<name>/<name>.csv`: raw reference CSVs (`ballparks`, `teams`, `ejections`, `coaches`, `relatives`, `biofile`).
- `processed/retrosheet/events/season={year}/` and `events_postseason/`: strongly-typed play-by-play events.
- `processed/retrosheet/boxscores_batting|boxscores_pitching|daily_splits|substitutions|rosters/season={year}/`: strongly-typed per-season tables.
- `processed/retrosheet/gamelogs/season={year}/`, `gamelogs_postseason/`, `reference_<name>/`: game logs and standardized reference tables.

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
