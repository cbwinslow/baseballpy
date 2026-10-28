# Design: Retrosheet Box Accounts

## Evidence (local, 10 files from 1950 and 2023, profiled 2026-10-27)
Record kinds and field counts (leading token included): `id` 2, `version` 2 (always `3`), `info` 3 (`info,<key>,<value>`; keys: visteam, hometeam, date, number, starttime, daynight, usedh, umphome, ump1b, ump2b, ump3b, umplf, umprf, site, attendance, temp, winddir, windspeed, fieldcond, precip, sky, timeofgame, innings, tiebreaker, gametype, wp, lp, save, gwrbi, oscorer), `start` 6 (`start,id,"Name",side,order,pos`), `stat,bline` 23, `stat,phline` 22, `stat,prline` 8, `stat,dline` 13, `stat,pline` 22, `stat,tline` 7, `line` 10-12 (runs per inning, side first), `event,<kind>` 6-8 (`hrline`, `dpline`, `tpline`, `sbline`, `csline`, `hpline`), `com` 2-6 (quoted text).
- `stat,bline` = `id, side, pos, seq, ab, r, h, 2b, 3b, hr, rbi, sh, sf, hbp, bb, ibb, k, sb, cs, gidp, int` (matches the published description in the format document).
- `stat,dline` example `rizzp101,0,1,6,27,1,1,0,0,0,0` = `id, side, seq, pos, outs played (innings x 3), po, a, e, dp, tp, pb`.
- `stat,pline` example has 20 values after the kind: `id, side, seq, outs pitched, batters faced, ...` (full list to be confirmed against `boxfile.txt`).
- Encoding is Latin-1 in places (names), records are CRLF or LF, ordering of record kinds within a game is free (sequence numbers are explicit).

## Decisions
1. Column names come from the official format document, not guessed from examples; where the document is unavailable the parser raises on an unexpected field count rather than guessing (never silently skip).
2. One dataset per record kind with `game_id` (from the preceding `id` record) on every row; innings pitched/played stay as integer outs (as published), documented.
3. Parsing is streaming and per file; partitioned by season; the raw `box_files` dataset is the source, so re-parsing needs no network.
4. Field counts that vary (`line` 10-12 = extra innings, `event` 6-8, `com`) are modelled explicitly (`line` as `innings` JSON/array columns + `inning_count`, events as a kind plus a typed field list per kind).

## Risks
The official spec could differ from the inference above; task 1.1 fetches and stores it under `docs/sources/` (respecting Retrosheet's notice) and the schema generator is reconciled with it before any dataset is registered.

## Live check on the 2015-2024 lake (2026-10-28, homelab `home_hist`, DuckDB over the processed Parquet)
- `box_games` 23,165 games; `gamelogs` 22,763 regular-season games (2015: 2,429 ... 2020: 898 ... 2024: 2,429); `box_batting_lines` 679,552 rows over 23,165 games; `box_records` 1,125,976 rows (unknown kinds and events: `stat,dline`, `stat,pline`, `event,hrline`, `stat,phline`, `line`, `stat,tline`, `event,dpline`, `event,sbline`, `event,hpline`, `event,csline`, `stat,prline`, `com`, `event,tpline`).
- Join key: `(hometeam, date, number)` of `box_games` against `(home_team, date, game_num)` of `gamelogs` (the game logs have no `game_id`). Regular-season game logs without a box game: 0. Box games with no game log in `gamelogs` or `gamelogs_postseason`: 0. Duplicate `game_id`: 0. Box games without any record: 0.
- The 23,165 - 22,763 = 402 extra box games are all in `gamelogs_postseason` (the extras listed by date include a 14 July game with home team `NLS`, an All-Star game, so that file holds All-Star games as well as the postseason): 37, 36, 39, 34, 38, 53, 38, 41, 42 and 44 per season 2015-2024, 402 in all. Of the 1,973 postseason game logs in the file (1903 onward), the ones outside 2015-2024 have no box game here because only those seasons were ingested.
- `quarantine/` does not exist in the lake: nothing was quarantined.
- Not checked: field-level equality between box lines and the game logs' score and line-score columns (the typed box datasets for the remaining kinds wait for the official `boxfile.txt`).
