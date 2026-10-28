# Tasks: Retrosheet and Leaderboard Column Descriptions

- [ ] 1. Retrosheet
  - [x] 1.1 retrosheet.org refused connections (2026-10-27); used the Chadwick tool documents (cwevent, cwdaily, cwsub) from chadwickbureau/chadwick for the event, daily-split and substitution fields
  - [x] 1.2 Builder + `docs/columns/retrosheet.json`, regenerate docs
  - [x] 1.3a Game logs (161 fields, both datasets) from `glfields.txt` as copied in the `maxtoki/baseball_R` repository (found by web search); parser `scripts/retro_glfields.py` + test
  - [ ] 1.3 Still undescribed: schedule, rosters, reference tables, discrepancies, box accounts (need the Retrosheet format documents; the chadwickbureau/retrosheet mirror ships only data files, retrosheet.org and web.archive.org are unreachable from this environment: blocked on network access, retry later)
- [x] 2. Savant leaderboards
  - [x] 2.1 Locate provider definitions for leaderboard columns; cite; build `docs/columns/statcast.json` additions
- [ ] 3. Verification
  - [ ] 3.1 Gates; baseline raised; per-source percentage in the commit
