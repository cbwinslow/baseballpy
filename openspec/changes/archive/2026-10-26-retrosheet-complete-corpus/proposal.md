# Change Proposal: Retrosheet Complete Corpus & Chadwick Suite Ingestion

## Why
Retrosheet historical data contains much more than regular-season event files and game logs. The upstream GitHub mirror (`chadwickbureau/retrosheet`) and the underlying `chadwickpy` parsing engine provide:
1. Game-by-game batting and pitching box scores (`cwbox`).
2. Daily player splits across batting, pitching, and fielding (`daily`).
3. In-game player substitutions and defensive changes (`sub`).
4. Official scoring notes and umpire comments (`comment`).
5. Postseason and All-Star game event files (`.EVE`: Wild Card, Division Series, LCS, World Series, All-Star).
6. Postseason game logs (`GLWC.TXT`, `GLDV.TXT`, `GLLC.TXT`, `GLWS.TXT`, `GLAS.TXT`).
7. Complete reference tables: `ballparks.csv`, `teams.csv`, `ejections.csv`, `coaches.csv`, `relatives.csv`, `biofile.csv`.
8. Team rosters (`.ROS`).

To meet our Full Data Preservation mandate (ADR 15) and provide a premier baseball research library, `baseballpy` must ingest, parse, and normalize every one of these datasets into strongly-typed PyArrow tables with zero data loss.

## What Changes
1. **Exhaustive Schema Documentation:** Document all column dictionaries, raw formats, physical PyArrow types, and nullabilities in `docs/sources/retrosheet.md`.
2. **Retrosheet Extractor Expansion:**
   - Add extraction for postseason event archives and deduplicated `.EB*` files.
   - Add extraction for postseason game logs (`GLAS`, `GLWC`, `GLDV`, `GLLC`, `GLWS`).
   - Add extraction for all reference tables from `chadwickbureau/retrosheet/reference/`.
   - Maintain atomic `.part` writing and manifest checkpointing.
3. **Retrosheet Normalizer Expansion:**
   - Implement `normalize_boxscores(season)` emitting `batting` and `pitching` PyArrow tables.
   - Implement `normalize_daily_splits(season)` emitting `daily_splits` PyArrow table.
   - Implement `normalize_substitutions(season)` emitting `substitutions` PyArrow table.
   - Implement `normalize_comments(season)` emitting `comments` PyArrow table.
   - Implement `normalize_reference(table_name)` emitting typed PyArrow tables for `ballparks`, `teams`, `ejections`, `coaches`, `relatives`, `biofile`.
   - Support postseason game log normalization.
4. **Public Facade Integration:** Expose unified helper methods under `baseballpy.sources.retrosheet` and top-level `bb.retrosheet`.
5. **Testing & Verification:** Comprehensive unit tests in `tests/test_retrosheet.py` with 100% offline mocked fixtures.

## Impact & Invariants
- Zero breaking changes to existing `normalize_events` and `normalize_gamelogs`.
- Strict typing with PyArrow: no untyped strings for numeric identifiers, dates, or counts.
- Strict two-tier folder structure (`raw/` vs `processed/`).
- 100% test coverage and strict type safety.
