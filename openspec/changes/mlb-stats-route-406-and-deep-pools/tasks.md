# Tasks: mlb-stats-route-406-and-deep-pools

- [ ] 1. The 406
  - [x] 1.1 Web-search how others handle 406 on `v1/stats` and record sources and findings in `design.md`
  - [ ] 1.2 Retest the route (at most one request per hour; control with `v1/teams`); record the date it answers 200 again
- [x] 2. Code
  - [x] 2.1 `gen_mlb_schemas.py` refuses to write an empty `PLAYER_STAT_COMBOS`/league combo table; a 406 is logged with its status and reported as a provider error, never `unsupported`; tests
  - [x] 2.2 The three deep single-season pools use smaller pages or a per-season split; respx tests (delegate the code to agy, review the diff)
- [ ] 3. Re-run
  - [ ] 3.1 After a 200: re-run the 15 failed pools and one modern MLB season on the homelab; record rows and errors in `design.md`
  - [ ] 3.2 Regenerate the `team_stats_year_by_year_*` schemas (`gen_mlb_schemas.py --only`, never the full run while the 406 lasts); add a test that the real-run fields are typed columns
