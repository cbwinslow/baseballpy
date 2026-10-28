# Retrosheet Ingestion Specification

## Purpose
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

---

## Requirements
### Requirement: Tree-Driven Discovery
Available seasons and files MUST be discovered from the upstream repository tree at the pinned ref, not hard-coded; file kinds map to datasets through a pattern registry and files no pattern covers MUST be reported.

### Requirement: Complete Dataset Set
The system MUST ingest event files (regular `events`, `events_postseason`, `events_deduced`), rosters, regular and postseason game logs, schedules (including `schedule_original`), umpires, discrepancy files, every CSV under `reference/`, and the derived `boxscores_*`, `daily_splits` and `substitutions` tables. Box-score game accounts (`.EB*`) MUST be stored raw and parsed into the `box_*` datasets (see Box-Score Game Accounts).

### Requirement: Honest Completion
A season MUST be marked COMPLETED only if every file the tree lists for it is present and valid; a tree-listed file answering 404 is recorded `ABSENT`; a 404 is never success. Every raw file records its sha256 and the pinned `source_ref`.

#### Scenario: Interrupted ingest
- **GIVEN** an `ingest_all(2000, 2005)` killed during 2003
- **WHEN** re-run
- **THEN** 2000-2002 are skipped, 2003's `.part` files are discarded, and 2003-2005 complete.

### Requirement: Streaming Parse
Parsing MUST stream into Parquet row-group batches (one per source file) without accumulating whole-season Python lists; CPU-bound parsing MAY use a bounded process pool.

### Requirement: GPL Boundary
`chadwickpy` MUST be imported only from `sources/retrosheet/_chadwick_adapter.py`, which raises an `ImportError` naming the `retrosheet` extra when the package is missing.

### Requirement: Box-Score Game Accounts (interim)
Every `.EB*` file MUST be parsed: `id`/`version`/`info` into `box_games` (typed, `unknown` as NULL, unknown keys in `_extras`), `start` into `box_starters`, `stat,bline` into `box_batting_lines`, and every other record (including unknown kinds) losslessly into `box_records` with its raw line; an unexpected field count for a typed kind MUST raise. Typed datasets for the remaining kinds follow once the official layout document is available.
