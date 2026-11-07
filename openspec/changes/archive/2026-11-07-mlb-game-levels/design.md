# Design

- **Option, not a new command:** `Selection.options` (`--option KEY=VALUE`) already carries source-specific switches, so the adapter reads `sports` from it and stores it as a job parameter (`sports=1`). The value is checked while planning, so a typo fails at once and not hours into a run.
- **Default:** the major leagues, like every other MLB path that uses `sport_ids=(1,)`. Per-game data was already opt-in; the owner asked for the major leagues first. `sports=all` brings back the old behaviour.
- **Filter:** `MlbApiSource.final_game_pks(season, sport_ids)` keeps games whose `schedule_hydrated.sport_id` is in the list (no `sport_id` is ever null in the stored schedules: 2008, 2015, 2025, 2026 checked, 9 to 13 levels each).
- **Evidence (2026-11-07):** final games per season, major vs all: 2026 2,960 vs 15,974; 2025 2,961 vs 16,847; 2015 2,969 vs 17,013; 2008 2,959 vs 16,674.
- **Not solved here:** the `MemoryError` itself (a run of 16,000 games held too much bookkeeping in memory). A major-league season is five times smaller; the cause is logged as an open backlog row.
