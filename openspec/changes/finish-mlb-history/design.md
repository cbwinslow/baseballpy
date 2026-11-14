# Design: finish-mlb-history

## Decisions
- D1 A games job is games only. `ingest_season(include_season=False)` skips the reference tables and the season endpoints except `schedule_hydrated`, which `final_game_pks` needs. The separate season job (when the selection asks for it) still runs the season datasets. A job created before this change has no `games_only` parameter and behaves as before.
- D2 Compaction after each stage, not at the end: 16 GB free cannot hold 16 seasons as small files. It first ran between stages; at 38,000 small files per season it took longer than the download, so it now runs beside the next stage, one at a time (ADR 94). Reads use `ParquetFile.read` (24 ms against 50 ms) and 2 datasets are compacted at a time.
- D3 One stage per season in the plan, so a crash, a retry and a compaction each cost one season.
- D4 `--min-free-gb 5` stays: when free space falls below it the stage exits 2 and the queue stops with a clear message instead of filling the disk.
- D5 Speed is a separate change (batched chunk writes). The profile showed the work is dominated by about 13 small files and 13 manifest rewrites per game, not by the network. Not done here.

## Disk arithmetic (measured 2026-11-08)
2022: 3.11 GB in 35,763 files. 2025: 12.2 GB (it still holds minor-league games from an earlier run). 16 seasons at about 3 GB would be about 48 GB uncompacted against 16.3 GB free. Compacted size is not measured yet; task 2.1 records it after the first season.

## Evidence
Filled in as the plan runs (see the tasks).

## Disk (measured 2026-11-08)
C: is 238 GB with 21 GB free. The lake is 72.9 GB: processed 38.8 GB (mlb_api 31.8, kalshi 3.3, statcast 2.1, retrosheet 1.2) and raw 33.6 GB (mlb_api 23.3, kalshi 4.0, statcast 3.6, retrosheet 2.2). The rest of the drive is other work: other projects about 9 GB, AppData about 56 GB (JetBrains 11, Claude session scratch 9.5, uv caches 6.7), `.cache` 8.9 GB, old copies `baseballpy_sc` 3 GB and `baseballpy_mlb` 1 GB. In `raw/mlb_api` the same response is kept once per dataset cut from it: the live feed four times (3.02 GB each) and the boxscore six times (0.57 GB each), about 12 GB of copies (task 3.5).

## Compaction in the queue (found by the first unattended run)
`compact --source mlb_api` also rewrote every old file (the ADR 87 migration) and spent 25+ minutes CPU bound before the next download could start. The queue now passes `--no-migrate`; the migration is task 2.3, run on its own when the downloads are done.


## As built: task 2.2, per-game coverage 2008-2026 (2026-11-12)

For every season, the finished major-league games of `schedule_hydrated` (`sport_id` 1, status Final) were checked for rows in each per-game dataset (13 datasets, from the processed files after the segment rebuild).

- Complete for every dataset except the cases below. `game_boxscore_pitching_notes` is empty for about two thirds of the games each season on purpose: the provider lists pitching notes only for games that have any (for example 2024: 2,112 of 2,940 games have none).
- Ten finished games lack core rows, and the provider itself holds nothing for them (checked 2026-11-12 against `v1/game/{pk}/linescore`, `playByPlay` and `boxscore`):
  - exhibition games `277489` (2010-03-03), `305461` (2011-02-25), `305471` (2011-02-27), `308207` (2011-03-04), `310735` (2011-03-30), `335533` (2012-04-03): no innings and no plays (two boxscore answers are HTTP 500);
  - summer-camp games `632099` and `632172` (2020-07-20) and regular-season games `745873` (2024-08-10) and `746402` (2024-05-03): the provider's linescore has no innings, while their play by play (64 to 77 plays) is stored.
No other finished major-league game is missing a row in any per-game dataset, 2008 to 2026.

## Forced segment rebuild (task 2.3)

`rebuild-segments mlb_api --season Y --apply --force --remove-legacy` ran for 2008 to 2026. Every season reported "Same: yes" (rebuilt rows equal the old rows). `catalog layout` now shows no MIXED_SCHEMA. `read("award_recipients")` has 43,481 rows and no empty `request_award_id` (646 distinct slugs). Remaining layout findings are not schema problems: TINY_FILES and SMALL_ROW_GROUPS (mlb_api, fangraphs, retrosheet), 3 ORPHAN_COMPACT in season 2023 and 2 EMPTY_FILES in statcast.

## Layout fixes and provider audit (tasks 2.3 and 2.4)

- `baseballpy compact` on FanGraphs and Statcast: 766 FanGraphs chunk files became 11; 2 zero-row Statcast leaderboard files were removed. Layout no longer lists them.
- Three chunks of season 2023 (`team_roster_all_time` team 404, `team_roster_coach` team 479, `award_recipients` ALREL) were recorded as compacted but their rows were not in the compact file, although the raw files hold them (1,178, 4 and 1 award records). They were lost in a compaction on 8 Nov that overlapped a download; the compact-one-writer change closed that hole. Repaired by `ingest mlb_api -s 2023 -d ... --refresh` and compacting again: team 404 has 1,178 rows, team 479 has 4. No ORPHAN_COMPACT is left.
- `baseballpy catalog audit` (mlb_api and statcast) printed `[]`: no MISSING, REVIVED or ERROR finding.
- Layout findings left are advice only: TINY_FILES for mlb_api (13 datasets whose season folder holds more than 10 segment files by design) and SMALL_ROW_GROUPS (mlb_api, retrosheet).

## Rare fields typed (task 3.2, ADR 118)

Roster `parentTeamId` and `note`, draft `xrefIds`, postseason reschedule fields, affiliate and boxscore `conference` now have typed columns (generator samples: 2026 rosters, postseasons 2009 and 2022, the 2019 draft, affiliates 2012, games 257753 and 427504). `compact` moved the old `_extras` values into the columns for the small datasets (roster 12,732 `parent_team_id` and 8 `note`, 208 affiliate conferences, 1 draft `xrefIds`, 16 reschedule rows). The per-game boxscore segments need a forced rebuild for the new columns. Still in `_extras`: `resumeDate` family (2 rows) and the stat-pool fields (`nameSlug`, `gameType`, `numLeagues`), which wait for the stats route (B-35).

## Size and rebuild time per season (task 2.1, partly)

Processed `mlb_api` size per season on 2026-11-13 (compacted, zstd), and the time of the forced segment rebuild from raw. The unattended download plan (`run plans/mlb-games-history.toml`) has not been re-run end to end; the games were downloaded in earlier runs and checked against the raw bytes (task 2.2).

| Season | Processed MB | Rebuild s | | Season | Processed MB | Rebuild s |
|---|---|---|---|---|---|---|
| 2008 | 606 | 660 | | 2018 | 1,088 | 763 |
| 2009 | 638 | 674 | | 2019 | 1,064 | 751 |
| 2010 | 688 | 693 | | 2020 | 458 | 344 |
| 2011 | 690 | 685 | | 2021 | 1,123 | 718 |
| 2012 | 688 | 696 | | 2022 | 1,072 | 705 |
| 2013 | 698 | 687 | | 2023 | 1,181 | 791 |
| 2014 | 676 | 685 | | 2024 | 1,149 | 750 |
| 2015 | 748 | 671 | | 2025 | 3,185 | 2,653 |
| 2016 | 779 | 712 | | 2026 | 3,539 | 3,120 |
| 2017 | 1,096 | 776 | | total | 21,165 | |

2025 and 2026 are larger because they include the minor-league games (sports 11 to 17 plus the others the fan-out asks for).

## Release hygiene: the source archive (2026-11-13)

A trial `uv build` (before the v1 release steps, task 4.1) gave a 12.1 MB source archive. 34 MB of it was `.delta/worktrees` (scratch copies of the repository from a tool, untracked and not ignored) and 17 MB was `docs/references`. `[tool.hatch.build.targets.sdist]` now excludes `.delta`, `.claude`, `.baseballpy` and `docs/references`; the archive is 2.8 MB, the wheel is unchanged (593 KB). The wheel installed in an empty environment, `baseballpy --version` printed 0.1.0, and a Chadwick download into an empty home gave 526,894 register rows, the same as the real lake. Test: `tests/test_packaging.py`. Not verified: an upload to TestPyPI (the owner's step, B-331), and CI, which has never run (`docs/agents/BACKLOG.md` notes it, and 54 commits are ahead of origin/main).

## Evidence: fresh Statcast 2024 pitches against the lake (2026-11-13)

`baseballpy verify-sample statcast -s 2024 -d pitches`: 51 weekly windows downloaded into a scratch home. 15 are identical row for row; 36 differ, and in every one only the column `pitch_type` differs. None of the 51 raw CSV files is byte-identical (the provider rewrites its files). One window was fetched again by hand (2024-06-04 to 2024-06-08): same 19,787 rows and the same keys; 11 pitches changed from `SL` (Slider) to `ST` (Sweeper). So Savant reclassifies pitches after the fact; this is provider drift, not a download or parsing defect, and the sample reports it as designed (a difference is information).

Open policy question for the owner (not decided here): the lake keeps what it fetched first (raw is immutable). A finished season can be refreshed once with `ingest statcast -s Y --refresh`; whether that should be a routine step (for example once after each season ends) is the "Statcast revision policy" item in the backlog.
