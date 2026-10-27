# Tasks: Column Descriptions

- [ ] 1. Mechanism <!-- id: 1 -->
  - [x] 1.1 YAML format + merge in `docsgen.py`; `TODO` marker and per-dataset counts
  - [x] 1.2 `baseballpy docs coverage` and the ratchet test (baseline recorded in the test)
- [ ] 2. Content from provider metadata <!-- id: 2 -->
  - [x] 2.1 MLB: `/v1/baseballStats`, `/v1/statTypes`, `/v1/gameTypes`, positions, event and pitch types
  - [x] 2.2 Statcast pitch CSV glossary (https://baseballsavant.mlb.com/csv-docs, 220 columns); leaderboard pages have no glossary and stay open
  - [ ] 2.3 (blocked 2026-10-27: retrosheet.org refuses connections, ECONNREFUSED from WebFetch and timeout from curl) Retrosheet: event, box, game-log, roster, schedule and discrepancy format documents
  - [ ] 2.4 Lahman readme, Chadwick register README
- [ ] 3. Records and verification <!-- id: 3 -->
  - [x] 3.1 ADR 34; spec delta merged
  - [x] 3.2 Gates; report the final coverage percentage per source in the commit

Open: 2.2 leaderboards, 2.3, 2.4; MLB stat columns whose response key differs from `/v1/baseballStats` names (avg, obp, strikeOuts ...) are not guessed. `scripts/build_column_descriptions.py` regenerates `docs/columns/{mlb_api,statcast}.json`.
