# Tasks: Column Descriptions

- [x] 1. Mechanism <!-- id: 1 -->
  - [x] 1.1 YAML format + merge in `docsgen.py`; `TODO` marker and per-dataset counts
  - [x] 1.2 `baseballpy docs coverage` and the ratchet test (baseline recorded in the test)
- [x] 2. Content from provider metadata <!-- id: 2 -->
  - [x] 2.1 MLB: `/v1/baseballStats`, `/v1/statTypes`, `/v1/gameTypes`, positions, event and pitch types
  - [x] 2.2 Statcast pitch CSV glossary (https://baseballsavant.mlb.com/csv-docs, 220 columns); leaderboard columns moved to `column-descriptions-retrosheet-and-leaderboards`
  - [x] 2.3 (moved to change `column-descriptions-retrosheet-and-leaderboards`; blocked 2026-10-27: retrosheet.org refuses connections, ECONNREFUSED from WebFetch and timeout from curl) Retrosheet: event, box, game-log, roster, schedule and discrepancy format documents
  - [x] 2.4 Lahman readme (SABR readme2025.txt, 97.2% of columns) and Chadwick register README (72.1%)
- [x] 3. Records and verification <!-- id: 3 -->
  - [x] 3.1 ADR 34; spec delta merged
  - [x] 3.2 Gates; report the final coverage percentage per source in the commit

Remaining content (Retrosheet, Savant leaderboards) moved to `column-descriptions-retrosheet-and-leaderboards`; MLB stat keys whose names differ from `/v1/baseballStats` are not guessed.
