# Design: statcast-source-review

Method and card format: `docs/agents/WORK_BREAKDOWN.md`; cards: `docs/agents/tracks/04-statcast.md`.
Evidence goes into the sections below as each task completes (command output, counts, dates).

## Starting facts (survey before the review)
Surveyed 2026-10-30 (facts only; the cards decide what is a finding).

- **Provider:** Baseball Savant (baseballsavant.mlb.com): the pitch search CSV (`statcast_search/csv`, 25,000-row cap, windows bisected) and 36 leaderboard routes plus the `pitches_minors` search (`minors=true`, 2021+). No git pin; currency is by response hash or window (ADR 43 applies, upstream fingerprints for HTTP sources are ETag, Last-Modified or the content hash).
- **Registry:** 38 datasets: `pitches` and `pitches_minors` (season-partitioned) and 36 `leaderboard_*` datasets (34 season-partitioned, 2 without a season), all default ingest. Game feeds are kept as raw bytes (no processed dataset).
- **Code:** `sources/statcast/` is 2,995 lines in 11 files (`extractor.py` 567, `lb_catalog.py` 499, `leaderboards.py` 345, `schema.py` 220, `adapter.py` 142, `game_feed.py` 137, `normalizer.py` 113; generated `lb_tables.py` 828).
- **Tests:** `test_statcast.py`, `test_statcast_coverage.py`, `test_statcast_grid.py`, `test_statcast_minors.py`, `test_statcast_pitches.py`.
- **Spec:** `openspec/specs/statcast-ingestion/spec.md` has nine requirements (pitch search completeness, leaderboard registry, season ingest, game feed, embedded-page leaderboards, season game feeds, minor-league pitches, aligned windows, verified `unsupported` verdicts).
- **Docs:** `docs/sources/statcast.md` (1,686 lines); column descriptions in `docs/columns/statcast.json` (`pitches` 110, `pitches_minors` 110, shared `*` 17).
- **Already known from the Retrosheet review (apply as checks, not assumptions):** keys must be unique on real rows; every operation must be audit-logged; text empty vs NULL must round-trip through CSV; a CSV export of each dataset must verify; chunks must carry the schema digest (ADR 49) and a `revision` when a value fix keeps the columns (ADR 51); no hard-coded seasons (the pitch window runs to the current season, 2026 opens at the start of the season).
- **Lessons recorded before this review:** `year=` is silently ignored by some leaderboard routes (the probe compares payload hashes across seasons); Savant's minor-league pitches start in 2021; the 2023 season window also holds postseason and exhibition games (2,955 `game_pk` for 2,430 regular-season games), not duplicates.

## S1 inventory
(not started)

## S2 conformance
(not started)

## S3 schema and types
(not started)

## S4 code review against the designated tools
(not started)

## S5 tests and spec gaps
(not started)

## S6 live verification
(not started)

## S7 access, export, descriptions, docs, close
(not started)
