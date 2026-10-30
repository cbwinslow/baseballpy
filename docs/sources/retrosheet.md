# Retrosheet Endpoint & Dataset Catalog

## Upstream Overview
- **Provider:** Retrosheet (`retrosheet.org`), distributed through the Chadwick Baseball Bureau GitHub mirror `chadwickbureau/retrosheet`.
- **Terms:** Retrosheet's attribution notice applies to all data (see `docs/DATA_LICENSES.md`).
- **Source of truth for what exists:** the git tree at the *pinned commit* (`src/baseballpy/core/sources_lock.json`, key `retrosheet`; override with `BASEBALLPY_RETROSHEET_REF`). At the current pin the tree lists 156 seasons (1871–2026) and about 8,600 files. Seasons and files are **discovered**, never hard-coded.
- **Endpoints used**
  | Purpose | Method + URL | Notes |
  | --- | --- | --- |
  | Tree discovery | `GET https://api.github.com/repos/chadwickbureau/retrosheet/git/trees/<sha>?recursive=1` | cached under `cache/http/github-tree/` (forever for a pinned SHA, 24 h for a branch); `GITHUB_TOKEN` is sent when set (lifts the 60 requests/hour limit) |
  | File download | `GET https://raw.githubusercontent.com/chadwickbureau/retrosheet/<sha>/<path>` | all through the shared `HttpClient`: 15 requests/second per host, bounded concurrency (default 4), retries with `Retry-After` |
- **Never `retrosheet.org` for bulk data:** the site drops connections from automated bulk clients (ADR 1, ADR 5).
- **Branch note:** the `master` branch is Chadwick's *augmented* edition (errata plus extra metadata); the `official` branch is the untouched upstream release. baseballpy pins a `master` commit.
- **Processing engine:** `chadwickpy` (GPL-3.0, imported only in `sources/retrosheet/_chadwick_adapter.py`).

### Honest completion rules
- A season is `COMPLETED` (manifest chunk `season_<year>` in `raw/retrosheet/event_files/`) **only if every file the tree lists for it is present**. A tree-listed file that answers 404 is recorded `ABSENT` and the season is retried on the next run.
- Every raw file is written atomically (`.part` → rename) with its `sha256`, size and the pinned `source_ref` recorded in the per-season manifest (`raw/retrosheet/<dataset>/season=YYYY/manifest.json`).
- `ingest_all(start, end)` is resumable: completed seasons and chunks are skipped, orphaned `.part` files are discarded, and an interrupted season is re-run from its missing files only.

## File kinds and the datasets they feed
| Tree pattern (`seasons/<year>/…`) | Raw directory (`raw/retrosheet/…/season=YYYY/`) | Processed dataset(s) |
| --- | --- | --- |
| `<year><TEAM>.EVA`, `.EVN` | `event_files/` | `events`; also `boxscores_batting`, `boxscores_pitching`, `daily_splits`, `substitutions` (derived with chadwickpy) |
| `<year>*.EVE`, `.EVR`, `.EVF` (postseason, all-star, special games) | `event_files/` | `events_postseason` |
| `<year>.EDA`, `.EDN`, `.EDF` (play-by-play deduced from box scores) | `event_files/` | `events_deduced` |
| `TEAM<year>` | `event_files/` | (used to resolve team names while parsing) |
| `<year>.EBA`, `.EBN`, `.EBE`, `.EBR`, `.EBF` (box-score game accounts) | `box_files/` | `box_games`, `box_starters`, `box_batting_lines`, `box_records` — see the box-account section |
| `<TEAM><year>.ROS` | `rosters/` | `rosters` |
| `GL<year>.TXT` | `gamelogs/` | `gamelogs` |
| `<year>schedule.csv` (`2026SCHEDULE.CSV`) | `schedule/` | `schedule` |
| `<year>sched-orig.csv` (e.g. 2020: the original pre-COVID schedule) | `schedule_original/` | `schedule_original` |
| `UMPIRES<year>.txt` | `umpires/` | `umpires` |
| `<year>aldiscs.csv`, `nldiscs.csv`, `fldiscs.csv` | `discrepancies/` | `discrepancies` |
| `gamelog/GL{WC,DV,LC,WS,AS}.TXT` | `gamelogs_postseason/` | `gamelogs_postseason` |
| `reference/<name>.csv` | `reference_<name>/` | `reference_<name>` |

**Box-score game accounts (`.EB*`)** are stored raw (`raw/retrosheet/box_files/`) and parsed into four datasets (section below); `boxscores_batting` and `boxscores_pitching` stay *derived* from the play-by-play files.

## Datasets Covered

### 1. Play-by-Play Event Data (`.EVA`, `.EVN`, `.EVE`, `.EB*`)
- **Coverage:** every season with play-by-play files in the tree (1912–present for most; complete modern coverage). `events` holds regular-season games, `events_postseason` postseason/all-star/special games, `events_deduced` games deduced from box scores. They are separate datasets so a game never appears twice in a view.
- **Format:** Retrosheet DiamondWare event records parsed by `chadwickpy.tools.events.event_rows` into all 164 fields it returns (cwevent standard fields 0-96 and extended fields 0-66, in that order) plus `_extras` for any field a future `chadwickpy` adds; a test pins the column list to `chadwickpy`'s own (see the generated dictionaries).
- **Partitioning:** `season=YYYY`; one atomic Parquet part per season written as one row group per source file.
- **Parsing:** CPU-bound and offline; files are parsed one at a time (optionally in a bounded process pool, `LakeConfig.parse_workers`) and streamed into the Parquet writer — no whole-season Python lists.
- **Key:** `(GAME_ID, EVENT_ID)`; `EVENT_ID` (cwevent standard field 96) is the play's number within the game, so the key is unique (checked on 38,161 real rows from 1925, 1935, 1950, 1975, 2000 and 2023). Before 2026-10-30 only 98 fields were kept and the key was `GAME_ID`, which collapsed a game to one row on merge exports; event Parquet written before then must be rebuilt (`ingest --refresh`).

### 2. Historical Game Logs (1871–present)
- **Regular season:** `seasons/<year>/GL<year>.TXT` (header-less, 161 positional fields documented by Retrosheet).
- **Postseason archives:** `gamelog/GLWC.TXT` (Wild Card), `GLDV.TXT` (Division Series), `GLLC.TXT` (League Championship Series), `GLWS.TXT` (World Series), `GLAS.TXT` (All-Star Games).
- **Partitioning:** regular logs by `season=YYYY`, postseason logs flat.

### 3. Box Scores (`cwbox`)
Derived from the regular-season play-by-play files with `chadwickpy.box.box_create`:

#### A. Batting Box Score Table (`retrosheet_box_batting`)
One row per player appearance (dataset `boxscores_batting`).

#### B. Pitching Box Score Table (`retrosheet_box_pitching`)
One row per pitcher appearance (dataset `boxscores_pitching`).

### 3b. Box-Score Game Accounts (`.EBA`, `.EBN`, `.EBE`, `.EBR`, `.EBF`)
428 files (1871-2025) holding games that have no (or no complete) play-by-play, e.g. most of 1871-1920. One game per `id,<GAME_ID>` record; record kinds profiled on the real 1950, 2023 and 2025 files (6,194 games for the first two, all 10 local files parse; 2023 `.EBA` has 1,215 games = half of 2,430, matching the game logs):

| Record | Fields (verified on the data) | Dataset |
|---|---|---|
| `id`, `version` (always `3`), `info,<key>,<value>` | game id, version, 30 known info keys (visteam, hometeam, date `YYYY/MM/DD`, number, starttime, daynight, usedh, umps, site, attendance, temp, wind, field, precip, sky, timeofgame, innings, tiebreaker, gametype, wp, lp, save, gwrbi, oscorer); `unknown` is NULL; other keys go to `_extras` | `box_games` |
| `start,<id>,"<name>",<side>,<order>,<pos>` | 6 fields | `box_starters` |
| `stat,bline,<id>,<side>,<pos>,<seq>,<17 counting stats>` | `ab r h 2b 3b hr rbi sh sf hbp bb ibb k sb cs gidp int` (columns `double`, `triple`, `interference` for the three non-identifier names) | `box_batting_lines` |
| `stat,phline`, `stat,prline`, `stat,dline`, `stat,pline`, `stat,tline`, `line`, `event,<kind>` (`hrline dpline tpline sbline csline hpline`), `com`, any unknown kind | parsed fields plus the raw line | `box_records` |

**Interim, honest status.** The official layout document (`https://www.retrosheet.org/boxfile.txt`) was not reachable from the build environment, so only the kinds whose layout is confirmed by both the data and independent descriptions are typed; every other record is kept losslessly in `box_records` (nothing is dropped) until the OpenSpec change `retrosheet-box-accounts` task 1.1 supplies the document and the remaining kinds get typed datasets. Field counts are strict: an unexpected count raises `BoxParseError` rather than guessing. Files are UTF-8 (Latin-1 fallback); innings played/pitched are stored as outs in the raw lines (as published).

### 4. Daily Player Splits (`daily`)
Derived with `chadwickpy.tools.daily.daily_lines` (154 columns) — dataset `daily_splits`.

### 5. Substitutions (`sub`)
Derived with `chadwickpy.tools.sub.sub_lines` (26 columns) — dataset `substitutions`.

### 6. Rosters, schedules, umpires, discrepancies
- `rosters`: `.ROS` files are header-less (`player_id,last,first,bats,throws,team,position`).
- `schedule`: header-based; a few old files (1904, 1921, 1933) ship **without a header row** and get the documented default header; 2022 has two doubleheader games numbered `0` (the key includes the per-team game number); only the schedule exists for 2026.
- `umpires`: `UMPIRES<year>.txt` (`ID,last,first`), one file per season, so `umpire_id` repeats across seasons.
- `discrepancies`: the AL/NL/federal discrepancy lists. About 5,300 rows in the 1900–1949 files have 14 instead of 15 fields and are padded with NULLs (logged); an unnamed 13th column is exposed as `flag`.

### 7. Reference Directories (`reference/`)
Every CSV in the tree's `reference/` directory is ingested by header name: `ballparks`, `teams`, `ejections`, `coaches`, `relatives`, `biofile` and `biofile0`. Quirks verified on the real files:
- Dates are `M/D/YYYY` (single digits allowed) in `biofile`, `ballparks`, `coaches`, `ejections` and `YYYYMMDD` in `biofile0`.
- Birth/death dates in both biofiles can be **partial** (`1906`, `5/1906`, `19010000`); those two columns stay text, all other dates are `date32`.
- `biofile` and `biofile0` describe the same 27,049 people with different headers and encodings; both are kept.
- Column order never matters: columns are matched by upstream header name, unknown columns land in `_extras` (JSON) with a one-time `schema_drift` warning.

## Freshness
Retrosheet data is immutable at a pinned commit: raw files and processed chunks are never re-fetched unless the pin moves (`baseballpy refs update`) or `refresh=True` is passed.

## Dataset reference (generated)

<!-- BEGIN GENERATED:retrosheet.description_sources -->
### Description sources

- `chadwick_cwdaily`: https://raw.githubusercontent.com/chadwickbureau/chadwick/master/doc/cwdaily.rst
- `chadwick_cwevent`: https://raw.githubusercontent.com/chadwickbureau/chadwick/master/doc/cwevent.rst
- `chadwick_cwsub`: https://raw.githubusercontent.com/chadwickbureau/chadwick/master/doc/cwsub.rst
- `retrosheet_glfields`: Retrosheet game-log field guide (glfields.txt), read from the copy in the book companion repository maxtoki/baseball_R because retrosheet.org was unreachable: https://raw.githubusercontent.com/maxtoki/baseball_R/master/data/glfields.txt

<!-- END GENERATED:retrosheet.description_sources -->

<!-- BEGIN GENERATED:retrosheet.boxscores_batting -->
### Dataset: boxscores_batting

Batting box score lines.

- **View:** `retrosheet_boxscores_batting`
- **Processed path:** `processed/retrosheet/boxscores_batting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `team_id`, `player_id`, `slot`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `team_id` | string | yes | — | TODO |
| `player_id` | string | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `slot` | int8 | yes | — | TODO |
| `pos` | int8 | yes | — | TODO |
| `ab` | int16 | yes | — | TODO |
| `r` | int16 | yes | — | TODO |
| `h` | int16 | yes | — | TODO |
| `d` | int16 | yes | — | TODO |
| `t` | int16 | yes | — | TODO |
| `hr` | int16 | yes | — | TODO |
| `rbi` | int16 | yes | — | TODO |
| `bb` | int16 | yes | — | TODO |
| `ibb` | int16 | yes | — | TODO |
| `so` | int16 | yes | — | TODO |
| `hbp` | int16 | yes | — | TODO |
| `sh` | int16 | yes | — | TODO |
| `sf` | int16 | yes | — | TODO |
| `sb` | int16 | yes | — | TODO |
| `cs` | int16 | yes | — | TODO |
| `gidp` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |

<!-- END GENERATED:retrosheet.boxscores_batting -->

<!-- BEGIN GENERATED:retrosheet.boxscores_pitching -->
### Dataset: boxscores_pitching

Pitching box score lines.

- **View:** `retrosheet_boxscores_pitching`
- **Processed path:** `processed/retrosheet/boxscores_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `team_id`, `pitcher_id`, `seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `team_id` | string | yes | — | TODO |
| `pitcher_id` | string | yes | — | TODO |
| `pitcher_name` | string | yes | — | TODO |
| `starter_fl` | bool | yes | — | TODO |
| `seq` | int8 | yes | — | TODO |
| `outs_recorded` | int16 | yes | — | TODO |
| `bf` | int16 | yes | — | TODO |
| `h` | int16 | yes | — | TODO |
| `r` | int16 | yes | — | TODO |
| `er` | int16 | yes | — | TODO |
| `bb` | int16 | yes | — | TODO |
| `ibb` | int16 | yes | — | TODO |
| `so` | int16 | yes | — | TODO |
| `hr` | int16 | yes | — | TODO |
| `hbp` | int16 | yes | — | TODO |
| `wp` | int16 | yes | — | TODO |
| `bk` | int16 | yes | — | TODO |
| `pitches` | int16 | yes | — | TODO |
| `strikes` | int16 | yes | — | TODO |
| `w` | bool | yes | — | TODO |
| `l` | bool | yes | — | TODO |
| `sv` | bool | yes | — | TODO |
| `cg` | bool | yes | — | TODO |
| `sho` | bool | yes | — | TODO |
| `gf` | bool | yes | — | TODO |

<!-- END GENERATED:retrosheet.boxscores_pitching -->

<!-- BEGIN GENERATED:retrosheet.daily_splits -->
### Dataset: daily_splits

Daily player appearance lines.

- **View:** `retrosheet_daily_splits`
- **Processed path:** `processed/retrosheet/daily_splits/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`, `TEAM_ID`, `PLAYER_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — | Game ID (src: chadwick_cwdaily) |
| `GAME_DT` | string | yes | — | Game date (src: chadwick_cwdaily) |
| `GAME_CT` | int16 | yes | — | Game number (src: chadwick_cwdaily) |
| `APPEAR_DT` | string | yes | — | Player appearance date (src: chadwick_cwdaily) |
| `TEAM_ID` | string | yes | — | Team ID (src: chadwick_cwdaily) |
| `PLAYER_ID` | string | yes | — | Player ID (src: chadwick_cwdaily) |
| `SLOT_CT` | int16 | yes | — | Batting-order slot (src: chadwick_cwdaily) |
| `SEQ_CT` | int16 | yes | — | Sequence within batting-order slot (src: chadwick_cwdaily) |
| `HOME_FL` | int8 | yes | — | Home-team flag (src: chadwick_cwdaily) |
| `OPPONENT_ID` | string | yes | — | Opponent ID (src: chadwick_cwdaily) |
| `PARK_ID` | string | yes | — | Park ID (src: chadwick_cwdaily) |
| `B_G` | int16 | yes | — | Games played as a batter (src: chadwick_cwdaily) |
| `B_PA` | int16 | yes | — | Plate appearances (src: chadwick_cwdaily) |
| `B_AB` | int16 | yes | — | At bats (src: chadwick_cwdaily) |
| `B_R` | int16 | yes | — | Runs (src: chadwick_cwdaily) |
| `B_H` | int16 | yes | — | Hits (src: chadwick_cwdaily) |
| `B_TB` | int16 | yes | — | Total bases (src: chadwick_cwdaily) |
| `B_2B` | int16 | yes | — | Doubles (src: chadwick_cwdaily) |
| `B_3B` | int16 | yes | — | Triples (src: chadwick_cwdaily) |
| `B_HR` | int16 | yes | — | Home runs (src: chadwick_cwdaily) |
| `B_HR4` | int16 | yes | — | Grand slams (src: chadwick_cwdaily) |
| `B_RBI` | int16 | yes | — | Runs batted in (src: chadwick_cwdaily) |
| `B_GW` | int16 | yes | — | Game-winning RBI (src: chadwick_cwdaily) |
| `B_BB` | int16 | yes | — | Walks (src: chadwick_cwdaily) |
| `B_IBB` | int16 | yes | — | Intentional walks (src: chadwick_cwdaily) |
| `B_SO` | int16 | yes | — | Strikeouts (src: chadwick_cwdaily) |
| `B_GDP` | int16 | yes | — | Grounded into double plays (src: chadwick_cwdaily) |
| `B_HP` | int16 | yes | — | Hit by pitch (src: chadwick_cwdaily) |
| `B_SH` | int16 | yes | — | Sacrifice hits (src: chadwick_cwdaily) |
| `B_SF` | int16 | yes | — | Sacrifice flies (src: chadwick_cwdaily) |
| `B_SB` | int16 | yes | — | Stolen bases (src: chadwick_cwdaily) |
| `B_CS` | int16 | yes | — | Caught stealing (src: chadwick_cwdaily) |
| `B_XI` | int16 | yes | — | Reached on interference (src: chadwick_cwdaily) |
| `B_G_DH` | int8 | yes | — | Games as designated hitter (src: chadwick_cwdaily) |
| `B_G_PH` | int8 | yes | — | Games as pinch hitter (src: chadwick_cwdaily) |
| `B_G_PR` | int8 | yes | — | Games as pinch runner (src: chadwick_cwdaily) |
| `P_G` | int16 | yes | — | Games pitched (src: chadwick_cwdaily) |
| `P_GS` | int16 | yes | — | Games started (src: chadwick_cwdaily) |
| `P_CG` | int16 | yes | — | Complete games (src: chadwick_cwdaily) |
| `P_SHO` | int16 | yes | — | Shutouts (src: chadwick_cwdaily) |
| `P_GF` | int16 | yes | — | Games finished (src: chadwick_cwdaily) |
| `P_W` | int16 | yes | — | Wins (src: chadwick_cwdaily) |
| `P_L` | int16 | yes | — | Losses (src: chadwick_cwdaily) |
| `P_SV` | int16 | yes | — | Saves (src: chadwick_cwdaily) |
| `P_OUT` | int16 | yes | — | Outs recorded (src: chadwick_cwdaily) |
| `P_TBF` | int16 | yes | — | Batters faced (src: chadwick_cwdaily) |
| `P_AB` | int16 | yes | — | At bats against (src: chadwick_cwdaily) |
| `P_R` | int16 | yes | — | Runs allowed (src: chadwick_cwdaily) |
| `P_ER` | int16 | yes | — | Earned runs allowed (src: chadwick_cwdaily) |
| `P_H` | int16 | yes | — | Hits allowed (src: chadwick_cwdaily) |
| `P_TB` | int16 | yes | — | Total bases allowed (src: chadwick_cwdaily) |
| `P_2B` | int16 | yes | — | Doubles allowed (src: chadwick_cwdaily) |
| `P_3B` | int16 | yes | — | Triples allowed (src: chadwick_cwdaily) |
| `P_HR` | int16 | yes | — | Home runs allowed (src: chadwick_cwdaily) |
| `P_HR4` | int16 | yes | — | Grand slams allowed (src: chadwick_cwdaily) |
| `P_BB` | int16 | yes | — | Walks allowed (src: chadwick_cwdaily) |
| `P_IBB` | int16 | yes | — | Intentional walks allowed (src: chadwick_cwdaily) |
| `P_SO` | int16 | yes | — | Strikeouts (src: chadwick_cwdaily) |
| `P_GDP` | int16 | yes | — | Grounded into double plays (src: chadwick_cwdaily) |
| `P_HP` | int16 | yes | — | Hit batsmen (src: chadwick_cwdaily) |
| `P_SH` | int16 | yes | — | Sacrifice hits against (src: chadwick_cwdaily) |
| `P_SF` | int16 | yes | — | Sacrifice flies against (src: chadwick_cwdaily) |
| `P_XI` | int16 | yes | — | Reached on interference (src: chadwick_cwdaily) |
| `P_WP` | int16 | yes | — | Wild pitches (src: chadwick_cwdaily) |
| `P_BK` | int16 | yes | — | Balks (src: chadwick_cwdaily) |
| `P_IR` | int16 | yes | — | Inherited runners (src: chadwick_cwdaily) |
| `P_IRS` | int16 | yes | — | Inherited runners who scored (src: chadwick_cwdaily) |
| `P_GO` | int16 | yes | — | Ground-ball outs (src: chadwick_cwdaily) |
| `P_AO` | int16 | yes | — | Air outs (src: chadwick_cwdaily) |
| `P_PITCH` | int16 | yes | — | Pitches (src: chadwick_cwdaily) |
| `P_STRIKE` | int16 | yes | — | Strikes (src: chadwick_cwdaily) |
| `F_P_G` | int16 | yes | — | TODO |
| `F_P_GS` | int16 | yes | — | TODO |
| `F_P_OUT` | int16 | yes | — | TODO |
| `F_P_TC` | int16 | yes | — | TODO |
| `F_P_PO` | int16 | yes | — | TODO |
| `F_P_A` | int16 | yes | — | TODO |
| `F_P_E` | int16 | yes | — | TODO |
| `F_P_DP` | int16 | yes | — | TODO |
| `F_P_TP` | int16 | yes | — | TODO |
| `F_C_G` | int16 | yes | — | TODO |
| `F_C_GS` | int16 | yes | — | TODO |
| `F_C_OUT` | int16 | yes | — | TODO |
| `F_C_TC` | int16 | yes | — | TODO |
| `F_C_PO` | int16 | yes | — | TODO |
| `F_C_A` | int16 | yes | — | TODO |
| `F_C_E` | int16 | yes | — | TODO |
| `F_C_DP` | int16 | yes | — | TODO |
| `F_C_TP` | int16 | yes | — | TODO |
| `F_C_PB` | int16 | yes | — | Passed balls (src: chadwick_cwdaily) |
| `F_C_XI` | int16 | yes | — | Catcher's interference (src: chadwick_cwdaily) |
| `F_1B_G` | int16 | yes | — | TODO |
| `F_1B_GS` | int16 | yes | — | TODO |
| `F_1B_OUT` | int16 | yes | — | TODO |
| `F_1B_TC` | int16 | yes | — | TODO |
| `F_1B_PO` | int16 | yes | — | TODO |
| `F_1B_A` | int16 | yes | — | TODO |
| `F_1B_E` | int16 | yes | — | TODO |
| `F_1B_DP` | int16 | yes | — | TODO |
| `F_1B_TP` | int16 | yes | — | TODO |
| `F_2B_G` | int16 | yes | — | TODO |
| `F_2B_GS` | int16 | yes | — | TODO |
| `F_2B_OUT` | int16 | yes | — | TODO |
| `F_2B_TC` | int16 | yes | — | TODO |
| `F_2B_PO` | int16 | yes | — | TODO |
| `F_2B_A` | int16 | yes | — | TODO |
| `F_2B_E` | int16 | yes | — | TODO |
| `F_2B_DP` | int16 | yes | — | TODO |
| `F_2B_TP` | int16 | yes | — | TODO |
| `F_3B_G` | int16 | yes | — | TODO |
| `F_3B_GS` | int16 | yes | — | TODO |
| `F_3B_OUT` | int16 | yes | — | TODO |
| `F_3B_TC` | int16 | yes | — | TODO |
| `F_3B_PO` | int16 | yes | — | TODO |
| `F_3B_A` | int16 | yes | — | TODO |
| `F_3B_E` | int16 | yes | — | TODO |
| `F_3B_DP` | int16 | yes | — | TODO |
| `F_3B_TP` | int16 | yes | — | TODO |
| `F_SS_G` | int16 | yes | — | TODO |
| `F_SS_GS` | int16 | yes | — | TODO |
| `F_SS_OUT` | int16 | yes | — | TODO |
| `F_SS_TC` | int16 | yes | — | TODO |
| `F_SS_PO` | int16 | yes | — | TODO |
| `F_SS_A` | int16 | yes | — | TODO |
| `F_SS_E` | int16 | yes | — | TODO |
| `F_SS_DP` | int16 | yes | — | TODO |
| `F_SS_TP` | int16 | yes | — | TODO |
| `F_LF_G` | int16 | yes | — | TODO |
| `F_LF_GS` | int16 | yes | — | TODO |
| `F_LF_OUT` | int16 | yes | — | TODO |
| `F_LF_TC` | int16 | yes | — | TODO |
| `F_LF_PO` | int16 | yes | — | TODO |
| `F_LF_A` | int16 | yes | — | TODO |
| `F_LF_E` | int16 | yes | — | TODO |
| `F_LF_DP` | int16 | yes | — | TODO |
| `F_LF_TP` | int16 | yes | — | TODO |
| `F_CF_G` | int16 | yes | — | TODO |
| `F_CF_GS` | int16 | yes | — | TODO |
| `F_CF_OUT` | int16 | yes | — | TODO |
| `F_CF_TC` | int16 | yes | — | TODO |
| `F_CF_PO` | int16 | yes | — | TODO |
| `F_CF_A` | int16 | yes | — | TODO |
| `F_CF_E` | int16 | yes | — | TODO |
| `F_CF_DP` | int16 | yes | — | TODO |
| `F_CF_TP` | int16 | yes | — | TODO |
| `F_RF_G` | int16 | yes | — | TODO |
| `F_RF_GS` | int16 | yes | — | TODO |
| `F_RF_OUT` | int16 | yes | — | TODO |
| `F_RF_TC` | int16 | yes | — | TODO |
| `F_RF_PO` | int16 | yes | — | TODO |
| `F_RF_A` | int16 | yes | — | TODO |
| `F_RF_E` | int16 | yes | — | TODO |
| `F_RF_DP` | int16 | yes | — | TODO |
| `F_RF_TP` | int16 | yes | — | TODO |

<!-- END GENERATED:retrosheet.daily_splits -->

<!-- BEGIN GENERATED:retrosheet.discrepancies -->
### Dataset: discrepancies

Known data discrepancies (seasons/<year>/*discs.csv).

- **View:** `retrosheet_discrepancies`
- **Processed path:** `processed/retrosheet/discrepancies/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `disc_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `disc_id` | string | yes | `ID` | TODO |
| `player_id` | string | yes | `Player` | TODO |
| `year` | int16 | yes | `Year` | TODO |
| `team_id` | string | yes | `Team` | TODO |
| `type` | string | yes | `Type` | TODO |
| `position` | string | yes | `Pos` | TODO |
| `category` | string | yes | `Cat` | TODO |
| `game_id` | string | yes | `Game` | TODO |
| `retro_value` | double | yes | `Retro` | TODO |
| `official_value` | double | yes | `Official` | TODO |
| `cross_id` | string | yes | `Cross` | TODO |
| `code` | string | yes | `Code` | TODO |
| `flag` | string | yes | `X|col_13` | TODO |
| `notes` | string | yes | `Notes` | TODO |
| `accepted` | string | yes | `Accepted` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.discrepancies -->

<!-- BEGIN GENERATED:retrosheet.events -->
### Dataset: events

Regular-season play-by-play events.

- **View:** `retrosheet_events`
- **Processed path:** `processed/retrosheet/events/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`, `EVENT_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — | Game ID (src: chadwick_cwevent) |
| `AWAY_TEAM_ID` | string | yes | — | Visiting team (src: chadwick_cwevent) |
| `INN_CT` | int16 | yes | — | Inning (src: chadwick_cwevent) |
| `BAT_HOME_ID` | int8 | yes | — | Batting team (src: chadwick_cwevent) |
| `OUTS_CT` | int8 | yes | — | Outs (src: chadwick_cwevent) |
| `BALLS_CT` | int8 | yes | — | Balls (src: chadwick_cwevent) |
| `STRIKES_CT` | int8 | yes | — | Strikes (src: chadwick_cwevent) |
| `PITCH_SEQ_TX` | string | yes | — | Pitch sequence (src: chadwick_cwevent) |
| `AWAY_SCORE_CT` | int16 | yes | — | Visitor score (src: chadwick_cwevent) |
| `HOME_SCORE_CT` | int16 | yes | — | Home score (src: chadwick_cwevent) |
| `BAT_ID` | string | yes | — | Batter (src: chadwick_cwevent) |
| `BAT_HAND_CD` | string | yes | — | Batter hand (src: chadwick_cwevent) |
| `RESP_BAT_ID` | string | yes | — | Result batter (src: chadwick_cwevent) |
| `RESP_BAT_HAND_CD` | string | yes | — | Result batter hand (src: chadwick_cwevent) |
| `PIT_ID` | string | yes | — | Pitcher (src: chadwick_cwevent) |
| `PIT_HAND_CD` | string | yes | — | Pitcher hand (src: chadwick_cwevent) |
| `RESP_PIT_ID` | string | yes | — | Result pitcher (src: chadwick_cwevent) |
| `RESP_PIT_HAND_CD` | string | yes | — | Result pitcher hand (src: chadwick_cwevent) |
| `POS2_FLD_ID` | string | yes | — | Catcher (src: chadwick_cwevent) |
| `POS3_FLD_ID` | string | yes | — | First baseman (src: chadwick_cwevent) |
| `POS4_FLD_ID` | string | yes | — | Second baseman (src: chadwick_cwevent) |
| `POS5_FLD_ID` | string | yes | — | Third baseman (src: chadwick_cwevent) |
| `POS6_FLD_ID` | string | yes | — | Shortstop (src: chadwick_cwevent) |
| `POS7_FLD_ID` | string | yes | — | Left fielder (src: chadwick_cwevent) |
| `POS8_FLD_ID` | string | yes | — | Center fielder (src: chadwick_cwevent) |
| `POS9_FLD_ID` | string | yes | — | Right fielder (src: chadwick_cwevent) |
| `BASE1_RUN_ID` | string | yes | — | Runner on first (src: chadwick_cwevent) |
| `BASE2_RUN_ID` | string | yes | — | Runner on second (src: chadwick_cwevent) |
| `BASE3_RUN_ID` | string | yes | — | Runner on third (src: chadwick_cwevent) |
| `EVENT_TX` | string | yes | — | Event text (src: chadwick_cwevent) |
| `LEADOFF_FL` | bool | yes | — | Leadoff flag (src: chadwick_cwevent) |
| `PH_FL` | bool | yes | — | Pinch-hit flag (src: chadwick_cwevent) |
| `BAT_FLD_CD` | int8 | yes | — | Defensive position (src: chadwick_cwevent) |
| `BAT_LINEUP_ID` | int8 | yes | — | Lineup position (src: chadwick_cwevent) |
| `EVENT_CD` | int16 | yes | — | Event type (src: chadwick_cwevent) |
| `BAT_EVENT_FL` | bool | yes | — | Batter event flag (src: chadwick_cwevent) |
| `AB_FL` | bool | yes | — | Official time at bat flag (src: chadwick_cwevent) |
| `H_CD` | int8 | yes | — | Hit value (src: chadwick_cwevent) |
| `SH_FL` | bool | yes | — | Sacrifice hit flag (src: chadwick_cwevent) |
| `SF_FL` | bool | yes | — | Sacrifice fly flag (src: chadwick_cwevent) |
| `EVENT_OUTS_CT` | int8 | yes | — | Outs on play (src: chadwick_cwevent) |
| `DP_FL` | bool | yes | — | Double play flag (src: chadwick_cwevent) |
| `TP_FL` | bool | yes | — | Triple play flag (src: chadwick_cwevent) |
| `RBI_CT` | int8 | yes | — | RBI on play (src: chadwick_cwevent) |
| `WP_FL` | bool | yes | — | Wild pitch flag (src: chadwick_cwevent) |
| `PB_FL` | bool | yes | — | Passed ball flag (src: chadwick_cwevent) |
| `FLD_CD` | int8 | yes | — | Fielded by (src: chadwick_cwevent) |
| `BATTEDBALL_CD` | string | yes | — | Batted ball type (src: chadwick_cwevent) |
| `BUNT_FL` | bool | yes | — | Bunt flag (src: chadwick_cwevent) |
| `FOUL_FL` | bool | yes | — | Foul flag (src: chadwick_cwevent) |
| `BATTEDBALL_LOC_TX` | string | yes | — | Hit location (src: chadwick_cwevent) |
| `ERR_CT` | int8 | yes | — | Number of errors (src: chadwick_cwevent) |
| `ERR1_FLD_CD` | int8 | yes | — | 1st error player (src: chadwick_cwevent) |
| `ERR1_CD` | string | yes | — | 1st error type (src: chadwick_cwevent) |
| `ERR2_FLD_CD` | int8 | yes | — | 2nd error player (src: chadwick_cwevent) |
| `ERR2_CD` | string | yes | — | 2nd error type (src: chadwick_cwevent) |
| `ERR3_FLD_CD` | int8 | yes | — | 3rd error player (src: chadwick_cwevent) |
| `ERR3_CD` | string | yes | — | 3rd error type (src: chadwick_cwevent) |
| `BAT_DEST_ID` | int8 | yes | — | Batter destination (src: chadwick_cwevent) |
| `RUN1_DEST_ID` | int8 | yes | — | Runner on first destination (src: chadwick_cwevent) |
| `RUN2_DEST_ID` | int8 | yes | — | Runner on second destination (src: chadwick_cwevent) |
| `RUN3_DEST_ID` | int8 | yes | — | Runner on third destination (src: chadwick_cwevent) |
| `BAT_PLAY_TX` | string | yes | — | Play on batter (src: chadwick_cwevent) |
| `RUN1_PLAY_TX` | string | yes | — | Play on runner on first (src: chadwick_cwevent) |
| `RUN2_PLAY_TX` | string | yes | — | Play on runner on second (src: chadwick_cwevent) |
| `RUN3_PLAY_TX` | string | yes | — | Play on runner on third (src: chadwick_cwevent) |
| `RUN1_SB_FL` | bool | yes | — | Stolen base for runner on first (src: chadwick_cwevent) |
| `RUN2_SB_FL` | bool | yes | — | Stolen base for runner on second (src: chadwick_cwevent) |
| `RUN3_SB_FL` | bool | yes | — | Stolen base for runner on third (src: chadwick_cwevent) |
| `RUN1_CS_FL` | bool | yes | — | Caught stealing for runner on first (src: chadwick_cwevent) |
| `RUN2_CS_FL` | bool | yes | — | Caught stealing for runner on second (src: chadwick_cwevent) |
| `RUN3_CS_FL` | bool | yes | — | Caught stealing for runner on third (src: chadwick_cwevent) |
| `RUN1_PK_FL` | bool | yes | — | Pickoff of runner on first (src: chadwick_cwevent) |
| `RUN2_PK_FL` | bool | yes | — | Pickoff of runner on second (src: chadwick_cwevent) |
| `RUN3_PK_FL` | bool | yes | — | Pickoff of runner on third (src: chadwick_cwevent) |
| `RUN1_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on first (src: chadwick_cwevent) |
| `RUN2_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on second (src: chadwick_cwevent) |
| `RUN3_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on third (src: chadwick_cwevent) |
| `GAME_NEW_FL` | bool | yes | — | New game flag (src: chadwick_cwevent) |
| `GAME_END_FL` | bool | yes | — | End game flag (src: chadwick_cwevent) |
| `PR_RUN1_FL` | bool | yes | — | Pinch-runner on first (src: chadwick_cwevent) |
| `PR_RUN2_FL` | bool | yes | — | Pinch-runner on second (src: chadwick_cwevent) |
| `PR_RUN3_FL` | bool | yes | — | Pinch-runner on third (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN1_ID` | string | yes | — | Runner removed for pinch-runner on first (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN2_ID` | string | yes | — | Runner removed for pinch-runner on second (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN3_ID` | string | yes | — | Runner removed for pinch-runner on third (src: chadwick_cwevent) |
| `REMOVED_FOR_PH_BAT_ID` | string | yes | — | Batter removed for pinch-hitter (src: chadwick_cwevent) |
| `REMOVED_FOR_PH_BAT_FLD_CD` | int8 | yes | — | Position of batter removed for pinch-hitter (src: chadwick_cwevent) |
| `PO1_FLD_CD` | int8 | yes | — | Fielder with first putout (src: chadwick_cwevent) |
| `PO2_FLD_CD` | int8 | yes | — | Fielder with second putout (src: chadwick_cwevent) |
| `PO3_FLD_CD` | int8 | yes | — | Fielder with third putout (src: chadwick_cwevent) |
| `ASS1_FLD_CD` | int8 | yes | — | Fielder with first assist (src: chadwick_cwevent) |
| `ASS2_FLD_CD` | int8 | yes | — | Fielder with second assist (src: chadwick_cwevent) |
| `ASS3_FLD_CD` | int8 | yes | — | Fielder with third assist (src: chadwick_cwevent) |
| `ASS4_FLD_CD` | int16 | yes | — | TODO |
| `ASS5_FLD_CD` | int16 | yes | — | TODO |
| `EVENT_ID` | int16 | yes | — | TODO |
| `HOME_TEAM_ID` | string | yes | — | TODO |
| `BAT_TEAM_ID` | string | yes | — | TODO |
| `FLD_TEAM_ID` | string | yes | — | TODO |
| `BAT_LAST_ID` | int8 | yes | — | half inning (differs from batting team if home team bats first) (src: chadwick_cwevent) |
| `INN_NEW_FL` | bool | yes | — | TODO |
| `INN_END_FL` | bool | yes | — | TODO |
| `START_BAT_SCORE_CT` | int16 | yes | — | TODO |
| `START_FLD_SCORE_CT` | int16 | yes | — | TODO |
| `INN_RUNS_CT` | int16 | yes | — | TODO |
| `GAME_PA_CT` | int16 | yes | — | TODO |
| `INN_PA_CT` | int16 | yes | — | TODO |
| `PA_NEW_FL` | bool | yes | — | TODO |
| `PA_TRUNC_FL` | bool | yes | — | TODO |
| `START_BASES_CD` | int16 | yes | — | TODO |
| `END_BASES_CD` | int16 | yes | — | TODO |
| `BAT_START_FL` | bool | yes | — | TODO |
| `RESP_BAT_START_FL` | bool | yes | — | TODO |
| `BAT_ON_DECK_ID` | string | yes | — | TODO |
| `BAT_IN_HOLD_ID` | string | yes | — | TODO |
| `PIT_START_FL` | bool | yes | — | TODO |
| `RESP_PIT_START_FL` | bool | yes | — | TODO |
| `RUN1_FLD_CD` | int16 | yes | — | TODO |
| `RUN1_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN1_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN2_FLD_CD` | int16 | yes | — | TODO |
| `RUN2_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN2_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN3_FLD_CD` | int16 | yes | — | TODO |
| `RUN3_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN3_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN1_RESP_CAT_ID` | string | yes | — | TODO |
| `RUN2_RESP_CAT_ID` | string | yes | — | TODO |
| `RUN3_RESP_CAT_ID` | string | yes | — | TODO |
| `PA_BALL_CT` | int16 | yes | — | TODO |
| `PA_CALLED_BALL_CT` | int16 | yes | — | TODO |
| `PA_INTENT_BALL_CT` | int16 | yes | — | TODO |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | TODO |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | TODO |
| `PA_OTHER_BALL_CT` | int16 | yes | — | TODO |
| `PA_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | TODO |
| `EVENT_RUNS_CT` | int16 | yes | — | TODO |
| `FLD_ID` | string | yes | — | TODO |
| `BASE2_FORCE_FL` | bool | yes | — | TODO |
| `BASE3_FORCE_FL` | bool | yes | — | TODO |
| `BASE4_FORCE_FL` | bool | yes | — | TODO |
| `BAT_SAFE_ERR_FL` | bool | yes | — | TODO |
| `BAT_FATE_ID` | int16 | yes | — | TODO |
| `RUN1_FATE_ID` | int16 | yes | — | TODO |
| `RUN2_FATE_ID` | int16 | yes | — | TODO |
| `RUN3_FATE_ID` | int16 | yes | — | TODO |
| `FATE_RUNS_CT` | int16 | yes | — | TODO |
| `ASS6_FLD_CD` | int16 | yes | — | TODO |
| `ASS7_FLD_CD` | int16 | yes | — | TODO |
| `ASS8_FLD_CD` | int16 | yes | — | TODO |
| `ASS9_FLD_CD` | int16 | yes | — | TODO |
| `ASS10_FLD_CD` | int16 | yes | — | TODO |
| `UNKNOWN_OUT_EXC_FL` | bool | yes | — | TODO |
| `UNCERTAIN_PLAY_EXC_FL` | bool | yes | — | TODO |
| `COUNT_TX` | string | yes | — | TODO |
| `RUN1_AUTO_FL` | bool | yes | — | TODO |
| `RUN2_AUTO_FL` | bool | yes | — | TODO |
| `RUN3_AUTO_FL` | bool | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.events -->

<!-- BEGIN GENERATED:retrosheet.events_deduced -->
### Dataset: events_deduced

Play-by-play events deduced from box scores (.ED* files).

- **View:** `retrosheet_events_deduced`
- **Processed path:** `processed/retrosheet/events_deduced/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`, `EVENT_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — | Game ID (src: chadwick_cwevent) |
| `AWAY_TEAM_ID` | string | yes | — | Visiting team (src: chadwick_cwevent) |
| `INN_CT` | int16 | yes | — | Inning (src: chadwick_cwevent) |
| `BAT_HOME_ID` | int8 | yes | — | Batting team (src: chadwick_cwevent) |
| `OUTS_CT` | int8 | yes | — | Outs (src: chadwick_cwevent) |
| `BALLS_CT` | int8 | yes | — | Balls (src: chadwick_cwevent) |
| `STRIKES_CT` | int8 | yes | — | Strikes (src: chadwick_cwevent) |
| `PITCH_SEQ_TX` | string | yes | — | Pitch sequence (src: chadwick_cwevent) |
| `AWAY_SCORE_CT` | int16 | yes | — | Visitor score (src: chadwick_cwevent) |
| `HOME_SCORE_CT` | int16 | yes | — | Home score (src: chadwick_cwevent) |
| `BAT_ID` | string | yes | — | Batter (src: chadwick_cwevent) |
| `BAT_HAND_CD` | string | yes | — | Batter hand (src: chadwick_cwevent) |
| `RESP_BAT_ID` | string | yes | — | Result batter (src: chadwick_cwevent) |
| `RESP_BAT_HAND_CD` | string | yes | — | Result batter hand (src: chadwick_cwevent) |
| `PIT_ID` | string | yes | — | Pitcher (src: chadwick_cwevent) |
| `PIT_HAND_CD` | string | yes | — | Pitcher hand (src: chadwick_cwevent) |
| `RESP_PIT_ID` | string | yes | — | Result pitcher (src: chadwick_cwevent) |
| `RESP_PIT_HAND_CD` | string | yes | — | Result pitcher hand (src: chadwick_cwevent) |
| `POS2_FLD_ID` | string | yes | — | Catcher (src: chadwick_cwevent) |
| `POS3_FLD_ID` | string | yes | — | First baseman (src: chadwick_cwevent) |
| `POS4_FLD_ID` | string | yes | — | Second baseman (src: chadwick_cwevent) |
| `POS5_FLD_ID` | string | yes | — | Third baseman (src: chadwick_cwevent) |
| `POS6_FLD_ID` | string | yes | — | Shortstop (src: chadwick_cwevent) |
| `POS7_FLD_ID` | string | yes | — | Left fielder (src: chadwick_cwevent) |
| `POS8_FLD_ID` | string | yes | — | Center fielder (src: chadwick_cwevent) |
| `POS9_FLD_ID` | string | yes | — | Right fielder (src: chadwick_cwevent) |
| `BASE1_RUN_ID` | string | yes | — | Runner on first (src: chadwick_cwevent) |
| `BASE2_RUN_ID` | string | yes | — | Runner on second (src: chadwick_cwevent) |
| `BASE3_RUN_ID` | string | yes | — | Runner on third (src: chadwick_cwevent) |
| `EVENT_TX` | string | yes | — | Event text (src: chadwick_cwevent) |
| `LEADOFF_FL` | bool | yes | — | Leadoff flag (src: chadwick_cwevent) |
| `PH_FL` | bool | yes | — | Pinch-hit flag (src: chadwick_cwevent) |
| `BAT_FLD_CD` | int8 | yes | — | Defensive position (src: chadwick_cwevent) |
| `BAT_LINEUP_ID` | int8 | yes | — | Lineup position (src: chadwick_cwevent) |
| `EVENT_CD` | int16 | yes | — | Event type (src: chadwick_cwevent) |
| `BAT_EVENT_FL` | bool | yes | — | Batter event flag (src: chadwick_cwevent) |
| `AB_FL` | bool | yes | — | Official time at bat flag (src: chadwick_cwevent) |
| `H_CD` | int8 | yes | — | Hit value (src: chadwick_cwevent) |
| `SH_FL` | bool | yes | — | Sacrifice hit flag (src: chadwick_cwevent) |
| `SF_FL` | bool | yes | — | Sacrifice fly flag (src: chadwick_cwevent) |
| `EVENT_OUTS_CT` | int8 | yes | — | Outs on play (src: chadwick_cwevent) |
| `DP_FL` | bool | yes | — | Double play flag (src: chadwick_cwevent) |
| `TP_FL` | bool | yes | — | Triple play flag (src: chadwick_cwevent) |
| `RBI_CT` | int8 | yes | — | RBI on play (src: chadwick_cwevent) |
| `WP_FL` | bool | yes | — | Wild pitch flag (src: chadwick_cwevent) |
| `PB_FL` | bool | yes | — | Passed ball flag (src: chadwick_cwevent) |
| `FLD_CD` | int8 | yes | — | Fielded by (src: chadwick_cwevent) |
| `BATTEDBALL_CD` | string | yes | — | Batted ball type (src: chadwick_cwevent) |
| `BUNT_FL` | bool | yes | — | Bunt flag (src: chadwick_cwevent) |
| `FOUL_FL` | bool | yes | — | Foul flag (src: chadwick_cwevent) |
| `BATTEDBALL_LOC_TX` | string | yes | — | Hit location (src: chadwick_cwevent) |
| `ERR_CT` | int8 | yes | — | Number of errors (src: chadwick_cwevent) |
| `ERR1_FLD_CD` | int8 | yes | — | 1st error player (src: chadwick_cwevent) |
| `ERR1_CD` | string | yes | — | 1st error type (src: chadwick_cwevent) |
| `ERR2_FLD_CD` | int8 | yes | — | 2nd error player (src: chadwick_cwevent) |
| `ERR2_CD` | string | yes | — | 2nd error type (src: chadwick_cwevent) |
| `ERR3_FLD_CD` | int8 | yes | — | 3rd error player (src: chadwick_cwevent) |
| `ERR3_CD` | string | yes | — | 3rd error type (src: chadwick_cwevent) |
| `BAT_DEST_ID` | int8 | yes | — | Batter destination (src: chadwick_cwevent) |
| `RUN1_DEST_ID` | int8 | yes | — | Runner on first destination (src: chadwick_cwevent) |
| `RUN2_DEST_ID` | int8 | yes | — | Runner on second destination (src: chadwick_cwevent) |
| `RUN3_DEST_ID` | int8 | yes | — | Runner on third destination (src: chadwick_cwevent) |
| `BAT_PLAY_TX` | string | yes | — | Play on batter (src: chadwick_cwevent) |
| `RUN1_PLAY_TX` | string | yes | — | Play on runner on first (src: chadwick_cwevent) |
| `RUN2_PLAY_TX` | string | yes | — | Play on runner on second (src: chadwick_cwevent) |
| `RUN3_PLAY_TX` | string | yes | — | Play on runner on third (src: chadwick_cwevent) |
| `RUN1_SB_FL` | bool | yes | — | Stolen base for runner on first (src: chadwick_cwevent) |
| `RUN2_SB_FL` | bool | yes | — | Stolen base for runner on second (src: chadwick_cwevent) |
| `RUN3_SB_FL` | bool | yes | — | Stolen base for runner on third (src: chadwick_cwevent) |
| `RUN1_CS_FL` | bool | yes | — | Caught stealing for runner on first (src: chadwick_cwevent) |
| `RUN2_CS_FL` | bool | yes | — | Caught stealing for runner on second (src: chadwick_cwevent) |
| `RUN3_CS_FL` | bool | yes | — | Caught stealing for runner on third (src: chadwick_cwevent) |
| `RUN1_PK_FL` | bool | yes | — | Pickoff of runner on first (src: chadwick_cwevent) |
| `RUN2_PK_FL` | bool | yes | — | Pickoff of runner on second (src: chadwick_cwevent) |
| `RUN3_PK_FL` | bool | yes | — | Pickoff of runner on third (src: chadwick_cwevent) |
| `RUN1_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on first (src: chadwick_cwevent) |
| `RUN2_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on second (src: chadwick_cwevent) |
| `RUN3_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on third (src: chadwick_cwevent) |
| `GAME_NEW_FL` | bool | yes | — | New game flag (src: chadwick_cwevent) |
| `GAME_END_FL` | bool | yes | — | End game flag (src: chadwick_cwevent) |
| `PR_RUN1_FL` | bool | yes | — | Pinch-runner on first (src: chadwick_cwevent) |
| `PR_RUN2_FL` | bool | yes | — | Pinch-runner on second (src: chadwick_cwevent) |
| `PR_RUN3_FL` | bool | yes | — | Pinch-runner on third (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN1_ID` | string | yes | — | Runner removed for pinch-runner on first (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN2_ID` | string | yes | — | Runner removed for pinch-runner on second (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN3_ID` | string | yes | — | Runner removed for pinch-runner on third (src: chadwick_cwevent) |
| `REMOVED_FOR_PH_BAT_ID` | string | yes | — | Batter removed for pinch-hitter (src: chadwick_cwevent) |
| `REMOVED_FOR_PH_BAT_FLD_CD` | int8 | yes | — | Position of batter removed for pinch-hitter (src: chadwick_cwevent) |
| `PO1_FLD_CD` | int8 | yes | — | Fielder with first putout (src: chadwick_cwevent) |
| `PO2_FLD_CD` | int8 | yes | — | Fielder with second putout (src: chadwick_cwevent) |
| `PO3_FLD_CD` | int8 | yes | — | Fielder with third putout (src: chadwick_cwevent) |
| `ASS1_FLD_CD` | int8 | yes | — | Fielder with first assist (src: chadwick_cwevent) |
| `ASS2_FLD_CD` | int8 | yes | — | Fielder with second assist (src: chadwick_cwevent) |
| `ASS3_FLD_CD` | int8 | yes | — | Fielder with third assist (src: chadwick_cwevent) |
| `ASS4_FLD_CD` | int16 | yes | — | TODO |
| `ASS5_FLD_CD` | int16 | yes | — | TODO |
| `EVENT_ID` | int16 | yes | — | TODO |
| `HOME_TEAM_ID` | string | yes | — | TODO |
| `BAT_TEAM_ID` | string | yes | — | TODO |
| `FLD_TEAM_ID` | string | yes | — | TODO |
| `BAT_LAST_ID` | int8 | yes | — | half inning (differs from batting team if home team bats first) (src: chadwick_cwevent) |
| `INN_NEW_FL` | bool | yes | — | TODO |
| `INN_END_FL` | bool | yes | — | TODO |
| `START_BAT_SCORE_CT` | int16 | yes | — | TODO |
| `START_FLD_SCORE_CT` | int16 | yes | — | TODO |
| `INN_RUNS_CT` | int16 | yes | — | TODO |
| `GAME_PA_CT` | int16 | yes | — | TODO |
| `INN_PA_CT` | int16 | yes | — | TODO |
| `PA_NEW_FL` | bool | yes | — | TODO |
| `PA_TRUNC_FL` | bool | yes | — | TODO |
| `START_BASES_CD` | int16 | yes | — | TODO |
| `END_BASES_CD` | int16 | yes | — | TODO |
| `BAT_START_FL` | bool | yes | — | TODO |
| `RESP_BAT_START_FL` | bool | yes | — | TODO |
| `BAT_ON_DECK_ID` | string | yes | — | TODO |
| `BAT_IN_HOLD_ID` | string | yes | — | TODO |
| `PIT_START_FL` | bool | yes | — | TODO |
| `RESP_PIT_START_FL` | bool | yes | — | TODO |
| `RUN1_FLD_CD` | int16 | yes | — | TODO |
| `RUN1_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN1_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN2_FLD_CD` | int16 | yes | — | TODO |
| `RUN2_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN2_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN3_FLD_CD` | int16 | yes | — | TODO |
| `RUN3_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN3_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN1_RESP_CAT_ID` | string | yes | — | TODO |
| `RUN2_RESP_CAT_ID` | string | yes | — | TODO |
| `RUN3_RESP_CAT_ID` | string | yes | — | TODO |
| `PA_BALL_CT` | int16 | yes | — | TODO |
| `PA_CALLED_BALL_CT` | int16 | yes | — | TODO |
| `PA_INTENT_BALL_CT` | int16 | yes | — | TODO |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | TODO |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | TODO |
| `PA_OTHER_BALL_CT` | int16 | yes | — | TODO |
| `PA_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | TODO |
| `EVENT_RUNS_CT` | int16 | yes | — | TODO |
| `FLD_ID` | string | yes | — | TODO |
| `BASE2_FORCE_FL` | bool | yes | — | TODO |
| `BASE3_FORCE_FL` | bool | yes | — | TODO |
| `BASE4_FORCE_FL` | bool | yes | — | TODO |
| `BAT_SAFE_ERR_FL` | bool | yes | — | TODO |
| `BAT_FATE_ID` | int16 | yes | — | TODO |
| `RUN1_FATE_ID` | int16 | yes | — | TODO |
| `RUN2_FATE_ID` | int16 | yes | — | TODO |
| `RUN3_FATE_ID` | int16 | yes | — | TODO |
| `FATE_RUNS_CT` | int16 | yes | — | TODO |
| `ASS6_FLD_CD` | int16 | yes | — | TODO |
| `ASS7_FLD_CD` | int16 | yes | — | TODO |
| `ASS8_FLD_CD` | int16 | yes | — | TODO |
| `ASS9_FLD_CD` | int16 | yes | — | TODO |
| `ASS10_FLD_CD` | int16 | yes | — | TODO |
| `UNKNOWN_OUT_EXC_FL` | bool | yes | — | TODO |
| `UNCERTAIN_PLAY_EXC_FL` | bool | yes | — | TODO |
| `COUNT_TX` | string | yes | — | TODO |
| `RUN1_AUTO_FL` | bool | yes | — | TODO |
| `RUN2_AUTO_FL` | bool | yes | — | TODO |
| `RUN3_AUTO_FL` | bool | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.events_deduced -->

<!-- BEGIN GENERATED:retrosheet.events_postseason -->
### Dataset: events_postseason

Postseason and all-star play-by-play events.

- **View:** `retrosheet_events_postseason`
- **Processed path:** `processed/retrosheet/events_postseason/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`, `EVENT_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — | Game ID (src: chadwick_cwevent) |
| `AWAY_TEAM_ID` | string | yes | — | Visiting team (src: chadwick_cwevent) |
| `INN_CT` | int16 | yes | — | Inning (src: chadwick_cwevent) |
| `BAT_HOME_ID` | int8 | yes | — | Batting team (src: chadwick_cwevent) |
| `OUTS_CT` | int8 | yes | — | Outs (src: chadwick_cwevent) |
| `BALLS_CT` | int8 | yes | — | Balls (src: chadwick_cwevent) |
| `STRIKES_CT` | int8 | yes | — | Strikes (src: chadwick_cwevent) |
| `PITCH_SEQ_TX` | string | yes | — | Pitch sequence (src: chadwick_cwevent) |
| `AWAY_SCORE_CT` | int16 | yes | — | Visitor score (src: chadwick_cwevent) |
| `HOME_SCORE_CT` | int16 | yes | — | Home score (src: chadwick_cwevent) |
| `BAT_ID` | string | yes | — | Batter (src: chadwick_cwevent) |
| `BAT_HAND_CD` | string | yes | — | Batter hand (src: chadwick_cwevent) |
| `RESP_BAT_ID` | string | yes | — | Result batter (src: chadwick_cwevent) |
| `RESP_BAT_HAND_CD` | string | yes | — | Result batter hand (src: chadwick_cwevent) |
| `PIT_ID` | string | yes | — | Pitcher (src: chadwick_cwevent) |
| `PIT_HAND_CD` | string | yes | — | Pitcher hand (src: chadwick_cwevent) |
| `RESP_PIT_ID` | string | yes | — | Result pitcher (src: chadwick_cwevent) |
| `RESP_PIT_HAND_CD` | string | yes | — | Result pitcher hand (src: chadwick_cwevent) |
| `POS2_FLD_ID` | string | yes | — | Catcher (src: chadwick_cwevent) |
| `POS3_FLD_ID` | string | yes | — | First baseman (src: chadwick_cwevent) |
| `POS4_FLD_ID` | string | yes | — | Second baseman (src: chadwick_cwevent) |
| `POS5_FLD_ID` | string | yes | — | Third baseman (src: chadwick_cwevent) |
| `POS6_FLD_ID` | string | yes | — | Shortstop (src: chadwick_cwevent) |
| `POS7_FLD_ID` | string | yes | — | Left fielder (src: chadwick_cwevent) |
| `POS8_FLD_ID` | string | yes | — | Center fielder (src: chadwick_cwevent) |
| `POS9_FLD_ID` | string | yes | — | Right fielder (src: chadwick_cwevent) |
| `BASE1_RUN_ID` | string | yes | — | Runner on first (src: chadwick_cwevent) |
| `BASE2_RUN_ID` | string | yes | — | Runner on second (src: chadwick_cwevent) |
| `BASE3_RUN_ID` | string | yes | — | Runner on third (src: chadwick_cwevent) |
| `EVENT_TX` | string | yes | — | Event text (src: chadwick_cwevent) |
| `LEADOFF_FL` | bool | yes | — | Leadoff flag (src: chadwick_cwevent) |
| `PH_FL` | bool | yes | — | Pinch-hit flag (src: chadwick_cwevent) |
| `BAT_FLD_CD` | int8 | yes | — | Defensive position (src: chadwick_cwevent) |
| `BAT_LINEUP_ID` | int8 | yes | — | Lineup position (src: chadwick_cwevent) |
| `EVENT_CD` | int16 | yes | — | Event type (src: chadwick_cwevent) |
| `BAT_EVENT_FL` | bool | yes | — | Batter event flag (src: chadwick_cwevent) |
| `AB_FL` | bool | yes | — | Official time at bat flag (src: chadwick_cwevent) |
| `H_CD` | int8 | yes | — | Hit value (src: chadwick_cwevent) |
| `SH_FL` | bool | yes | — | Sacrifice hit flag (src: chadwick_cwevent) |
| `SF_FL` | bool | yes | — | Sacrifice fly flag (src: chadwick_cwevent) |
| `EVENT_OUTS_CT` | int8 | yes | — | Outs on play (src: chadwick_cwevent) |
| `DP_FL` | bool | yes | — | Double play flag (src: chadwick_cwevent) |
| `TP_FL` | bool | yes | — | Triple play flag (src: chadwick_cwevent) |
| `RBI_CT` | int8 | yes | — | RBI on play (src: chadwick_cwevent) |
| `WP_FL` | bool | yes | — | Wild pitch flag (src: chadwick_cwevent) |
| `PB_FL` | bool | yes | — | Passed ball flag (src: chadwick_cwevent) |
| `FLD_CD` | int8 | yes | — | Fielded by (src: chadwick_cwevent) |
| `BATTEDBALL_CD` | string | yes | — | Batted ball type (src: chadwick_cwevent) |
| `BUNT_FL` | bool | yes | — | Bunt flag (src: chadwick_cwevent) |
| `FOUL_FL` | bool | yes | — | Foul flag (src: chadwick_cwevent) |
| `BATTEDBALL_LOC_TX` | string | yes | — | Hit location (src: chadwick_cwevent) |
| `ERR_CT` | int8 | yes | — | Number of errors (src: chadwick_cwevent) |
| `ERR1_FLD_CD` | int8 | yes | — | 1st error player (src: chadwick_cwevent) |
| `ERR1_CD` | string | yes | — | 1st error type (src: chadwick_cwevent) |
| `ERR2_FLD_CD` | int8 | yes | — | 2nd error player (src: chadwick_cwevent) |
| `ERR2_CD` | string | yes | — | 2nd error type (src: chadwick_cwevent) |
| `ERR3_FLD_CD` | int8 | yes | — | 3rd error player (src: chadwick_cwevent) |
| `ERR3_CD` | string | yes | — | 3rd error type (src: chadwick_cwevent) |
| `BAT_DEST_ID` | int8 | yes | — | Batter destination (src: chadwick_cwevent) |
| `RUN1_DEST_ID` | int8 | yes | — | Runner on first destination (src: chadwick_cwevent) |
| `RUN2_DEST_ID` | int8 | yes | — | Runner on second destination (src: chadwick_cwevent) |
| `RUN3_DEST_ID` | int8 | yes | — | Runner on third destination (src: chadwick_cwevent) |
| `BAT_PLAY_TX` | string | yes | — | Play on batter (src: chadwick_cwevent) |
| `RUN1_PLAY_TX` | string | yes | — | Play on runner on first (src: chadwick_cwevent) |
| `RUN2_PLAY_TX` | string | yes | — | Play on runner on second (src: chadwick_cwevent) |
| `RUN3_PLAY_TX` | string | yes | — | Play on runner on third (src: chadwick_cwevent) |
| `RUN1_SB_FL` | bool | yes | — | Stolen base for runner on first (src: chadwick_cwevent) |
| `RUN2_SB_FL` | bool | yes | — | Stolen base for runner on second (src: chadwick_cwevent) |
| `RUN3_SB_FL` | bool | yes | — | Stolen base for runner on third (src: chadwick_cwevent) |
| `RUN1_CS_FL` | bool | yes | — | Caught stealing for runner on first (src: chadwick_cwevent) |
| `RUN2_CS_FL` | bool | yes | — | Caught stealing for runner on second (src: chadwick_cwevent) |
| `RUN3_CS_FL` | bool | yes | — | Caught stealing for runner on third (src: chadwick_cwevent) |
| `RUN1_PK_FL` | bool | yes | — | Pickoff of runner on first (src: chadwick_cwevent) |
| `RUN2_PK_FL` | bool | yes | — | Pickoff of runner on second (src: chadwick_cwevent) |
| `RUN3_PK_FL` | bool | yes | — | Pickoff of runner on third (src: chadwick_cwevent) |
| `RUN1_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on first (src: chadwick_cwevent) |
| `RUN2_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on second (src: chadwick_cwevent) |
| `RUN3_RESP_PIT_ID` | string | yes | — | Pitcher charged with runner on third (src: chadwick_cwevent) |
| `GAME_NEW_FL` | bool | yes | — | New game flag (src: chadwick_cwevent) |
| `GAME_END_FL` | bool | yes | — | End game flag (src: chadwick_cwevent) |
| `PR_RUN1_FL` | bool | yes | — | Pinch-runner on first (src: chadwick_cwevent) |
| `PR_RUN2_FL` | bool | yes | — | Pinch-runner on second (src: chadwick_cwevent) |
| `PR_RUN3_FL` | bool | yes | — | Pinch-runner on third (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN1_ID` | string | yes | — | Runner removed for pinch-runner on first (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN2_ID` | string | yes | — | Runner removed for pinch-runner on second (src: chadwick_cwevent) |
| `REMOVED_FOR_PR_RUN3_ID` | string | yes | — | Runner removed for pinch-runner on third (src: chadwick_cwevent) |
| `REMOVED_FOR_PH_BAT_ID` | string | yes | — | Batter removed for pinch-hitter (src: chadwick_cwevent) |
| `REMOVED_FOR_PH_BAT_FLD_CD` | int8 | yes | — | Position of batter removed for pinch-hitter (src: chadwick_cwevent) |
| `PO1_FLD_CD` | int8 | yes | — | Fielder with first putout (src: chadwick_cwevent) |
| `PO2_FLD_CD` | int8 | yes | — | Fielder with second putout (src: chadwick_cwevent) |
| `PO3_FLD_CD` | int8 | yes | — | Fielder with third putout (src: chadwick_cwevent) |
| `ASS1_FLD_CD` | int8 | yes | — | Fielder with first assist (src: chadwick_cwevent) |
| `ASS2_FLD_CD` | int8 | yes | — | Fielder with second assist (src: chadwick_cwevent) |
| `ASS3_FLD_CD` | int8 | yes | — | Fielder with third assist (src: chadwick_cwevent) |
| `ASS4_FLD_CD` | int16 | yes | — | TODO |
| `ASS5_FLD_CD` | int16 | yes | — | TODO |
| `EVENT_ID` | int16 | yes | — | TODO |
| `HOME_TEAM_ID` | string | yes | — | TODO |
| `BAT_TEAM_ID` | string | yes | — | TODO |
| `FLD_TEAM_ID` | string | yes | — | TODO |
| `BAT_LAST_ID` | int8 | yes | — | half inning (differs from batting team if home team bats first) (src: chadwick_cwevent) |
| `INN_NEW_FL` | bool | yes | — | TODO |
| `INN_END_FL` | bool | yes | — | TODO |
| `START_BAT_SCORE_CT` | int16 | yes | — | TODO |
| `START_FLD_SCORE_CT` | int16 | yes | — | TODO |
| `INN_RUNS_CT` | int16 | yes | — | TODO |
| `GAME_PA_CT` | int16 | yes | — | TODO |
| `INN_PA_CT` | int16 | yes | — | TODO |
| `PA_NEW_FL` | bool | yes | — | TODO |
| `PA_TRUNC_FL` | bool | yes | — | TODO |
| `START_BASES_CD` | int16 | yes | — | TODO |
| `END_BASES_CD` | int16 | yes | — | TODO |
| `BAT_START_FL` | bool | yes | — | TODO |
| `RESP_BAT_START_FL` | bool | yes | — | TODO |
| `BAT_ON_DECK_ID` | string | yes | — | TODO |
| `BAT_IN_HOLD_ID` | string | yes | — | TODO |
| `PIT_START_FL` | bool | yes | — | TODO |
| `RESP_PIT_START_FL` | bool | yes | — | TODO |
| `RUN1_FLD_CD` | int16 | yes | — | TODO |
| `RUN1_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN1_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN2_FLD_CD` | int16 | yes | — | TODO |
| `RUN2_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN2_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN3_FLD_CD` | int16 | yes | — | TODO |
| `RUN3_LINEUP_CD` | int16 | yes | — | TODO |
| `RUN3_ORIGIN_EVENT_ID` | int16 | yes | — | TODO |
| `RUN1_RESP_CAT_ID` | string | yes | — | TODO |
| `RUN2_RESP_CAT_ID` | string | yes | — | TODO |
| `RUN3_RESP_CAT_ID` | string | yes | — | TODO |
| `PA_BALL_CT` | int16 | yes | — | TODO |
| `PA_CALLED_BALL_CT` | int16 | yes | — | TODO |
| `PA_INTENT_BALL_CT` | int16 | yes | — | TODO |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | TODO |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | TODO |
| `PA_OTHER_BALL_CT` | int16 | yes | — | TODO |
| `PA_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | TODO |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | TODO |
| `EVENT_RUNS_CT` | int16 | yes | — | TODO |
| `FLD_ID` | string | yes | — | TODO |
| `BASE2_FORCE_FL` | bool | yes | — | TODO |
| `BASE3_FORCE_FL` | bool | yes | — | TODO |
| `BASE4_FORCE_FL` | bool | yes | — | TODO |
| `BAT_SAFE_ERR_FL` | bool | yes | — | TODO |
| `BAT_FATE_ID` | int16 | yes | — | TODO |
| `RUN1_FATE_ID` | int16 | yes | — | TODO |
| `RUN2_FATE_ID` | int16 | yes | — | TODO |
| `RUN3_FATE_ID` | int16 | yes | — | TODO |
| `FATE_RUNS_CT` | int16 | yes | — | TODO |
| `ASS6_FLD_CD` | int16 | yes | — | TODO |
| `ASS7_FLD_CD` | int16 | yes | — | TODO |
| `ASS8_FLD_CD` | int16 | yes | — | TODO |
| `ASS9_FLD_CD` | int16 | yes | — | TODO |
| `ASS10_FLD_CD` | int16 | yes | — | TODO |
| `UNKNOWN_OUT_EXC_FL` | bool | yes | — | TODO |
| `UNCERTAIN_PLAY_EXC_FL` | bool | yes | — | TODO |
| `COUNT_TX` | string | yes | — | TODO |
| `RUN1_AUTO_FL` | bool | yes | — | TODO |
| `RUN2_AUTO_FL` | bool | yes | — | TODO |
| `RUN3_AUTO_FL` | bool | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.events_postseason -->

<!-- BEGIN GENERATED:retrosheet.gamelogs -->
### Dataset: gamelogs

Regular-season game logs.

- **View:** `retrosheet_gamelogs`
- **Processed path:** `processed/retrosheet/gamelogs/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `date`, `game_num`, `home_team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `date` | date32[day] | yes | — | Date in the form "yyyymmdd" (src: retrosheet_glfields) |
| `game_num` | int8 | yes | — | Number of game (src: retrosheet_glfields) |
| `day_of_week` | string | yes | — | Day of week (src: retrosheet_glfields) |
| `visiting_team` | string | yes | — | Visiting team (src: retrosheet_glfields) |
| `visiting_league` | string | yes | — | Visiting league (src: retrosheet_glfields) |
| `visiting_game_num` | int16 | yes | — | Visiting team game number (src: retrosheet_glfields) |
| `home_team` | string | yes | — | Home team (src: retrosheet_glfields) |
| `home_league` | string | yes | — | Home league (src: retrosheet_glfields) |
| `home_game_num` | int16 | yes | — | Home team game number (src: retrosheet_glfields) |
| `visiting_score` | int16 | yes | — | Visiting team score (src: retrosheet_glfields) |
| `home_score` | int16 | yes | — | Home team score (src: retrosheet_glfields) |
| `outs_total` | int16 | yes | — | Length of game in outs (src: retrosheet_glfields) |
| `day_night` | string | yes | — | Day/night indicator (src: retrosheet_glfields) |
| `completion` | string | yes | — | Completion information (src: retrosheet_glfields) |
| `forfeit` | string | yes | — | Forfeit information (src: retrosheet_glfields) |
| `protest` | string | yes | — | Protest information (src: retrosheet_glfields) |
| `park_id` | string | yes | — | Park ID (src: retrosheet_glfields) |
| `attendance` | int32 | yes | — | Attendance (src: retrosheet_glfields) |
| `time_of_game` | int16 | yes | — | Time of game in minutes (src: retrosheet_glfields) |
| `visiting_line_score` | string | yes | — | Visiting line scores (src: retrosheet_glfields) |
| `home_line_score` | string | yes | — | Home line scores (src: retrosheet_glfields) |
| `v_ab` | int16 | yes | — | Visiting team offensive: at-bats (src: retrosheet_glfields) |
| `v_h` | int16 | yes | — | Visiting team offensive: hits (src: retrosheet_glfields) |
| `v_2b` | int16 | yes | — | Visiting team offensive: doubles (src: retrosheet_glfields) |
| `v_3b` | int16 | yes | — | Visiting team offensive: triples (src: retrosheet_glfields) |
| `v_hr` | int16 | yes | — | Visiting team offensive: homeruns (src: retrosheet_glfields) |
| `v_rbi` | int16 | yes | — | Visiting team offensive: RBI (src: retrosheet_glfields) |
| `v_sh` | int16 | yes | — | Visiting team offensive: sacrifice hits (src: retrosheet_glfields) |
| `v_sf` | int16 | yes | — | Visiting team offensive: prior to 1954 when sacrifice flies were allowed (src: retrosheet_glfields) |
| `v_hbp` | int16 | yes | — | Visiting team offensive: sacrifice flies (since 1954) (src: retrosheet_glfields) |
| `v_bb` | int16 | yes | — | Visiting team offensive: hit-by-pitch (src: retrosheet_glfields) |
| `v_ibb` | int16 | yes | — | Visiting team offensive: walks (src: retrosheet_glfields) |
| `v_so` | int16 | yes | — | Visiting team offensive: intentional walks (src: retrosheet_glfields) |
| `v_sb` | int16 | yes | — | Visiting team offensive: strikeouts (src: retrosheet_glfields) |
| `v_cs` | int16 | yes | — | Visiting team offensive: stolen bases (src: retrosheet_glfields) |
| `v_gidp` | int16 | yes | — | Visiting team offensive: caught stealing (src: retrosheet_glfields) |
| `v_ci` | int16 | yes | — | Visiting team offensive: grounded into double plays (src: retrosheet_glfields) |
| `v_lob` | int16 | yes | — | Visiting team offensive: awarded first on catcher's interference (src: retrosheet_glfields) |
| `v_pitchers_used` | int16 | yes | — | Visiting team pitching: pitchers used ( 1 means it was a complete game ) (src: retrosheet_glfields) |
| `v_ind_er` | int16 | yes | — | Visiting team pitching: individual earned runs (src: retrosheet_glfields) |
| `v_team_er` | int16 | yes | — | Visiting team pitching: team earned runs (src: retrosheet_glfields) |
| `v_wp` | int16 | yes | — | Visiting team pitching: wild pitches (src: retrosheet_glfields) |
| `v_balks` | int16 | yes | — | Visiting team pitching: balks (src: retrosheet_glfields) |
| `v_putouts` | int16 | yes | — | Visiting team defensive: putouts (src: retrosheet_glfields) |
| `v_assists` | int16 | yes | — | Visiting team defensive: the number of innings pitched (src: retrosheet_glfields) |
| `v_errors` | int16 | yes | — | Visiting team defensive: putout was awarded when a runner was declared out for (src: retrosheet_glfields) |
| `v_passed_balls` | int16 | yes | — | Visiting team defensive: being hit by a batted ball (src: retrosheet_glfields) |
| `v_double_plays` | int16 | yes | — | Visiting team defensive: assists (src: retrosheet_glfields) |
| `v_triple_plays` | int16 | yes | — | Visiting team defensive: errors (src: retrosheet_glfields) |
| `h_ab` | int16 | yes | — | Home team offensive: at-bats (src: retrosheet_glfields) |
| `h_h` | int16 | yes | — | Home team offensive: hits (src: retrosheet_glfields) |
| `h_2b` | int16 | yes | — | Home team offensive: doubles (src: retrosheet_glfields) |
| `h_3b` | int16 | yes | — | Home team offensive: triples (src: retrosheet_glfields) |
| `h_hr` | int16 | yes | — | Home team offensive: homeruns (src: retrosheet_glfields) |
| `h_rbi` | int16 | yes | — | Home team offensive: RBI (src: retrosheet_glfields) |
| `h_sh` | int16 | yes | — | Home team offensive: sacrifice hits (src: retrosheet_glfields) |
| `h_sf` | int16 | yes | — | Home team offensive: prior to 1954 when sacrifice flies were allowed (src: retrosheet_glfields) |
| `h_hbp` | int16 | yes | — | Home team offensive: sacrifice flies (since 1954) (src: retrosheet_glfields) |
| `h_bb` | int16 | yes | — | Home team offensive: hit-by-pitch (src: retrosheet_glfields) |
| `h_ibb` | int16 | yes | — | Home team offensive: walks (src: retrosheet_glfields) |
| `h_so` | int16 | yes | — | Home team offensive: intentional walks (src: retrosheet_glfields) |
| `h_sb` | int16 | yes | — | Home team offensive: strikeouts (src: retrosheet_glfields) |
| `h_cs` | int16 | yes | — | Home team offensive: stolen bases (src: retrosheet_glfields) |
| `h_gidp` | int16 | yes | — | Home team offensive: caught stealing (src: retrosheet_glfields) |
| `h_ci` | int16 | yes | — | Home team offensive: grounded into double plays (src: retrosheet_glfields) |
| `h_lob` | int16 | yes | — | Home team offensive: awarded first on catcher's interference (src: retrosheet_glfields) |
| `h_pitchers_used` | int16 | yes | — | Home team pitching: pitchers used ( 1 means it was a complete game ) (src: retrosheet_glfields) |
| `h_ind_er` | int16 | yes | — | Home team pitching: individual earned runs (src: retrosheet_glfields) |
| `h_team_er` | int16 | yes | — | Home team pitching: team earned runs (src: retrosheet_glfields) |
| `h_wp` | int16 | yes | — | Home team pitching: wild pitches (src: retrosheet_glfields) |
| `h_balks` | int16 | yes | — | Home team pitching: balks (src: retrosheet_glfields) |
| `h_putouts` | int16 | yes | — | Home team defensive: putouts (src: retrosheet_glfields) |
| `h_assists` | int16 | yes | — | Home team defensive: the number of innings pitched (src: retrosheet_glfields) |
| `h_errors` | int16 | yes | — | Home team defensive: putout was awarded when a runner was declared out for (src: retrosheet_glfields) |
| `h_passed_balls` | int16 | yes | — | Home team defensive: being hit by a batted ball (src: retrosheet_glfields) |
| `h_double_plays` | int16 | yes | — | Home team defensive: assists (src: retrosheet_glfields) |
| `h_triple_plays` | int16 | yes | — | Home team defensive: errors (src: retrosheet_glfields) |
| `hp_ump_id` | string | yes | — | Home plate umpire ID (src: retrosheet_glfields) |
| `hp_ump_name` | string | yes | — | Home plate umpire name (src: retrosheet_glfields) |
| `1b_ump_id` | string | yes | — | 1B umpire ID (src: retrosheet_glfields) |
| `1b_ump_name` | string | yes | — | 1B umpire name (src: retrosheet_glfields) |
| `2b_ump_id` | string | yes | — | 2B umpire ID (src: retrosheet_glfields) |
| `2b_ump_name` | string | yes | — | 2B umpire name (src: retrosheet_glfields) |
| `3b_ump_id` | string | yes | — | 3B umpire ID (src: retrosheet_glfields) |
| `3b_ump_name` | string | yes | — | 3B umpire name (src: retrosheet_glfields) |
| `lf_ump_id` | string | yes | — | LF umpire ID (src: retrosheet_glfields) |
| `lf_ump_name` | string | yes | — | LF umpire name (src: retrosheet_glfields) |
| `rf_ump_id` | string | yes | — | RF umpire ID (src: retrosheet_glfields) |
| `rf_ump_name` | string | yes | — | RF umpire name (src: retrosheet_glfields) |
| `v_manager_id` | string | yes | — | Visiting team manager ID (src: retrosheet_glfields) |
| `v_manager_name` | string | yes | — | Visiting team manager name (src: retrosheet_glfields) |
| `h_manager_id` | string | yes | — | Home team manager ID (src: retrosheet_glfields) |
| `h_manager_name` | string | yes | — | Home team manager name (src: retrosheet_glfields) |
| `win_pitcher_id` | string | yes | — | Winning pitcher ID (src: retrosheet_glfields) |
| `win_pitcher_name` | string | yes | — | Winning pitcher name (src: retrosheet_glfields) |
| `lose_pitcher_id` | string | yes | — | Losing pitcher ID (src: retrosheet_glfields) |
| `lose_pitcher_name` | string | yes | — | Losing pitcher name (src: retrosheet_glfields) |
| `save_pitcher_id` | string | yes | — | Saving pitcher ID (src: retrosheet_glfields) |
| `save_pitcher_name` | string | yes | — | Saving pitcher name (src: retrosheet_glfields) |
| `gwrbi_id` | string | yes | — | Game Winning RBI batter ID (src: retrosheet_glfields) |
| `gwrbi_name` | string | yes | — | Game Winning RBI batter name (src: retrosheet_glfields) |
| `v_start_pitcher_id` | string | yes | — | Visiting starting pitcher ID (src: retrosheet_glfields) |
| `v_start_pitcher_name` | string | yes | — | Visiting starting pitcher name (src: retrosheet_glfields) |
| `h_start_pitcher_id` | string | yes | — | Home starting pitcher ID (src: retrosheet_glfields) |
| `h_start_pitcher_name` | string | yes | — | Home starting pitcher name (src: retrosheet_glfields) |
| `v_b1_id` | string | yes | — | Visiting starting players, batting order 1: ID (src: retrosheet_glfields) |
| `v_b1_name` | string | yes | — | Visiting starting players, batting order 1: name (src: retrosheet_glfields) |
| `v_b1_pos` | int8 | yes | — | Visiting starting players, batting order 1: defensive position (src: retrosheet_glfields) |
| `v_b2_id` | string | yes | — | Visiting starting players, batting order 2: ID (src: retrosheet_glfields) |
| `v_b2_name` | string | yes | — | Visiting starting players, batting order 2: name (src: retrosheet_glfields) |
| `v_b2_pos` | int8 | yes | — | Visiting starting players, batting order 2: defensive position (src: retrosheet_glfields) |
| `v_b3_id` | string | yes | — | Visiting starting players, batting order 3: ID (src: retrosheet_glfields) |
| `v_b3_name` | string | yes | — | Visiting starting players, batting order 3: name (src: retrosheet_glfields) |
| `v_b3_pos` | int8 | yes | — | Visiting starting players, batting order 3: defensive position (src: retrosheet_glfields) |
| `v_b4_id` | string | yes | — | Visiting starting players, batting order 4: ID (src: retrosheet_glfields) |
| `v_b4_name` | string | yes | — | Visiting starting players, batting order 4: name (src: retrosheet_glfields) |
| `v_b4_pos` | int8 | yes | — | Visiting starting players, batting order 4: defensive position (src: retrosheet_glfields) |
| `v_b5_id` | string | yes | — | Visiting starting players, batting order 5: ID (src: retrosheet_glfields) |
| `v_b5_name` | string | yes | — | Visiting starting players, batting order 5: name (src: retrosheet_glfields) |
| `v_b5_pos` | int8 | yes | — | Visiting starting players, batting order 5: defensive position (src: retrosheet_glfields) |
| `v_b6_id` | string | yes | — | Visiting starting players, batting order 6: ID (src: retrosheet_glfields) |
| `v_b6_name` | string | yes | — | Visiting starting players, batting order 6: name (src: retrosheet_glfields) |
| `v_b6_pos` | int8 | yes | — | Visiting starting players, batting order 6: defensive position (src: retrosheet_glfields) |
| `v_b7_id` | string | yes | — | Visiting starting players, batting order 7: ID (src: retrosheet_glfields) |
| `v_b7_name` | string | yes | — | Visiting starting players, batting order 7: name (src: retrosheet_glfields) |
| `v_b7_pos` | int8 | yes | — | Visiting starting players, batting order 7: defensive position (src: retrosheet_glfields) |
| `v_b8_id` | string | yes | — | Visiting starting players, batting order 8: ID (src: retrosheet_glfields) |
| `v_b8_name` | string | yes | — | Visiting starting players, batting order 8: name (src: retrosheet_glfields) |
| `v_b8_pos` | int8 | yes | — | Visiting starting players, batting order 8: defensive position (src: retrosheet_glfields) |
| `v_b9_id` | string | yes | — | Visiting starting players, batting order 9: ID (src: retrosheet_glfields) |
| `v_b9_name` | string | yes | — | Visiting starting players, batting order 9: name (src: retrosheet_glfields) |
| `v_b9_pos` | int8 | yes | — | Visiting starting players, batting order 9: defensive position (src: retrosheet_glfields) |
| `h_b1_id` | string | yes | — | Home starting players, batting order 1: ID (src: retrosheet_glfields) |
| `h_b1_name` | string | yes | — | Home starting players, batting order 1: name (src: retrosheet_glfields) |
| `h_b1_pos` | int8 | yes | — | Home starting players, batting order 1: defensive position (src: retrosheet_glfields) |
| `h_b2_id` | string | yes | — | Home starting players, batting order 2: ID (src: retrosheet_glfields) |
| `h_b2_name` | string | yes | — | Home starting players, batting order 2: name (src: retrosheet_glfields) |
| `h_b2_pos` | int8 | yes | — | Home starting players, batting order 2: defensive position (src: retrosheet_glfields) |
| `h_b3_id` | string | yes | — | Home starting players, batting order 3: ID (src: retrosheet_glfields) |
| `h_b3_name` | string | yes | — | Home starting players, batting order 3: name (src: retrosheet_glfields) |
| `h_b3_pos` | int8 | yes | — | Home starting players, batting order 3: defensive position (src: retrosheet_glfields) |
| `h_b4_id` | string | yes | — | Home starting players, batting order 4: ID (src: retrosheet_glfields) |
| `h_b4_name` | string | yes | — | Home starting players, batting order 4: name (src: retrosheet_glfields) |
| `h_b4_pos` | int8 | yes | — | Home starting players, batting order 4: defensive position (src: retrosheet_glfields) |
| `h_b5_id` | string | yes | — | Home starting players, batting order 5: ID (src: retrosheet_glfields) |
| `h_b5_name` | string | yes | — | Home starting players, batting order 5: name (src: retrosheet_glfields) |
| `h_b5_pos` | int8 | yes | — | Home starting players, batting order 5: defensive position (src: retrosheet_glfields) |
| `h_b6_id` | string | yes | — | Home starting players, batting order 6: ID (src: retrosheet_glfields) |
| `h_b6_name` | string | yes | — | Home starting players, batting order 6: name (src: retrosheet_glfields) |
| `h_b6_pos` | int8 | yes | — | Home starting players, batting order 6: defensive position (src: retrosheet_glfields) |
| `h_b7_id` | string | yes | — | Home starting players, batting order 7: ID (src: retrosheet_glfields) |
| `h_b7_name` | string | yes | — | Home starting players, batting order 7: name (src: retrosheet_glfields) |
| `h_b7_pos` | int8 | yes | — | Home starting players, batting order 7: defensive position (src: retrosheet_glfields) |
| `h_b8_id` | string | yes | — | Home starting players, batting order 8: ID (src: retrosheet_glfields) |
| `h_b8_name` | string | yes | — | Home starting players, batting order 8: name (src: retrosheet_glfields) |
| `h_b8_pos` | int8 | yes | — | Home starting players, batting order 8: defensive position (src: retrosheet_glfields) |
| `h_b9_id` | string | yes | — | Home starting players, batting order 9: ID (src: retrosheet_glfields) |
| `h_b9_name` | string | yes | — | Home starting players, batting order 9: name (src: retrosheet_glfields) |
| `h_b9_pos` | int8 | yes | — | Home starting players, batting order 9: defensive position (src: retrosheet_glfields) |
| `additional_info` | string | yes | — | Additional information (src: retrosheet_glfields) |
| `acquisition_info` | string | yes | — | Acquisition information (src: retrosheet_glfields) |

<!-- END GENERATED:retrosheet.gamelogs -->

<!-- BEGIN GENERATED:retrosheet.gamelogs_postseason -->
### Dataset: gamelogs_postseason

Postseason and all-star game logs.

- **View:** `retrosheet_gamelogs_postseason`
- **Processed path:** `processed/retrosheet/gamelogs_postseason/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `date`, `game_num`, `home_team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `date` | date32[day] | yes | — | Date in the form "yyyymmdd" (src: retrosheet_glfields) |
| `game_num` | int8 | yes | — | Number of game (src: retrosheet_glfields) |
| `day_of_week` | string | yes | — | Day of week (src: retrosheet_glfields) |
| `visiting_team` | string | yes | — | Visiting team (src: retrosheet_glfields) |
| `visiting_league` | string | yes | — | Visiting league (src: retrosheet_glfields) |
| `visiting_game_num` | int16 | yes | — | Visiting team game number (src: retrosheet_glfields) |
| `home_team` | string | yes | — | Home team (src: retrosheet_glfields) |
| `home_league` | string | yes | — | Home league (src: retrosheet_glfields) |
| `home_game_num` | int16 | yes | — | Home team game number (src: retrosheet_glfields) |
| `visiting_score` | int16 | yes | — | Visiting team score (src: retrosheet_glfields) |
| `home_score` | int16 | yes | — | Home team score (src: retrosheet_glfields) |
| `outs_total` | int16 | yes | — | Length of game in outs (src: retrosheet_glfields) |
| `day_night` | string | yes | — | Day/night indicator (src: retrosheet_glfields) |
| `completion` | string | yes | — | Completion information (src: retrosheet_glfields) |
| `forfeit` | string | yes | — | Forfeit information (src: retrosheet_glfields) |
| `protest` | string | yes | — | Protest information (src: retrosheet_glfields) |
| `park_id` | string | yes | — | Park ID (src: retrosheet_glfields) |
| `attendance` | int32 | yes | — | Attendance (src: retrosheet_glfields) |
| `time_of_game` | int16 | yes | — | Time of game in minutes (src: retrosheet_glfields) |
| `visiting_line_score` | string | yes | — | Visiting line scores (src: retrosheet_glfields) |
| `home_line_score` | string | yes | — | Home line scores (src: retrosheet_glfields) |
| `v_ab` | int16 | yes | — | Visiting team offensive: at-bats (src: retrosheet_glfields) |
| `v_h` | int16 | yes | — | Visiting team offensive: hits (src: retrosheet_glfields) |
| `v_2b` | int16 | yes | — | Visiting team offensive: doubles (src: retrosheet_glfields) |
| `v_3b` | int16 | yes | — | Visiting team offensive: triples (src: retrosheet_glfields) |
| `v_hr` | int16 | yes | — | Visiting team offensive: homeruns (src: retrosheet_glfields) |
| `v_rbi` | int16 | yes | — | Visiting team offensive: RBI (src: retrosheet_glfields) |
| `v_sh` | int16 | yes | — | Visiting team offensive: sacrifice hits (src: retrosheet_glfields) |
| `v_sf` | int16 | yes | — | Visiting team offensive: prior to 1954 when sacrifice flies were allowed (src: retrosheet_glfields) |
| `v_hbp` | int16 | yes | — | Visiting team offensive: sacrifice flies (since 1954) (src: retrosheet_glfields) |
| `v_bb` | int16 | yes | — | Visiting team offensive: hit-by-pitch (src: retrosheet_glfields) |
| `v_ibb` | int16 | yes | — | Visiting team offensive: walks (src: retrosheet_glfields) |
| `v_so` | int16 | yes | — | Visiting team offensive: intentional walks (src: retrosheet_glfields) |
| `v_sb` | int16 | yes | — | Visiting team offensive: strikeouts (src: retrosheet_glfields) |
| `v_cs` | int16 | yes | — | Visiting team offensive: stolen bases (src: retrosheet_glfields) |
| `v_gidp` | int16 | yes | — | Visiting team offensive: caught stealing (src: retrosheet_glfields) |
| `v_ci` | int16 | yes | — | Visiting team offensive: grounded into double plays (src: retrosheet_glfields) |
| `v_lob` | int16 | yes | — | Visiting team offensive: awarded first on catcher's interference (src: retrosheet_glfields) |
| `v_pitchers_used` | int16 | yes | — | Visiting team pitching: pitchers used ( 1 means it was a complete game ) (src: retrosheet_glfields) |
| `v_ind_er` | int16 | yes | — | Visiting team pitching: individual earned runs (src: retrosheet_glfields) |
| `v_team_er` | int16 | yes | — | Visiting team pitching: team earned runs (src: retrosheet_glfields) |
| `v_wp` | int16 | yes | — | Visiting team pitching: wild pitches (src: retrosheet_glfields) |
| `v_balks` | int16 | yes | — | Visiting team pitching: balks (src: retrosheet_glfields) |
| `v_putouts` | int16 | yes | — | Visiting team defensive: putouts (src: retrosheet_glfields) |
| `v_assists` | int16 | yes | — | Visiting team defensive: the number of innings pitched (src: retrosheet_glfields) |
| `v_errors` | int16 | yes | — | Visiting team defensive: putout was awarded when a runner was declared out for (src: retrosheet_glfields) |
| `v_passed_balls` | int16 | yes | — | Visiting team defensive: being hit by a batted ball (src: retrosheet_glfields) |
| `v_double_plays` | int16 | yes | — | Visiting team defensive: assists (src: retrosheet_glfields) |
| `v_triple_plays` | int16 | yes | — | Visiting team defensive: errors (src: retrosheet_glfields) |
| `h_ab` | int16 | yes | — | Home team offensive: at-bats (src: retrosheet_glfields) |
| `h_h` | int16 | yes | — | Home team offensive: hits (src: retrosheet_glfields) |
| `h_2b` | int16 | yes | — | Home team offensive: doubles (src: retrosheet_glfields) |
| `h_3b` | int16 | yes | — | Home team offensive: triples (src: retrosheet_glfields) |
| `h_hr` | int16 | yes | — | Home team offensive: homeruns (src: retrosheet_glfields) |
| `h_rbi` | int16 | yes | — | Home team offensive: RBI (src: retrosheet_glfields) |
| `h_sh` | int16 | yes | — | Home team offensive: sacrifice hits (src: retrosheet_glfields) |
| `h_sf` | int16 | yes | — | Home team offensive: prior to 1954 when sacrifice flies were allowed (src: retrosheet_glfields) |
| `h_hbp` | int16 | yes | — | Home team offensive: sacrifice flies (since 1954) (src: retrosheet_glfields) |
| `h_bb` | int16 | yes | — | Home team offensive: hit-by-pitch (src: retrosheet_glfields) |
| `h_ibb` | int16 | yes | — | Home team offensive: walks (src: retrosheet_glfields) |
| `h_so` | int16 | yes | — | Home team offensive: intentional walks (src: retrosheet_glfields) |
| `h_sb` | int16 | yes | — | Home team offensive: strikeouts (src: retrosheet_glfields) |
| `h_cs` | int16 | yes | — | Home team offensive: stolen bases (src: retrosheet_glfields) |
| `h_gidp` | int16 | yes | — | Home team offensive: caught stealing (src: retrosheet_glfields) |
| `h_ci` | int16 | yes | — | Home team offensive: grounded into double plays (src: retrosheet_glfields) |
| `h_lob` | int16 | yes | — | Home team offensive: awarded first on catcher's interference (src: retrosheet_glfields) |
| `h_pitchers_used` | int16 | yes | — | Home team pitching: pitchers used ( 1 means it was a complete game ) (src: retrosheet_glfields) |
| `h_ind_er` | int16 | yes | — | Home team pitching: individual earned runs (src: retrosheet_glfields) |
| `h_team_er` | int16 | yes | — | Home team pitching: team earned runs (src: retrosheet_glfields) |
| `h_wp` | int16 | yes | — | Home team pitching: wild pitches (src: retrosheet_glfields) |
| `h_balks` | int16 | yes | — | Home team pitching: balks (src: retrosheet_glfields) |
| `h_putouts` | int16 | yes | — | Home team defensive: putouts (src: retrosheet_glfields) |
| `h_assists` | int16 | yes | — | Home team defensive: the number of innings pitched (src: retrosheet_glfields) |
| `h_errors` | int16 | yes | — | Home team defensive: putout was awarded when a runner was declared out for (src: retrosheet_glfields) |
| `h_passed_balls` | int16 | yes | — | Home team defensive: being hit by a batted ball (src: retrosheet_glfields) |
| `h_double_plays` | int16 | yes | — | Home team defensive: assists (src: retrosheet_glfields) |
| `h_triple_plays` | int16 | yes | — | Home team defensive: errors (src: retrosheet_glfields) |
| `hp_ump_id` | string | yes | — | Home plate umpire ID (src: retrosheet_glfields) |
| `hp_ump_name` | string | yes | — | Home plate umpire name (src: retrosheet_glfields) |
| `1b_ump_id` | string | yes | — | 1B umpire ID (src: retrosheet_glfields) |
| `1b_ump_name` | string | yes | — | 1B umpire name (src: retrosheet_glfields) |
| `2b_ump_id` | string | yes | — | 2B umpire ID (src: retrosheet_glfields) |
| `2b_ump_name` | string | yes | — | 2B umpire name (src: retrosheet_glfields) |
| `3b_ump_id` | string | yes | — | 3B umpire ID (src: retrosheet_glfields) |
| `3b_ump_name` | string | yes | — | 3B umpire name (src: retrosheet_glfields) |
| `lf_ump_id` | string | yes | — | LF umpire ID (src: retrosheet_glfields) |
| `lf_ump_name` | string | yes | — | LF umpire name (src: retrosheet_glfields) |
| `rf_ump_id` | string | yes | — | RF umpire ID (src: retrosheet_glfields) |
| `rf_ump_name` | string | yes | — | RF umpire name (src: retrosheet_glfields) |
| `v_manager_id` | string | yes | — | Visiting team manager ID (src: retrosheet_glfields) |
| `v_manager_name` | string | yes | — | Visiting team manager name (src: retrosheet_glfields) |
| `h_manager_id` | string | yes | — | Home team manager ID (src: retrosheet_glfields) |
| `h_manager_name` | string | yes | — | Home team manager name (src: retrosheet_glfields) |
| `win_pitcher_id` | string | yes | — | Winning pitcher ID (src: retrosheet_glfields) |
| `win_pitcher_name` | string | yes | — | Winning pitcher name (src: retrosheet_glfields) |
| `lose_pitcher_id` | string | yes | — | Losing pitcher ID (src: retrosheet_glfields) |
| `lose_pitcher_name` | string | yes | — | Losing pitcher name (src: retrosheet_glfields) |
| `save_pitcher_id` | string | yes | — | Saving pitcher ID (src: retrosheet_glfields) |
| `save_pitcher_name` | string | yes | — | Saving pitcher name (src: retrosheet_glfields) |
| `gwrbi_id` | string | yes | — | Game Winning RBI batter ID (src: retrosheet_glfields) |
| `gwrbi_name` | string | yes | — | Game Winning RBI batter name (src: retrosheet_glfields) |
| `v_start_pitcher_id` | string | yes | — | Visiting starting pitcher ID (src: retrosheet_glfields) |
| `v_start_pitcher_name` | string | yes | — | Visiting starting pitcher name (src: retrosheet_glfields) |
| `h_start_pitcher_id` | string | yes | — | Home starting pitcher ID (src: retrosheet_glfields) |
| `h_start_pitcher_name` | string | yes | — | Home starting pitcher name (src: retrosheet_glfields) |
| `v_b1_id` | string | yes | — | Visiting starting players, batting order 1: ID (src: retrosheet_glfields) |
| `v_b1_name` | string | yes | — | Visiting starting players, batting order 1: name (src: retrosheet_glfields) |
| `v_b1_pos` | int8 | yes | — | Visiting starting players, batting order 1: defensive position (src: retrosheet_glfields) |
| `v_b2_id` | string | yes | — | Visiting starting players, batting order 2: ID (src: retrosheet_glfields) |
| `v_b2_name` | string | yes | — | Visiting starting players, batting order 2: name (src: retrosheet_glfields) |
| `v_b2_pos` | int8 | yes | — | Visiting starting players, batting order 2: defensive position (src: retrosheet_glfields) |
| `v_b3_id` | string | yes | — | Visiting starting players, batting order 3: ID (src: retrosheet_glfields) |
| `v_b3_name` | string | yes | — | Visiting starting players, batting order 3: name (src: retrosheet_glfields) |
| `v_b3_pos` | int8 | yes | — | Visiting starting players, batting order 3: defensive position (src: retrosheet_glfields) |
| `v_b4_id` | string | yes | — | Visiting starting players, batting order 4: ID (src: retrosheet_glfields) |
| `v_b4_name` | string | yes | — | Visiting starting players, batting order 4: name (src: retrosheet_glfields) |
| `v_b4_pos` | int8 | yes | — | Visiting starting players, batting order 4: defensive position (src: retrosheet_glfields) |
| `v_b5_id` | string | yes | — | Visiting starting players, batting order 5: ID (src: retrosheet_glfields) |
| `v_b5_name` | string | yes | — | Visiting starting players, batting order 5: name (src: retrosheet_glfields) |
| `v_b5_pos` | int8 | yes | — | Visiting starting players, batting order 5: defensive position (src: retrosheet_glfields) |
| `v_b6_id` | string | yes | — | Visiting starting players, batting order 6: ID (src: retrosheet_glfields) |
| `v_b6_name` | string | yes | — | Visiting starting players, batting order 6: name (src: retrosheet_glfields) |
| `v_b6_pos` | int8 | yes | — | Visiting starting players, batting order 6: defensive position (src: retrosheet_glfields) |
| `v_b7_id` | string | yes | — | Visiting starting players, batting order 7: ID (src: retrosheet_glfields) |
| `v_b7_name` | string | yes | — | Visiting starting players, batting order 7: name (src: retrosheet_glfields) |
| `v_b7_pos` | int8 | yes | — | Visiting starting players, batting order 7: defensive position (src: retrosheet_glfields) |
| `v_b8_id` | string | yes | — | Visiting starting players, batting order 8: ID (src: retrosheet_glfields) |
| `v_b8_name` | string | yes | — | Visiting starting players, batting order 8: name (src: retrosheet_glfields) |
| `v_b8_pos` | int8 | yes | — | Visiting starting players, batting order 8: defensive position (src: retrosheet_glfields) |
| `v_b9_id` | string | yes | — | Visiting starting players, batting order 9: ID (src: retrosheet_glfields) |
| `v_b9_name` | string | yes | — | Visiting starting players, batting order 9: name (src: retrosheet_glfields) |
| `v_b9_pos` | int8 | yes | — | Visiting starting players, batting order 9: defensive position (src: retrosheet_glfields) |
| `h_b1_id` | string | yes | — | Home starting players, batting order 1: ID (src: retrosheet_glfields) |
| `h_b1_name` | string | yes | — | Home starting players, batting order 1: name (src: retrosheet_glfields) |
| `h_b1_pos` | int8 | yes | — | Home starting players, batting order 1: defensive position (src: retrosheet_glfields) |
| `h_b2_id` | string | yes | — | Home starting players, batting order 2: ID (src: retrosheet_glfields) |
| `h_b2_name` | string | yes | — | Home starting players, batting order 2: name (src: retrosheet_glfields) |
| `h_b2_pos` | int8 | yes | — | Home starting players, batting order 2: defensive position (src: retrosheet_glfields) |
| `h_b3_id` | string | yes | — | Home starting players, batting order 3: ID (src: retrosheet_glfields) |
| `h_b3_name` | string | yes | — | Home starting players, batting order 3: name (src: retrosheet_glfields) |
| `h_b3_pos` | int8 | yes | — | Home starting players, batting order 3: defensive position (src: retrosheet_glfields) |
| `h_b4_id` | string | yes | — | Home starting players, batting order 4: ID (src: retrosheet_glfields) |
| `h_b4_name` | string | yes | — | Home starting players, batting order 4: name (src: retrosheet_glfields) |
| `h_b4_pos` | int8 | yes | — | Home starting players, batting order 4: defensive position (src: retrosheet_glfields) |
| `h_b5_id` | string | yes | — | Home starting players, batting order 5: ID (src: retrosheet_glfields) |
| `h_b5_name` | string | yes | — | Home starting players, batting order 5: name (src: retrosheet_glfields) |
| `h_b5_pos` | int8 | yes | — | Home starting players, batting order 5: defensive position (src: retrosheet_glfields) |
| `h_b6_id` | string | yes | — | Home starting players, batting order 6: ID (src: retrosheet_glfields) |
| `h_b6_name` | string | yes | — | Home starting players, batting order 6: name (src: retrosheet_glfields) |
| `h_b6_pos` | int8 | yes | — | Home starting players, batting order 6: defensive position (src: retrosheet_glfields) |
| `h_b7_id` | string | yes | — | Home starting players, batting order 7: ID (src: retrosheet_glfields) |
| `h_b7_name` | string | yes | — | Home starting players, batting order 7: name (src: retrosheet_glfields) |
| `h_b7_pos` | int8 | yes | — | Home starting players, batting order 7: defensive position (src: retrosheet_glfields) |
| `h_b8_id` | string | yes | — | Home starting players, batting order 8: ID (src: retrosheet_glfields) |
| `h_b8_name` | string | yes | — | Home starting players, batting order 8: name (src: retrosheet_glfields) |
| `h_b8_pos` | int8 | yes | — | Home starting players, batting order 8: defensive position (src: retrosheet_glfields) |
| `h_b9_id` | string | yes | — | Home starting players, batting order 9: ID (src: retrosheet_glfields) |
| `h_b9_name` | string | yes | — | Home starting players, batting order 9: name (src: retrosheet_glfields) |
| `h_b9_pos` | int8 | yes | — | Home starting players, batting order 9: defensive position (src: retrosheet_glfields) |
| `additional_info` | string | yes | — | Additional information (src: retrosheet_glfields) |
| `acquisition_info` | string | yes | — | Acquisition information (src: retrosheet_glfields) |

<!-- END GENERATED:retrosheet.gamelogs_postseason -->

<!-- BEGIN GENERATED:retrosheet.reference_ballparks -->
### Dataset: reference_ballparks

Ballparks (reference/ballparks.csv).

- **View:** `retrosheet_reference_ballparks`
- **Processed path:** `processed/retrosheet/reference_ballparks/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `park_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `park_id` | string | yes | `PARKID` | TODO |
| `name` | string | yes | `NAME` | TODO |
| `aka` | string | yes | `AKA` | TODO |
| `city` | string | yes | `CITY` | TODO |
| `state` | string | yes | `STATE` | TODO |
| `start_date` | date32[day] (`%m/%d/%Y`) | yes | `START` | TODO |
| `end_date` | date32[day] (`%m/%d/%Y`) | yes | `END` | TODO |
| `league` | string | yes | `LEAGUE` | TODO |
| `notes` | string | yes | `NOTES` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_ballparks -->

<!-- BEGIN GENERATED:retrosheet.reference_biofile -->
### Dataset: reference_biofile

Biographical file (reference/biofile.csv).

- **View:** `retrosheet_reference_biofile`
- **Processed path:** `processed/retrosheet/reference_biofile/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | string | yes | `PLAYERID` | TODO |
| `last_name` | string | yes | `LAST` | TODO |
| `first_name` | string | yes | `FIRST` | TODO |
| `nickname` | string | yes | `NICKNAME` | TODO |
| `birthdate` | string | yes | `BIRTHDATE` | TODO |
| `birth_city` | string | yes | `BIRTH.CITY` | TODO |
| `birth_state` | string | yes | `BIRTH.STATE` | TODO |
| `birth_country` | string | yes | `BIRTH.COUNTRY` | TODO |
| `play_debut` | date32[day] (`%m/%d/%Y`) | yes | `PLAY.DEBUT` | TODO |
| `play_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `PLAY.LASTGAME` | TODO |
| `mgr_debut` | date32[day] (`%m/%d/%Y`) | yes | `MGR.DEBUT` | TODO |
| `mgr_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `MGR.LASTGAME` | TODO |
| `coach_debut` | date32[day] (`%m/%d/%Y`) | yes | `COACH.DEBUT` | TODO |
| `coach_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `COACH.LASTGAME` | TODO |
| `ump_debut` | date32[day] (`%m/%d/%Y`) | yes | `UMP.DEBUT` | TODO |
| `ump_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `UMP.LASTGAME` | TODO |
| `deathdate` | string | yes | `DEATHDATE` | TODO |
| `death_city` | string | yes | `DEATH.CITY` | TODO |
| `death_state` | string | yes | `DEATH.STATE` | TODO |
| `death_country` | string | yes | `DEATH.COUNTRY` | TODO |
| `bats` | string | yes | `BATS` | TODO |
| `throws` | string | yes | `THROWS` | TODO |
| `height` | string | yes | `HEIGHT` | TODO |
| `weight` | double | yes | `WEIGHT` | TODO |
| `cemetery` | string | yes | `CEMETERY` | TODO |
| `ceme_city` | string | yes | `CEME.CITY` | TODO |
| `ceme_state` | string | yes | `CEME.STATE` | TODO |
| `ceme_country` | string | yes | `CEME.COUNTRY` | TODO |
| `ceme_note` | string | yes | `CEME.NOTE` | TODO |
| `birth_name` | string | yes | `BIRTH.NAME` | TODO |
| `name_chg` | string | yes | `NAME.CHG` | TODO |
| `bat_chg` | string | yes | `BAT.CHG` | TODO |
| `hof` | string | yes | `HOF` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_biofile -->

<!-- BEGIN GENERATED:retrosheet.reference_biofile0 -->
### Dataset: reference_biofile0

Biographical file, ISO-date edition (reference/biofile0.csv).

- **View:** `retrosheet_reference_biofile0`
- **Processed path:** `processed/retrosheet/reference_biofile0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | string | yes | `id` | TODO |
| `last_name` | string | yes | `lastname` | TODO |
| `use_name` | string | yes | `usename` | TODO |
| `full_name` | string | yes | `fullname` | TODO |
| `birthdate` | string | yes | — | TODO |
| `birthcity` | string | yes | — | TODO |
| `birthstate` | string | yes | — | TODO |
| `birthcountry` | string | yes | — | TODO |
| `deathdate` | string | yes | — | TODO |
| `deathcity` | string | yes | — | TODO |
| `deathstate` | string | yes | — | TODO |
| `deathcountry` | string | yes | — | TODO |
| `cemetery` | string | yes | — | TODO |
| `cem_city` | string | yes | — | TODO |
| `cem_state` | string | yes | — | TODO |
| `cem_ctry` | string | yes | — | TODO |
| `cem_note` | string | yes | — | TODO |
| `birth_name` | string | yes | `birthname` | TODO |
| `alt_name` | string | yes | `altname` | TODO |
| `debut_p` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_p` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `debut_c` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_c` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `debut_m` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_m` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `debut_u` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_u` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `bats` | string | yes | — | TODO |
| `throws` | string | yes | — | TODO |
| `height` | double | yes | — | TODO |
| `weight` | double | yes | — | TODO |
| `hof` | string | yes | `HOF` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_biofile0 -->

<!-- BEGIN GENERATED:retrosheet.reference_coaches -->
### Dataset: reference_coaches

Coaching staffs (reference/coaches.csv).

- **View:** `retrosheet_reference_coaches`
- **Processed path:** `processed/retrosheet/reference_coaches/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `person_id`, `year`, `team_id`, `role`, `start_date`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `person_id` | string | yes | `id` | TODO |
| `year` | int16 | yes | — | TODO |
| `team_id` | string | yes | `team` | TODO |
| `role` | string | yes | — | TODO |
| `start_date` | date32[day] (`%m/%d/%Y`) | yes | `start` | TODO |
| `end_date` | date32[day] (`%m/%d/%Y`) | yes | `end` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_coaches -->

<!-- BEGIN GENERATED:retrosheet.reference_ejections -->
### Dataset: reference_ejections

Ejections (reference/ejections.csv).

- **View:** `retrosheet_reference_ejections`
- **Processed path:** `processed/retrosheet/reference_ejections/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `game_id`, `ejectee_id`, `inning`, `reason`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | `GAMEID` | TODO |
| `ejection_date` | date32[day] (`%m/%d/%Y`) | yes | `DATE` | TODO |
| `dh` | int16 | yes | `DH` | TODO |
| `ejectee_id` | string | yes | `EJECTEE` | TODO |
| `ejectee_name` | string | yes | `EJECTEENAME` | TODO |
| `team_id` | string | yes | `TEAM` | TODO |
| `job` | string | yes | `JOB` | TODO |
| `umpire_id` | string | yes | `UMPIRE` | TODO |
| `umpire_name` | string | yes | `UMPIRENAME` | TODO |
| `inning` | int16 | yes | `INNING` | TODO |
| `reason` | string | yes | `REASON` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_ejections -->

<!-- BEGIN GENERATED:retrosheet.reference_relatives -->
### Dataset: reference_relatives

Relatives among players/managers (reference/relatives.csv).

- **View:** `retrosheet_reference_relatives`
- **Processed path:** `processed/retrosheet/reference_relatives/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `person_id_1`, `relation`, `person_id_2`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `person_id_1` | string | yes | `id1` | TODO |
| `relation` | string | yes | — | TODO |
| `person_id_2` | string | yes | `id2` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_relatives -->

<!-- BEGIN GENERATED:retrosheet.reference_teams -->
### Dataset: reference_teams

Franchise/team codes (reference/teams.csv).

- **View:** `retrosheet_reference_teams`
- **Processed path:** `processed/retrosheet/reference_teams/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `team_id`, `first_year`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | string | yes | `TEAM` | TODO |
| `league` | string | yes | `LEAGUE` | TODO |
| `city` | string | yes | `CITY` | TODO |
| `nickname` | string | yes | `NICKNAME` | TODO |
| `first_year` | int16 | yes | `FIRST` | TODO |
| `last_year` | int16 | yes | `LAST` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.reference_teams -->

<!-- BEGIN GENERATED:retrosheet.rosters -->
### Dataset: rosters

Team rosters per season.

- **View:** `retrosheet_rosters`
- **Processed path:** `processed/retrosheet/rosters/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `year`, `team`, `player_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `player_id` | string | yes | — | TODO |
| `last_name` | string | yes | — | TODO |
| `first_name` | string | yes | — | TODO |
| `bats` | string | yes | — | TODO |
| `throws` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `year` | int16 | yes | — | TODO |

<!-- END GENERATED:retrosheet.rosters -->

<!-- BEGIN GENERATED:retrosheet.schedule -->
### Dataset: schedule

Season schedules (seasons/<year>/<year>schedule.csv).

- **View:** `retrosheet_schedule`
- **Processed path:** `processed/retrosheet/schedule/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_date`, `game_number`, `visitor_team`, `visitor_game_number`, `home_team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_date` | date32[day] (`%Y%m%d`) | yes | `Date` | TODO |
| `game_number` | int16 | yes | `Num` | TODO |
| `day_of_week` | string | yes | `Day` | TODO |
| `visitor_team` | string | yes | `Visitor` | TODO |
| `visitor_league` | string | yes | `League` | TODO |
| `visitor_game_number` | int16 | yes | `Game` | TODO |
| `home_team` | string | yes | `Home` | TODO |
| `home_league` | string | yes | `League__2` | TODO |
| `home_game_number` | int16 | yes | `Game__2` | TODO |
| `day_night` | string | yes | `Day/Night` | TODO |
| `postponed` | string | yes | `Postponed` | TODO |
| `makeup_date` | string | yes | `Makeup` | TODO |
| `park_id` | string | yes | `Location` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.schedule -->

<!-- BEGIN GENERATED:retrosheet.substitutions -->
### Dataset: substitutions

In-game substitutions.

- **View:** `retrosheet_substitutions`
- **Processed path:** `processed/retrosheet/substitutions/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`, `EVENT_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — | Game ID (src: chadwick_cwsub) |
| `INN_CT` | int16 | yes | — | Inning (src: chadwick_cwsub) |
| `BAT_HOME_ID` | int16 | yes | — | Batting team (src: chadwick_cwsub) |
| `SUB_ID` | string | yes | — | Substitute (src: chadwick_cwsub) |
| `SUB_HOME_ID` | int16 | yes | — | Team (src: chadwick_cwsub) |
| `SUB_LINEUP_ID` | int16 | yes | — | Lineup position (src: chadwick_cwsub) |
| `SUB_FLD_CD` | int16 | yes | — | Fielding position (src: chadwick_cwsub) |
| `REMOVED_ID` | string | yes | — | Removed player (src: chadwick_cwsub) |
| `REMOVED_FLD_CD` | int16 | yes | — | Position of removed player (src: chadwick_cwsub) |
| `EVENT_ID` | int16 | yes | — | Event number (src: chadwick_cwsub) |
| `BALLS_CT` | int16 | yes | — | Balls (src: chadwick_cwsub) |
| `STRIKES_CT` | int16 | yes | — | Strikes (src: chadwick_cwsub) |
| `PITCH_SEQ_TX` | string | yes | — | Pitch sequence (src: chadwick_cwsub) |
| `PA_BALL_CT` | int16 | yes | — | number of balls in plate appearance (src: chadwick_cwsub) |
| `PA_CALLED_BALL_CT` | int16 | yes | — | number of called balls in plate appearance (src: chadwick_cwsub) |
| `PA_INTENT_BALL_CT` | int16 | yes | — | number of intentional balls in plate appearance (src: chadwick_cwsub) |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | number of pitchouts in plate appearance (src: chadwick_cwsub) |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | number of pitches hitting batter in plate appearance (src: chadwick_cwsub) |
| `PA_OTHER_BALL_CT` | int16 | yes | — | number of other balls in plate appearance (src: chadwick_cwsub) |
| `PA_STRIKE_CT` | int16 | yes | — | number of strikes in plate appearance (src: chadwick_cwsub) |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | number of called strikes in plate appearance (src: chadwick_cwsub) |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | number of swinging strikes in plate appearance (src: chadwick_cwsub) |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | number of foul balls in plate appearance (src: chadwick_cwsub) |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | number of balls in play in plate appearance (src: chadwick_cwsub) |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | number of other strikes in plate appearance (src: chadwick_cwsub) |
| `COUNT_TX` | string | yes | — | text of count as appears in event file (src: chadwick_cwsub) |

<!-- END GENERATED:retrosheet.substitutions -->

<!-- BEGIN GENERATED:retrosheet.umpires -->
### Dataset: umpires

Umpires working each season (seasons/<year>/UMPIRES<year>.txt).

- **View:** `retrosheet_umpires`
- **Processed path:** `processed/retrosheet/umpires/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `umpire_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `umpire_id` | string | yes | `ID` | TODO |
| `last_name` | string | yes | `last` | TODO |
| `first_name` | string | yes | `first` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.umpires -->

<!-- BEGIN GENERATED:retrosheet.schedule_original -->
### Dataset: schedule_original

Original pre-disruption schedules (seasons/<year>/<year>sched-orig.csv).

- **View:** `retrosheet_schedule_original`
- **Processed path:** `processed/retrosheet/schedule_original/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_date`, `game_number`, `visitor_team`, `visitor_game_number`, `home_team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_date` | date32[day] (`%Y%m%d`) | yes | `Date` | TODO |
| `game_number` | int16 | yes | `Num` | TODO |
| `day_of_week` | string | yes | `Day` | TODO |
| `visitor_team` | string | yes | `Visitor` | TODO |
| `visitor_league` | string | yes | `League` | TODO |
| `visitor_game_number` | int16 | yes | `Game` | TODO |
| `home_team` | string | yes | `Home` | TODO |
| `home_league` | string | yes | `League__2` | TODO |
| `home_game_number` | int16 | yes | `Game__2` | TODO |
| `day_night` | string | yes | `Day/Night` | TODO |
| `postponed` | string | yes | `Postponed` | TODO |
| `makeup_date` | string | yes | `Makeup` | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.schedule_original -->

<!-- BEGIN GENERATED:retrosheet.box_batting_lines -->
### Dataset: box_batting_lines

Batting and base-running lines of the box-score accounts (stat,bline).

- **View:** `retrosheet_box_batting_lines`
- **Processed path:** `processed/retrosheet/box_batting_lines/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `player_id`, `side`, `seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `player_id` | string | yes | — | TODO |
| `side` | int8 | yes | — | TODO |
| `position` | int8 | yes | — | TODO |
| `seq` | int8 | yes | — | TODO |
| `ab` | int16 | yes | — | TODO |
| `r` | int16 | yes | — | TODO |
| `h` | int16 | yes | — | TODO |
| `double` | int16 | yes | — | TODO |
| `triple` | int16 | yes | — | TODO |
| `hr` | int16 | yes | — | TODO |
| `rbi` | int16 | yes | — | TODO |
| `sh` | int16 | yes | — | TODO |
| `sf` | int16 | yes | — | TODO |
| `hbp` | int16 | yes | — | TODO |
| `bb` | int16 | yes | — | TODO |
| `ibb` | int16 | yes | — | TODO |
| `k` | int16 | yes | — | TODO |
| `sb` | int16 | yes | — | TODO |
| `cs` | int16 | yes | — | TODO |
| `gidp` | int16 | yes | — | TODO |
| `interference` | int16 | yes | — | TODO |

<!-- END GENERATED:retrosheet.box_batting_lines -->

<!-- BEGIN GENERATED:retrosheet.box_games -->
### Dataset: box_games

Games of the box-score accounts (id, version, info lines).

- **View:** `retrosheet_box_games`
- **Processed path:** `processed/retrosheet/box_games/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `version` | int16 | yes | — | TODO |
| `visteam` | string | yes | — | TODO |
| `hometeam` | string | yes | — | TODO |
| `date` | date32[day] (`%Y/%m/%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `starttime` | string | yes | — | TODO |
| `daynight` | string | yes | — | TODO |
| `usedh` | bool | yes | — | TODO |
| `umphome` | string | yes | — | TODO |
| `ump1b` | string | yes | — | TODO |
| `ump2b` | string | yes | — | TODO |
| `ump3b` | string | yes | — | TODO |
| `umplf` | string | yes | — | TODO |
| `umprf` | string | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `attendance` | int32 | yes | — | TODO |
| `temp` | int16 | yes | — | TODO |
| `winddir` | string | yes | — | TODO |
| `windspeed` | int16 | yes | — | TODO |
| `fieldcond` | string | yes | — | TODO |
| `precip` | string | yes | — | TODO |
| `sky` | string | yes | — | TODO |
| `timeofgame` | int16 | yes | — | TODO |
| `innings` | int16 | yes | — | TODO |
| `tiebreaker` | string | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `wp` | string | yes | — | TODO |
| `lp` | string | yes | — | TODO |
| `save` | string | yes | — | TODO |
| `gwrbi` | string | yes | — | TODO |
| `oscorer` | string | yes | — | TODO |
| `source_file` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.box_games -->

<!-- BEGIN GENERATED:retrosheet.box_records -->
### Dataset: box_records

Every other box-account record (pinch hitters/runners, fielding, pitching, team totals, line scores, events, comments, unknown kinds) as parsed fields plus the raw line.

- **View:** `retrosheet_box_records`
- **Processed path:** `processed/retrosheet/box_records/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `line_no`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `line_no` | int32 | yes | — | TODO |
| `kind` | string | yes | — | TODO |
| `fields` | list<item: string> | yes | — | TODO |
| `raw` | string | yes | — | TODO |

<!-- END GENERATED:retrosheet.box_records -->

<!-- BEGIN GENERATED:retrosheet.box_starters -->
### Dataset: box_starters

Starting lineups of the box-score accounts (start lines).

- **View:** `retrosheet_box_starters`
- **Processed path:** `processed/retrosheet/box_starters/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `player_id`, `side`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `player_id` | string | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `side` | int8 | yes | — | TODO |
| `batting_order` | int8 | yes | — | TODO |
| `position` | int8 | yes | — | TODO |

<!-- END GENERATED:retrosheet.box_starters -->
