# Design: finish-mlb-history

## Decisions
- D1 A games job is games only. `ingest_season(include_season=False)` skips the reference tables and the season endpoints except `schedule_hydrated`, which `final_game_pks` needs. The separate season job (when the selection asks for it) still runs the season datasets. A job created before this change has no `games_only` parameter and behaves as before.
- D2 Compaction between stages, not at the end: 16 GB free cannot hold 16 seasons as small files. It runs after a stage ends well and never beside a download.
- D3 One stage per season in the plan, so a crash, a retry and a compaction each cost one season.
- D4 `--min-free-gb 5` stays: when free space falls below it the stage exits 2 and the queue stops with a clear message instead of filling the disk.
- D5 Speed is a separate change (batched chunk writes). The profile showed the work is dominated by about 13 small files and 13 manifest rewrites per game, not by the network. Not done here.

## Disk arithmetic (measured 2026-11-08)
2022: 3.11 GB in 35,763 files. 2025: 12.2 GB (it still holds minor-league games from an earlier run). 16 seasons at about 3 GB would be about 48 GB uncompacted against 16.3 GB free. Compacted size is not measured yet; task 2.1 records it after the first season.

## Evidence
Filled in as the plan runs (see the tasks).
