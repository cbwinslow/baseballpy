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
