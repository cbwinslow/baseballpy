# Tasks: verify-optin-paths

- [x] 1. Per-game family: 13 datasets ingested for real, re-run served from cache, drift fixed by a wider generator sample (design, Findings)
- [x] 2. Per-player stats family (`ingest_people_stats`, bounded; `metrics` and one `matchups` pair): 149 endpoints, 62k rows, quarantine empty, drift fixed by a wider person sample (design, Findings); the two `vs_player_*_opp_team` keys stay non-unique (documented, open)
- [ ] 3. All-time pools (`ingest_history`, watch the 20,000-row refusal and runtime)
- [ ] 4. On-demand: `people_changes`, `game_changes` (`updated_since`), `people_search` (query)
- [x] 5. `StatcastGameFeed.ingest_season` with a small cap (`ingest statcast --datasets game_feed --limit 20`: 20 feeds, 50 MB raw, 25 s; see design, Findings)
- [ ] 6. CLI knobs for opt-in paths where missing, generated from the registry, with tests and `docs generate`
- [ ] 7. Final report; archive
