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
| `<year>.EBA`, `.EBN`, `.EBE`, `.EBR`, `.EBF` (box-score game accounts) | `box_files/` | **raw only** — see below |
| `<TEAM><year>.ROS` | `rosters/` | `rosters` |
| `GL<year>.TXT` | `gamelogs/` | `gamelogs` |
| `<year>schedule.csv` (`2026SCHEDULE.CSV`) | `schedule/` | `schedule` |
| `<year>sched-orig.csv` (e.g. 2020: the original pre-COVID schedule) | `schedule_original/` | `schedule_original` |
| `UMPIRES<year>.txt` | `umpires/` | `umpires` |
| `<year>aldiscs.csv`, `nldiscs.csv`, `fldiscs.csv` | `discrepancies/` | `discrepancies` |
| `gamelog/GL{WC,DV,LC,WS,AS}.TXT` | `gamelogs_postseason/` | `gamelogs_postseason` |
| `reference/<name>.csv` | `reference_<name>/` | `reference_<name>` |

**Box-score game accounts (`.EB*`) are stored raw only.** They use Retrosheet's box-score record format (`stat,bline`, `stat,pline`, `stat,dline`, `line`, `event` records) rather than play-by-play, so the event parser yields no rows for them. The meaning of every field is specified on retrosheet.org (not reachable for automated fetches), so baseballpy does not guess a column mapping; `boxscores_batting` and `boxscores_pitching` are instead *derived* from the play-by-play files, which cover every game that has play-by-play. Parsing the box accounts is a documented follow-up.

## Datasets Covered

### 1. Play-by-Play Event Data (`.EVA`, `.EVN`, `.EVE`, `.EB*`)
- **Coverage:** every season with play-by-play files in the tree (1912–present for most; complete modern coverage). `events` holds regular-season games, `events_postseason` postseason/all-star/special games, `events_deduced` games deduced from box scores. They are separate datasets so a game never appears twice in a view.
- **Format:** Retrosheet DiamondWare event records parsed by `chadwickpy.tools.events.event_rows` into 97 canonical fields (see the generated dictionaries).
- **Partitioning:** `season=YYYY`; one atomic Parquet part per season written as one row group per source file.
- **Parsing:** CPU-bound and offline; files are parsed one at a time (optionally in a bounded process pool, `LakeConfig.parse_workers`) and streamed into the Parquet writer — no whole-season Python lists.
- **Key:** `GAME_ID` (event order is file order; there is no unique event key upstream).

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

<!-- BEGIN GENERATED:retrosheet.boxscores_batting -->
### Dataset: boxscores_batting

Batting box score lines.

- **View:** `retrosheet_boxscores_batting`
- **Processed path:** `processed/retrosheet/boxscores_batting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `team_id`, `player_id`, `slot`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — |  |
| `team_id` | string | yes | — |  |
| `player_id` | string | yes | — |  |
| `player_name` | string | yes | — |  |
| `slot` | int8 | yes | — |  |
| `pos` | int8 | yes | — |  |
| `ab` | int16 | yes | — |  |
| `r` | int16 | yes | — |  |
| `h` | int16 | yes | — |  |
| `d` | int16 | yes | — |  |
| `t` | int16 | yes | — |  |
| `hr` | int16 | yes | — |  |
| `rbi` | int16 | yes | — |  |
| `bb` | int16 | yes | — |  |
| `ibb` | int16 | yes | — |  |
| `so` | int16 | yes | — |  |
| `hbp` | int16 | yes | — |  |
| `sh` | int16 | yes | — |  |
| `sf` | int16 | yes | — |  |
| `sb` | int16 | yes | — |  |
| `cs` | int16 | yes | — |  |
| `gidp` | int16 | yes | — |  |
| `pa` | int16 | yes | — |  |

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
| `game_id` | string | yes | — |  |
| `team_id` | string | yes | — |  |
| `pitcher_id` | string | yes | — |  |
| `pitcher_name` | string | yes | — |  |
| `starter_fl` | bool | yes | — |  |
| `seq` | int8 | yes | — |  |
| `outs_recorded` | int16 | yes | — |  |
| `bf` | int16 | yes | — |  |
| `h` | int16 | yes | — |  |
| `r` | int16 | yes | — |  |
| `er` | int16 | yes | — |  |
| `bb` | int16 | yes | — |  |
| `ibb` | int16 | yes | — |  |
| `so` | int16 | yes | — |  |
| `hr` | int16 | yes | — |  |
| `hbp` | int16 | yes | — |  |
| `wp` | int16 | yes | — |  |
| `bk` | int16 | yes | — |  |
| `pitches` | int16 | yes | — |  |
| `strikes` | int16 | yes | — |  |
| `w` | bool | yes | — |  |
| `l` | bool | yes | — |  |
| `sv` | bool | yes | — |  |
| `cg` | bool | yes | — |  |
| `sho` | bool | yes | — |  |
| `gf` | bool | yes | — |  |

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
| `GAME_ID` | string | yes | — |  |
| `GAME_DT` | string | yes | — |  |
| `GAME_CT` | int16 | yes | — |  |
| `APPEAR_DT` | string | yes | — |  |
| `TEAM_ID` | string | yes | — |  |
| `PLAYER_ID` | string | yes | — |  |
| `SLOT_CT` | int16 | yes | — |  |
| `SEQ_CT` | int16 | yes | — |  |
| `HOME_FL` | int8 | yes | — |  |
| `OPPONENT_ID` | string | yes | — |  |
| `PARK_ID` | string | yes | — |  |
| `B_G` | int16 | yes | — |  |
| `B_PA` | int16 | yes | — |  |
| `B_AB` | int16 | yes | — |  |
| `B_R` | int16 | yes | — |  |
| `B_H` | int16 | yes | — |  |
| `B_TB` | int16 | yes | — |  |
| `B_2B` | int16 | yes | — |  |
| `B_3B` | int16 | yes | — |  |
| `B_HR` | int16 | yes | — |  |
| `B_HR4` | int16 | yes | — |  |
| `B_RBI` | int16 | yes | — |  |
| `B_GW` | int16 | yes | — |  |
| `B_BB` | int16 | yes | — |  |
| `B_IBB` | int16 | yes | — |  |
| `B_SO` | int16 | yes | — |  |
| `B_GDP` | int16 | yes | — |  |
| `B_HP` | int16 | yes | — |  |
| `B_SH` | int16 | yes | — |  |
| `B_SF` | int16 | yes | — |  |
| `B_SB` | int16 | yes | — |  |
| `B_CS` | int16 | yes | — |  |
| `B_XI` | int16 | yes | — |  |
| `B_G_DH` | int8 | yes | — |  |
| `B_G_PH` | int8 | yes | — |  |
| `B_G_PR` | int8 | yes | — |  |
| `P_G` | int16 | yes | — |  |
| `P_GS` | int16 | yes | — |  |
| `P_CG` | int16 | yes | — |  |
| `P_SHO` | int16 | yes | — |  |
| `P_GF` | int16 | yes | — |  |
| `P_W` | int16 | yes | — |  |
| `P_L` | int16 | yes | — |  |
| `P_SV` | int16 | yes | — |  |
| `P_OUT` | int16 | yes | — |  |
| `P_TBF` | int16 | yes | — |  |
| `P_AB` | int16 | yes | — |  |
| `P_R` | int16 | yes | — |  |
| `P_ER` | int16 | yes | — |  |
| `P_H` | int16 | yes | — |  |
| `P_TB` | int16 | yes | — |  |
| `P_2B` | int16 | yes | — |  |
| `P_3B` | int16 | yes | — |  |
| `P_HR` | int16 | yes | — |  |
| `P_HR4` | int16 | yes | — |  |
| `P_BB` | int16 | yes | — |  |
| `P_IBB` | int16 | yes | — |  |
| `P_SO` | int16 | yes | — |  |
| `P_GDP` | int16 | yes | — |  |
| `P_HP` | int16 | yes | — |  |
| `P_SH` | int16 | yes | — |  |
| `P_SF` | int16 | yes | — |  |
| `P_XI` | int16 | yes | — |  |
| `P_WP` | int16 | yes | — |  |
| `P_BK` | int16 | yes | — |  |
| `P_IR` | int16 | yes | — |  |
| `P_IRS` | int16 | yes | — |  |
| `P_GO` | int16 | yes | — |  |
| `P_AO` | int16 | yes | — |  |
| `P_PITCH` | int16 | yes | — |  |
| `P_STRIKE` | int16 | yes | — |  |
| `F_P_G` | int16 | yes | — |  |
| `F_P_GS` | int16 | yes | — |  |
| `F_P_OUT` | int16 | yes | — |  |
| `F_P_TC` | int16 | yes | — |  |
| `F_P_PO` | int16 | yes | — |  |
| `F_P_A` | int16 | yes | — |  |
| `F_P_E` | int16 | yes | — |  |
| `F_P_DP` | int16 | yes | — |  |
| `F_P_TP` | int16 | yes | — |  |
| `F_C_G` | int16 | yes | — |  |
| `F_C_GS` | int16 | yes | — |  |
| `F_C_OUT` | int16 | yes | — |  |
| `F_C_TC` | int16 | yes | — |  |
| `F_C_PO` | int16 | yes | — |  |
| `F_C_A` | int16 | yes | — |  |
| `F_C_E` | int16 | yes | — |  |
| `F_C_DP` | int16 | yes | — |  |
| `F_C_TP` | int16 | yes | — |  |
| `F_C_PB` | int16 | yes | — |  |
| `F_C_XI` | int16 | yes | — |  |
| `F_1B_G` | int16 | yes | — |  |
| `F_1B_GS` | int16 | yes | — |  |
| `F_1B_OUT` | int16 | yes | — |  |
| `F_1B_TC` | int16 | yes | — |  |
| `F_1B_PO` | int16 | yes | — |  |
| `F_1B_A` | int16 | yes | — |  |
| `F_1B_E` | int16 | yes | — |  |
| `F_1B_DP` | int16 | yes | — |  |
| `F_1B_TP` | int16 | yes | — |  |
| `F_2B_G` | int16 | yes | — |  |
| `F_2B_GS` | int16 | yes | — |  |
| `F_2B_OUT` | int16 | yes | — |  |
| `F_2B_TC` | int16 | yes | — |  |
| `F_2B_PO` | int16 | yes | — |  |
| `F_2B_A` | int16 | yes | — |  |
| `F_2B_E` | int16 | yes | — |  |
| `F_2B_DP` | int16 | yes | — |  |
| `F_2B_TP` | int16 | yes | — |  |
| `F_3B_G` | int16 | yes | — |  |
| `F_3B_GS` | int16 | yes | — |  |
| `F_3B_OUT` | int16 | yes | — |  |
| `F_3B_TC` | int16 | yes | — |  |
| `F_3B_PO` | int16 | yes | — |  |
| `F_3B_A` | int16 | yes | — |  |
| `F_3B_E` | int16 | yes | — |  |
| `F_3B_DP` | int16 | yes | — |  |
| `F_3B_TP` | int16 | yes | — |  |
| `F_SS_G` | int16 | yes | — |  |
| `F_SS_GS` | int16 | yes | — |  |
| `F_SS_OUT` | int16 | yes | — |  |
| `F_SS_TC` | int16 | yes | — |  |
| `F_SS_PO` | int16 | yes | — |  |
| `F_SS_A` | int16 | yes | — |  |
| `F_SS_E` | int16 | yes | — |  |
| `F_SS_DP` | int16 | yes | — |  |
| `F_SS_TP` | int16 | yes | — |  |
| `F_LF_G` | int16 | yes | — |  |
| `F_LF_GS` | int16 | yes | — |  |
| `F_LF_OUT` | int16 | yes | — |  |
| `F_LF_TC` | int16 | yes | — |  |
| `F_LF_PO` | int16 | yes | — |  |
| `F_LF_A` | int16 | yes | — |  |
| `F_LF_E` | int16 | yes | — |  |
| `F_LF_DP` | int16 | yes | — |  |
| `F_LF_TP` | int16 | yes | — |  |
| `F_CF_G` | int16 | yes | — |  |
| `F_CF_GS` | int16 | yes | — |  |
| `F_CF_OUT` | int16 | yes | — |  |
| `F_CF_TC` | int16 | yes | — |  |
| `F_CF_PO` | int16 | yes | — |  |
| `F_CF_A` | int16 | yes | — |  |
| `F_CF_E` | int16 | yes | — |  |
| `F_CF_DP` | int16 | yes | — |  |
| `F_CF_TP` | int16 | yes | — |  |
| `F_RF_G` | int16 | yes | — |  |
| `F_RF_GS` | int16 | yes | — |  |
| `F_RF_OUT` | int16 | yes | — |  |
| `F_RF_TC` | int16 | yes | — |  |
| `F_RF_PO` | int16 | yes | — |  |
| `F_RF_A` | int16 | yes | — |  |
| `F_RF_E` | int16 | yes | — |  |
| `F_RF_DP` | int16 | yes | — |  |
| `F_RF_TP` | int16 | yes | — |  |

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
| `disc_id` | string | yes | `ID` |  |
| `player_id` | string | yes | `Player` |  |
| `year` | int16 | yes | `Year` |  |
| `team_id` | string | yes | `Team` |  |
| `type` | string | yes | `Type` |  |
| `position` | string | yes | `Pos` |  |
| `category` | string | yes | `Cat` |  |
| `game_id` | string | yes | `Game` |  |
| `retro_value` | double | yes | `Retro` |  |
| `official_value` | double | yes | `Official` |  |
| `cross_id` | string | yes | `Cross` |  |
| `code` | string | yes | `Code` |  |
| `flag` | string | yes | `X|col_13` |  |
| `notes` | string | yes | `Notes` |  |
| `accepted` | string | yes | `Accepted` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:retrosheet.discrepancies -->

<!-- BEGIN GENERATED:retrosheet.events -->
### Dataset: events

Regular-season play-by-play events.

- **View:** `retrosheet_events`
- **Processed path:** `processed/retrosheet/events/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — |  |
| `AWAY_TEAM_ID` | string | yes | — |  |
| `INN_CT` | int16 | yes | — |  |
| `BAT_HOME_ID` | int8 | yes | — |  |
| `OUTS_CT` | int8 | yes | — |  |
| `BALLS_CT` | int8 | yes | — |  |
| `STRIKES_CT` | int8 | yes | — |  |
| `PITCH_SEQ_TX` | string | yes | — |  |
| `AWAY_SCORE_CT` | int16 | yes | — |  |
| `HOME_SCORE_CT` | int16 | yes | — |  |
| `BAT_ID` | string | yes | — |  |
| `BAT_HAND_CD` | string | yes | — |  |
| `RESP_BAT_ID` | string | yes | — |  |
| `RESP_BAT_HAND_CD` | string | yes | — |  |
| `PIT_ID` | string | yes | — |  |
| `PIT_HAND_CD` | string | yes | — |  |
| `RESP_PIT_ID` | string | yes | — |  |
| `RESP_PIT_HAND_CD` | string | yes | — |  |
| `POS2_FLD_ID` | string | yes | — |  |
| `POS3_FLD_ID` | string | yes | — |  |
| `POS4_FLD_ID` | string | yes | — |  |
| `POS5_FLD_ID` | string | yes | — |  |
| `POS6_FLD_ID` | string | yes | — |  |
| `POS7_FLD_ID` | string | yes | — |  |
| `POS8_FLD_ID` | string | yes | — |  |
| `POS9_FLD_ID` | string | yes | — |  |
| `BASE1_RUN_ID` | string | yes | — |  |
| `BASE2_RUN_ID` | string | yes | — |  |
| `BASE3_RUN_ID` | string | yes | — |  |
| `EVENT_TX` | string | yes | — |  |
| `LEADOFF_FL` | bool | yes | — |  |
| `PH_FL` | bool | yes | — |  |
| `BAT_FLD_CD` | int8 | yes | — |  |
| `BAT_LINEUP_ID` | int8 | yes | — |  |
| `EVENT_CD` | int16 | yes | — |  |
| `BAT_EVENT_FL` | bool | yes | — |  |
| `AB_FL` | bool | yes | — |  |
| `H_CD` | int8 | yes | — |  |
| `SH_FL` | bool | yes | — |  |
| `SF_FL` | bool | yes | — |  |
| `EVENT_OUTS_CT` | int8 | yes | — |  |
| `DP_FL` | bool | yes | — |  |
| `TP_FL` | bool | yes | — |  |
| `RBI_CT` | int8 | yes | — |  |
| `WP_FL` | bool | yes | — |  |
| `PB_FL` | bool | yes | — |  |
| `FLD_CD` | int8 | yes | — |  |
| `BATTEDBALL_CD` | string | yes | — |  |
| `BUNT_FL` | bool | yes | — |  |
| `FOUL_FL` | bool | yes | — |  |
| `BATTEDBALL_LOC_TX` | string | yes | — |  |
| `ERR_CT` | int8 | yes | — |  |
| `ERR1_FLD_CD` | int8 | yes | — |  |
| `ERR1_CD` | string | yes | — |  |
| `ERR2_FLD_CD` | int8 | yes | — |  |
| `ERR2_CD` | string | yes | — |  |
| `ERR3_FLD_CD` | int8 | yes | — |  |
| `ERR3_CD` | string | yes | — |  |
| `BAT_DEST_ID` | int8 | yes | — |  |
| `RUN1_DEST_ID` | int8 | yes | — |  |
| `RUN2_DEST_ID` | int8 | yes | — |  |
| `RUN3_DEST_ID` | int8 | yes | — |  |
| `BAT_PLAY_TX` | string | yes | — |  |
| `RUN1_PLAY_TX` | string | yes | — |  |
| `RUN2_PLAY_TX` | string | yes | — |  |
| `RUN3_PLAY_TX` | string | yes | — |  |
| `RUN1_SB_FL` | bool | yes | — |  |
| `RUN2_SB_FL` | bool | yes | — |  |
| `RUN3_SB_FL` | bool | yes | — |  |
| `RUN1_CS_FL` | bool | yes | — |  |
| `RUN2_CS_FL` | bool | yes | — |  |
| `RUN3_CS_FL` | bool | yes | — |  |
| `RUN1_PK_FL` | bool | yes | — |  |
| `RUN2_PK_FL` | bool | yes | — |  |
| `RUN3_PK_FL` | bool | yes | — |  |
| `RUN1_RESP_PIT_ID` | string | yes | — |  |
| `RUN2_RESP_PIT_ID` | string | yes | — |  |
| `RUN3_RESP_PIT_ID` | string | yes | — |  |
| `GAME_NEW_FL` | bool | yes | — |  |
| `GAME_END_FL` | bool | yes | — |  |
| `PR_RUN1_FL` | bool | yes | — |  |
| `PR_RUN2_FL` | bool | yes | — |  |
| `PR_RUN3_FL` | bool | yes | — |  |
| `REMOVED_FOR_PR_RUN1_ID` | string | yes | — |  |
| `REMOVED_FOR_PR_RUN2_ID` | string | yes | — |  |
| `REMOVED_FOR_PR_RUN3_ID` | string | yes | — |  |
| `REMOVED_FOR_PH_BAT_ID` | string | yes | — |  |
| `REMOVED_FOR_PH_BAT_FLD_CD` | int8 | yes | — |  |
| `PO1_FLD_CD` | int8 | yes | — |  |
| `PO2_FLD_CD` | int8 | yes | — |  |
| `PO3_FLD_CD` | int8 | yes | — |  |
| `ASS1_FLD_CD` | int8 | yes | — |  |
| `ASS2_FLD_CD` | int8 | yes | — |  |
| `ASS3_FLD_CD` | int8 | yes | — |  |
| `ERR1_FLD_CD_NEW` | int8 | yes | — |  |
| `ERR2_FLD_CD_NEW` | int8 | yes | — |  |
| `ERR3_FLD_CD_NEW` | int8 | yes | — |  |
| `BAT_LAST_ID` | int8 | yes | — |  |

<!-- END GENERATED:retrosheet.events -->

<!-- BEGIN GENERATED:retrosheet.events_deduced -->
### Dataset: events_deduced

Play-by-play events deduced from box scores (.ED* files).

- **View:** `retrosheet_events_deduced`
- **Processed path:** `processed/retrosheet/events_deduced/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — |  |
| `AWAY_TEAM_ID` | string | yes | — |  |
| `INN_CT` | int16 | yes | — |  |
| `BAT_HOME_ID` | int8 | yes | — |  |
| `OUTS_CT` | int8 | yes | — |  |
| `BALLS_CT` | int8 | yes | — |  |
| `STRIKES_CT` | int8 | yes | — |  |
| `PITCH_SEQ_TX` | string | yes | — |  |
| `AWAY_SCORE_CT` | int16 | yes | — |  |
| `HOME_SCORE_CT` | int16 | yes | — |  |
| `BAT_ID` | string | yes | — |  |
| `BAT_HAND_CD` | string | yes | — |  |
| `RESP_BAT_ID` | string | yes | — |  |
| `RESP_BAT_HAND_CD` | string | yes | — |  |
| `PIT_ID` | string | yes | — |  |
| `PIT_HAND_CD` | string | yes | — |  |
| `RESP_PIT_ID` | string | yes | — |  |
| `RESP_PIT_HAND_CD` | string | yes | — |  |
| `POS2_FLD_ID` | string | yes | — |  |
| `POS3_FLD_ID` | string | yes | — |  |
| `POS4_FLD_ID` | string | yes | — |  |
| `POS5_FLD_ID` | string | yes | — |  |
| `POS6_FLD_ID` | string | yes | — |  |
| `POS7_FLD_ID` | string | yes | — |  |
| `POS8_FLD_ID` | string | yes | — |  |
| `POS9_FLD_ID` | string | yes | — |  |
| `BASE1_RUN_ID` | string | yes | — |  |
| `BASE2_RUN_ID` | string | yes | — |  |
| `BASE3_RUN_ID` | string | yes | — |  |
| `EVENT_TX` | string | yes | — |  |
| `LEADOFF_FL` | bool | yes | — |  |
| `PH_FL` | bool | yes | — |  |
| `BAT_FLD_CD` | int8 | yes | — |  |
| `BAT_LINEUP_ID` | int8 | yes | — |  |
| `EVENT_CD` | int16 | yes | — |  |
| `BAT_EVENT_FL` | bool | yes | — |  |
| `AB_FL` | bool | yes | — |  |
| `H_CD` | int8 | yes | — |  |
| `SH_FL` | bool | yes | — |  |
| `SF_FL` | bool | yes | — |  |
| `EVENT_OUTS_CT` | int8 | yes | — |  |
| `DP_FL` | bool | yes | — |  |
| `TP_FL` | bool | yes | — |  |
| `RBI_CT` | int8 | yes | — |  |
| `WP_FL` | bool | yes | — |  |
| `PB_FL` | bool | yes | — |  |
| `FLD_CD` | int8 | yes | — |  |
| `BATTEDBALL_CD` | string | yes | — |  |
| `BUNT_FL` | bool | yes | — |  |
| `FOUL_FL` | bool | yes | — |  |
| `BATTEDBALL_LOC_TX` | string | yes | — |  |
| `ERR_CT` | int8 | yes | — |  |
| `ERR1_FLD_CD` | int8 | yes | — |  |
| `ERR1_CD` | string | yes | — |  |
| `ERR2_FLD_CD` | int8 | yes | — |  |
| `ERR2_CD` | string | yes | — |  |
| `ERR3_FLD_CD` | int8 | yes | — |  |
| `ERR3_CD` | string | yes | — |  |
| `BAT_DEST_ID` | int8 | yes | — |  |
| `RUN1_DEST_ID` | int8 | yes | — |  |
| `RUN2_DEST_ID` | int8 | yes | — |  |
| `RUN3_DEST_ID` | int8 | yes | — |  |
| `BAT_PLAY_TX` | string | yes | — |  |
| `RUN1_PLAY_TX` | string | yes | — |  |
| `RUN2_PLAY_TX` | string | yes | — |  |
| `RUN3_PLAY_TX` | string | yes | — |  |
| `RUN1_SB_FL` | bool | yes | — |  |
| `RUN2_SB_FL` | bool | yes | — |  |
| `RUN3_SB_FL` | bool | yes | — |  |
| `RUN1_CS_FL` | bool | yes | — |  |
| `RUN2_CS_FL` | bool | yes | — |  |
| `RUN3_CS_FL` | bool | yes | — |  |
| `RUN1_PK_FL` | bool | yes | — |  |
| `RUN2_PK_FL` | bool | yes | — |  |
| `RUN3_PK_FL` | bool | yes | — |  |
| `RUN1_RESP_PIT_ID` | string | yes | — |  |
| `RUN2_RESP_PIT_ID` | string | yes | — |  |
| `RUN3_RESP_PIT_ID` | string | yes | — |  |
| `GAME_NEW_FL` | bool | yes | — |  |
| `GAME_END_FL` | bool | yes | — |  |
| `PR_RUN1_FL` | bool | yes | — |  |
| `PR_RUN2_FL` | bool | yes | — |  |
| `PR_RUN3_FL` | bool | yes | — |  |
| `REMOVED_FOR_PR_RUN1_ID` | string | yes | — |  |
| `REMOVED_FOR_PR_RUN2_ID` | string | yes | — |  |
| `REMOVED_FOR_PR_RUN3_ID` | string | yes | — |  |
| `REMOVED_FOR_PH_BAT_ID` | string | yes | — |  |
| `REMOVED_FOR_PH_BAT_FLD_CD` | int8 | yes | — |  |
| `PO1_FLD_CD` | int8 | yes | — |  |
| `PO2_FLD_CD` | int8 | yes | — |  |
| `PO3_FLD_CD` | int8 | yes | — |  |
| `ASS1_FLD_CD` | int8 | yes | — |  |
| `ASS2_FLD_CD` | int8 | yes | — |  |
| `ASS3_FLD_CD` | int8 | yes | — |  |
| `ERR1_FLD_CD_NEW` | int8 | yes | — |  |
| `ERR2_FLD_CD_NEW` | int8 | yes | — |  |
| `ERR3_FLD_CD_NEW` | int8 | yes | — |  |
| `BAT_LAST_ID` | int8 | yes | — |  |

<!-- END GENERATED:retrosheet.events_deduced -->

<!-- BEGIN GENERATED:retrosheet.events_postseason -->
### Dataset: events_postseason

Postseason and all-star play-by-play events.

- **View:** `retrosheet_events_postseason`
- **Processed path:** `processed/retrosheet/events_postseason/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `GAME_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — |  |
| `AWAY_TEAM_ID` | string | yes | — |  |
| `INN_CT` | int16 | yes | — |  |
| `BAT_HOME_ID` | int8 | yes | — |  |
| `OUTS_CT` | int8 | yes | — |  |
| `BALLS_CT` | int8 | yes | — |  |
| `STRIKES_CT` | int8 | yes | — |  |
| `PITCH_SEQ_TX` | string | yes | — |  |
| `AWAY_SCORE_CT` | int16 | yes | — |  |
| `HOME_SCORE_CT` | int16 | yes | — |  |
| `BAT_ID` | string | yes | — |  |
| `BAT_HAND_CD` | string | yes | — |  |
| `RESP_BAT_ID` | string | yes | — |  |
| `RESP_BAT_HAND_CD` | string | yes | — |  |
| `PIT_ID` | string | yes | — |  |
| `PIT_HAND_CD` | string | yes | — |  |
| `RESP_PIT_ID` | string | yes | — |  |
| `RESP_PIT_HAND_CD` | string | yes | — |  |
| `POS2_FLD_ID` | string | yes | — |  |
| `POS3_FLD_ID` | string | yes | — |  |
| `POS4_FLD_ID` | string | yes | — |  |
| `POS5_FLD_ID` | string | yes | — |  |
| `POS6_FLD_ID` | string | yes | — |  |
| `POS7_FLD_ID` | string | yes | — |  |
| `POS8_FLD_ID` | string | yes | — |  |
| `POS9_FLD_ID` | string | yes | — |  |
| `BASE1_RUN_ID` | string | yes | — |  |
| `BASE2_RUN_ID` | string | yes | — |  |
| `BASE3_RUN_ID` | string | yes | — |  |
| `EVENT_TX` | string | yes | — |  |
| `LEADOFF_FL` | bool | yes | — |  |
| `PH_FL` | bool | yes | — |  |
| `BAT_FLD_CD` | int8 | yes | — |  |
| `BAT_LINEUP_ID` | int8 | yes | — |  |
| `EVENT_CD` | int16 | yes | — |  |
| `BAT_EVENT_FL` | bool | yes | — |  |
| `AB_FL` | bool | yes | — |  |
| `H_CD` | int8 | yes | — |  |
| `SH_FL` | bool | yes | — |  |
| `SF_FL` | bool | yes | — |  |
| `EVENT_OUTS_CT` | int8 | yes | — |  |
| `DP_FL` | bool | yes | — |  |
| `TP_FL` | bool | yes | — |  |
| `RBI_CT` | int8 | yes | — |  |
| `WP_FL` | bool | yes | — |  |
| `PB_FL` | bool | yes | — |  |
| `FLD_CD` | int8 | yes | — |  |
| `BATTEDBALL_CD` | string | yes | — |  |
| `BUNT_FL` | bool | yes | — |  |
| `FOUL_FL` | bool | yes | — |  |
| `BATTEDBALL_LOC_TX` | string | yes | — |  |
| `ERR_CT` | int8 | yes | — |  |
| `ERR1_FLD_CD` | int8 | yes | — |  |
| `ERR1_CD` | string | yes | — |  |
| `ERR2_FLD_CD` | int8 | yes | — |  |
| `ERR2_CD` | string | yes | — |  |
| `ERR3_FLD_CD` | int8 | yes | — |  |
| `ERR3_CD` | string | yes | — |  |
| `BAT_DEST_ID` | int8 | yes | — |  |
| `RUN1_DEST_ID` | int8 | yes | — |  |
| `RUN2_DEST_ID` | int8 | yes | — |  |
| `RUN3_DEST_ID` | int8 | yes | — |  |
| `BAT_PLAY_TX` | string | yes | — |  |
| `RUN1_PLAY_TX` | string | yes | — |  |
| `RUN2_PLAY_TX` | string | yes | — |  |
| `RUN3_PLAY_TX` | string | yes | — |  |
| `RUN1_SB_FL` | bool | yes | — |  |
| `RUN2_SB_FL` | bool | yes | — |  |
| `RUN3_SB_FL` | bool | yes | — |  |
| `RUN1_CS_FL` | bool | yes | — |  |
| `RUN2_CS_FL` | bool | yes | — |  |
| `RUN3_CS_FL` | bool | yes | — |  |
| `RUN1_PK_FL` | bool | yes | — |  |
| `RUN2_PK_FL` | bool | yes | — |  |
| `RUN3_PK_FL` | bool | yes | — |  |
| `RUN1_RESP_PIT_ID` | string | yes | — |  |
| `RUN2_RESP_PIT_ID` | string | yes | — |  |
| `RUN3_RESP_PIT_ID` | string | yes | — |  |
| `GAME_NEW_FL` | bool | yes | — |  |
| `GAME_END_FL` | bool | yes | — |  |
| `PR_RUN1_FL` | bool | yes | — |  |
| `PR_RUN2_FL` | bool | yes | — |  |
| `PR_RUN3_FL` | bool | yes | — |  |
| `REMOVED_FOR_PR_RUN1_ID` | string | yes | — |  |
| `REMOVED_FOR_PR_RUN2_ID` | string | yes | — |  |
| `REMOVED_FOR_PR_RUN3_ID` | string | yes | — |  |
| `REMOVED_FOR_PH_BAT_ID` | string | yes | — |  |
| `REMOVED_FOR_PH_BAT_FLD_CD` | int8 | yes | — |  |
| `PO1_FLD_CD` | int8 | yes | — |  |
| `PO2_FLD_CD` | int8 | yes | — |  |
| `PO3_FLD_CD` | int8 | yes | — |  |
| `ASS1_FLD_CD` | int8 | yes | — |  |
| `ASS2_FLD_CD` | int8 | yes | — |  |
| `ASS3_FLD_CD` | int8 | yes | — |  |
| `ERR1_FLD_CD_NEW` | int8 | yes | — |  |
| `ERR2_FLD_CD_NEW` | int8 | yes | — |  |
| `ERR3_FLD_CD_NEW` | int8 | yes | — |  |
| `BAT_LAST_ID` | int8 | yes | — |  |

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
| `date` | date32[day] | yes | — |  |
| `game_num` | int8 | yes | — |  |
| `day_of_week` | string | yes | — |  |
| `visiting_team` | string | yes | — |  |
| `visiting_league` | string | yes | — |  |
| `visiting_game_num` | int16 | yes | — |  |
| `home_team` | string | yes | — |  |
| `home_league` | string | yes | — |  |
| `home_game_num` | int16 | yes | — |  |
| `visiting_score` | int16 | yes | — |  |
| `home_score` | int16 | yes | — |  |
| `outs_total` | int16 | yes | — |  |
| `day_night` | string | yes | — |  |
| `completion` | string | yes | — |  |
| `forfeit` | string | yes | — |  |
| `protest` | string | yes | — |  |
| `park_id` | string | yes | — |  |
| `attendance` | int32 | yes | — |  |
| `time_of_game` | int16 | yes | — |  |
| `visiting_line_score` | string | yes | — |  |
| `home_line_score` | string | yes | — |  |
| `v_ab` | int16 | yes | — |  |
| `v_h` | int16 | yes | — |  |
| `v_2b` | int16 | yes | — |  |
| `v_3b` | int16 | yes | — |  |
| `v_hr` | int16 | yes | — |  |
| `v_rbi` | int16 | yes | — |  |
| `v_sh` | int16 | yes | — |  |
| `v_sf` | int16 | yes | — |  |
| `v_hbp` | int16 | yes | — |  |
| `v_bb` | int16 | yes | — |  |
| `v_ibb` | int16 | yes | — |  |
| `v_so` | int16 | yes | — |  |
| `v_sb` | int16 | yes | — |  |
| `v_cs` | int16 | yes | — |  |
| `v_gidp` | int16 | yes | — |  |
| `v_ci` | int16 | yes | — |  |
| `v_lob` | int16 | yes | — |  |
| `v_pitchers_used` | int16 | yes | — |  |
| `v_ind_er` | int16 | yes | — |  |
| `v_team_er` | int16 | yes | — |  |
| `v_wp` | int16 | yes | — |  |
| `v_balks` | int16 | yes | — |  |
| `v_putouts` | int16 | yes | — |  |
| `v_assists` | int16 | yes | — |  |
| `v_errors` | int16 | yes | — |  |
| `v_passed_balls` | int16 | yes | — |  |
| `v_double_plays` | int16 | yes | — |  |
| `v_triple_plays` | int16 | yes | — |  |
| `h_ab` | int16 | yes | — |  |
| `h_h` | int16 | yes | — |  |
| `h_2b` | int16 | yes | — |  |
| `h_3b` | int16 | yes | — |  |
| `h_hr` | int16 | yes | — |  |
| `h_rbi` | int16 | yes | — |  |
| `h_sh` | int16 | yes | — |  |
| `h_sf` | int16 | yes | — |  |
| `h_hbp` | int16 | yes | — |  |
| `h_bb` | int16 | yes | — |  |
| `h_ibb` | int16 | yes | — |  |
| `h_so` | int16 | yes | — |  |
| `h_sb` | int16 | yes | — |  |
| `h_cs` | int16 | yes | — |  |
| `h_gidp` | int16 | yes | — |  |
| `h_ci` | int16 | yes | — |  |
| `h_lob` | int16 | yes | — |  |
| `h_pitchers_used` | int16 | yes | — |  |
| `h_ind_er` | int16 | yes | — |  |
| `h_team_er` | int16 | yes | — |  |
| `h_wp` | int16 | yes | — |  |
| `h_balks` | int16 | yes | — |  |
| `h_putouts` | int16 | yes | — |  |
| `h_assists` | int16 | yes | — |  |
| `h_errors` | int16 | yes | — |  |
| `h_passed_balls` | int16 | yes | — |  |
| `h_double_plays` | int16 | yes | — |  |
| `h_triple_plays` | int16 | yes | — |  |
| `hp_ump_id` | string | yes | — |  |
| `hp_ump_name` | string | yes | — |  |
| `1b_ump_id` | string | yes | — |  |
| `1b_ump_name` | string | yes | — |  |
| `2b_ump_id` | string | yes | — |  |
| `2b_ump_name` | string | yes | — |  |
| `3b_ump_id` | string | yes | — |  |
| `3b_ump_name` | string | yes | — |  |
| `lf_ump_id` | string | yes | — |  |
| `lf_ump_name` | string | yes | — |  |
| `rf_ump_id` | string | yes | — |  |
| `rf_ump_name` | string | yes | — |  |
| `v_manager_id` | string | yes | — |  |
| `v_manager_name` | string | yes | — |  |
| `h_manager_id` | string | yes | — |  |
| `h_manager_name` | string | yes | — |  |
| `win_pitcher_id` | string | yes | — |  |
| `win_pitcher_name` | string | yes | — |  |
| `lose_pitcher_id` | string | yes | — |  |
| `lose_pitcher_name` | string | yes | — |  |
| `save_pitcher_id` | string | yes | — |  |
| `save_pitcher_name` | string | yes | — |  |
| `gwrbi_id` | string | yes | — |  |
| `gwrbi_name` | string | yes | — |  |
| `v_start_pitcher_id` | string | yes | — |  |
| `v_start_pitcher_name` | string | yes | — |  |
| `h_start_pitcher_id` | string | yes | — |  |
| `h_start_pitcher_name` | string | yes | — |  |
| `v_b1_id` | string | yes | — |  |
| `v_b1_name` | string | yes | — |  |
| `v_b1_pos` | int8 | yes | — |  |
| `v_b2_id` | string | yes | — |  |
| `v_b2_name` | string | yes | — |  |
| `v_b2_pos` | int8 | yes | — |  |
| `v_b3_id` | string | yes | — |  |
| `v_b3_name` | string | yes | — |  |
| `v_b3_pos` | int8 | yes | — |  |
| `v_b4_id` | string | yes | — |  |
| `v_b4_name` | string | yes | — |  |
| `v_b4_pos` | int8 | yes | — |  |
| `v_b5_id` | string | yes | — |  |
| `v_b5_name` | string | yes | — |  |
| `v_b5_pos` | int8 | yes | — |  |
| `v_b6_id` | string | yes | — |  |
| `v_b6_name` | string | yes | — |  |
| `v_b6_pos` | int8 | yes | — |  |
| `v_b7_id` | string | yes | — |  |
| `v_b7_name` | string | yes | — |  |
| `v_b7_pos` | int8 | yes | — |  |
| `v_b8_id` | string | yes | — |  |
| `v_b8_name` | string | yes | — |  |
| `v_b8_pos` | int8 | yes | — |  |
| `v_b9_id` | string | yes | — |  |
| `v_b9_name` | string | yes | — |  |
| `v_b9_pos` | int8 | yes | — |  |
| `h_b1_id` | string | yes | — |  |
| `h_b1_name` | string | yes | — |  |
| `h_b1_pos` | int8 | yes | — |  |
| `h_b2_id` | string | yes | — |  |
| `h_b2_name` | string | yes | — |  |
| `h_b2_pos` | int8 | yes | — |  |
| `h_b3_id` | string | yes | — |  |
| `h_b3_name` | string | yes | — |  |
| `h_b3_pos` | int8 | yes | — |  |
| `h_b4_id` | string | yes | — |  |
| `h_b4_name` | string | yes | — |  |
| `h_b4_pos` | int8 | yes | — |  |
| `h_b5_id` | string | yes | — |  |
| `h_b5_name` | string | yes | — |  |
| `h_b5_pos` | int8 | yes | — |  |
| `h_b6_id` | string | yes | — |  |
| `h_b6_name` | string | yes | — |  |
| `h_b6_pos` | int8 | yes | — |  |
| `h_b7_id` | string | yes | — |  |
| `h_b7_name` | string | yes | — |  |
| `h_b7_pos` | int8 | yes | — |  |
| `h_b8_id` | string | yes | — |  |
| `h_b8_name` | string | yes | — |  |
| `h_b8_pos` | int8 | yes | — |  |
| `h_b9_id` | string | yes | — |  |
| `h_b9_name` | string | yes | — |  |
| `h_b9_pos` | int8 | yes | — |  |
| `additional_info` | string | yes | — |  |
| `acquisition_info` | string | yes | — |  |

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
| `date` | date32[day] | yes | — |  |
| `game_num` | int8 | yes | — |  |
| `day_of_week` | string | yes | — |  |
| `visiting_team` | string | yes | — |  |
| `visiting_league` | string | yes | — |  |
| `visiting_game_num` | int16 | yes | — |  |
| `home_team` | string | yes | — |  |
| `home_league` | string | yes | — |  |
| `home_game_num` | int16 | yes | — |  |
| `visiting_score` | int16 | yes | — |  |
| `home_score` | int16 | yes | — |  |
| `outs_total` | int16 | yes | — |  |
| `day_night` | string | yes | — |  |
| `completion` | string | yes | — |  |
| `forfeit` | string | yes | — |  |
| `protest` | string | yes | — |  |
| `park_id` | string | yes | — |  |
| `attendance` | int32 | yes | — |  |
| `time_of_game` | int16 | yes | — |  |
| `visiting_line_score` | string | yes | — |  |
| `home_line_score` | string | yes | — |  |
| `v_ab` | int16 | yes | — |  |
| `v_h` | int16 | yes | — |  |
| `v_2b` | int16 | yes | — |  |
| `v_3b` | int16 | yes | — |  |
| `v_hr` | int16 | yes | — |  |
| `v_rbi` | int16 | yes | — |  |
| `v_sh` | int16 | yes | — |  |
| `v_sf` | int16 | yes | — |  |
| `v_hbp` | int16 | yes | — |  |
| `v_bb` | int16 | yes | — |  |
| `v_ibb` | int16 | yes | — |  |
| `v_so` | int16 | yes | — |  |
| `v_sb` | int16 | yes | — |  |
| `v_cs` | int16 | yes | — |  |
| `v_gidp` | int16 | yes | — |  |
| `v_ci` | int16 | yes | — |  |
| `v_lob` | int16 | yes | — |  |
| `v_pitchers_used` | int16 | yes | — |  |
| `v_ind_er` | int16 | yes | — |  |
| `v_team_er` | int16 | yes | — |  |
| `v_wp` | int16 | yes | — |  |
| `v_balks` | int16 | yes | — |  |
| `v_putouts` | int16 | yes | — |  |
| `v_assists` | int16 | yes | — |  |
| `v_errors` | int16 | yes | — |  |
| `v_passed_balls` | int16 | yes | — |  |
| `v_double_plays` | int16 | yes | — |  |
| `v_triple_plays` | int16 | yes | — |  |
| `h_ab` | int16 | yes | — |  |
| `h_h` | int16 | yes | — |  |
| `h_2b` | int16 | yes | — |  |
| `h_3b` | int16 | yes | — |  |
| `h_hr` | int16 | yes | — |  |
| `h_rbi` | int16 | yes | — |  |
| `h_sh` | int16 | yes | — |  |
| `h_sf` | int16 | yes | — |  |
| `h_hbp` | int16 | yes | — |  |
| `h_bb` | int16 | yes | — |  |
| `h_ibb` | int16 | yes | — |  |
| `h_so` | int16 | yes | — |  |
| `h_sb` | int16 | yes | — |  |
| `h_cs` | int16 | yes | — |  |
| `h_gidp` | int16 | yes | — |  |
| `h_ci` | int16 | yes | — |  |
| `h_lob` | int16 | yes | — |  |
| `h_pitchers_used` | int16 | yes | — |  |
| `h_ind_er` | int16 | yes | — |  |
| `h_team_er` | int16 | yes | — |  |
| `h_wp` | int16 | yes | — |  |
| `h_balks` | int16 | yes | — |  |
| `h_putouts` | int16 | yes | — |  |
| `h_assists` | int16 | yes | — |  |
| `h_errors` | int16 | yes | — |  |
| `h_passed_balls` | int16 | yes | — |  |
| `h_double_plays` | int16 | yes | — |  |
| `h_triple_plays` | int16 | yes | — |  |
| `hp_ump_id` | string | yes | — |  |
| `hp_ump_name` | string | yes | — |  |
| `1b_ump_id` | string | yes | — |  |
| `1b_ump_name` | string | yes | — |  |
| `2b_ump_id` | string | yes | — |  |
| `2b_ump_name` | string | yes | — |  |
| `3b_ump_id` | string | yes | — |  |
| `3b_ump_name` | string | yes | — |  |
| `lf_ump_id` | string | yes | — |  |
| `lf_ump_name` | string | yes | — |  |
| `rf_ump_id` | string | yes | — |  |
| `rf_ump_name` | string | yes | — |  |
| `v_manager_id` | string | yes | — |  |
| `v_manager_name` | string | yes | — |  |
| `h_manager_id` | string | yes | — |  |
| `h_manager_name` | string | yes | — |  |
| `win_pitcher_id` | string | yes | — |  |
| `win_pitcher_name` | string | yes | — |  |
| `lose_pitcher_id` | string | yes | — |  |
| `lose_pitcher_name` | string | yes | — |  |
| `save_pitcher_id` | string | yes | — |  |
| `save_pitcher_name` | string | yes | — |  |
| `gwrbi_id` | string | yes | — |  |
| `gwrbi_name` | string | yes | — |  |
| `v_start_pitcher_id` | string | yes | — |  |
| `v_start_pitcher_name` | string | yes | — |  |
| `h_start_pitcher_id` | string | yes | — |  |
| `h_start_pitcher_name` | string | yes | — |  |
| `v_b1_id` | string | yes | — |  |
| `v_b1_name` | string | yes | — |  |
| `v_b1_pos` | int8 | yes | — |  |
| `v_b2_id` | string | yes | — |  |
| `v_b2_name` | string | yes | — |  |
| `v_b2_pos` | int8 | yes | — |  |
| `v_b3_id` | string | yes | — |  |
| `v_b3_name` | string | yes | — |  |
| `v_b3_pos` | int8 | yes | — |  |
| `v_b4_id` | string | yes | — |  |
| `v_b4_name` | string | yes | — |  |
| `v_b4_pos` | int8 | yes | — |  |
| `v_b5_id` | string | yes | — |  |
| `v_b5_name` | string | yes | — |  |
| `v_b5_pos` | int8 | yes | — |  |
| `v_b6_id` | string | yes | — |  |
| `v_b6_name` | string | yes | — |  |
| `v_b6_pos` | int8 | yes | — |  |
| `v_b7_id` | string | yes | — |  |
| `v_b7_name` | string | yes | — |  |
| `v_b7_pos` | int8 | yes | — |  |
| `v_b8_id` | string | yes | — |  |
| `v_b8_name` | string | yes | — |  |
| `v_b8_pos` | int8 | yes | — |  |
| `v_b9_id` | string | yes | — |  |
| `v_b9_name` | string | yes | — |  |
| `v_b9_pos` | int8 | yes | — |  |
| `h_b1_id` | string | yes | — |  |
| `h_b1_name` | string | yes | — |  |
| `h_b1_pos` | int8 | yes | — |  |
| `h_b2_id` | string | yes | — |  |
| `h_b2_name` | string | yes | — |  |
| `h_b2_pos` | int8 | yes | — |  |
| `h_b3_id` | string | yes | — |  |
| `h_b3_name` | string | yes | — |  |
| `h_b3_pos` | int8 | yes | — |  |
| `h_b4_id` | string | yes | — |  |
| `h_b4_name` | string | yes | — |  |
| `h_b4_pos` | int8 | yes | — |  |
| `h_b5_id` | string | yes | — |  |
| `h_b5_name` | string | yes | — |  |
| `h_b5_pos` | int8 | yes | — |  |
| `h_b6_id` | string | yes | — |  |
| `h_b6_name` | string | yes | — |  |
| `h_b6_pos` | int8 | yes | — |  |
| `h_b7_id` | string | yes | — |  |
| `h_b7_name` | string | yes | — |  |
| `h_b7_pos` | int8 | yes | — |  |
| `h_b8_id` | string | yes | — |  |
| `h_b8_name` | string | yes | — |  |
| `h_b8_pos` | int8 | yes | — |  |
| `h_b9_id` | string | yes | — |  |
| `h_b9_name` | string | yes | — |  |
| `h_b9_pos` | int8 | yes | — |  |
| `additional_info` | string | yes | — |  |
| `acquisition_info` | string | yes | — |  |

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
| `park_id` | string | yes | `PARKID` |  |
| `name` | string | yes | `NAME` |  |
| `aka` | string | yes | `AKA` |  |
| `city` | string | yes | `CITY` |  |
| `state` | string | yes | `STATE` |  |
| `start_date` | date32[day] (`%m/%d/%Y`) | yes | `START` |  |
| `end_date` | date32[day] (`%m/%d/%Y`) | yes | `END` |  |
| `league` | string | yes | `LEAGUE` |  |
| `notes` | string | yes | `NOTES` |  |
| `_extras` | string | yes | — |  |

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
| `player_id` | string | yes | `PLAYERID` |  |
| `last_name` | string | yes | `LAST` |  |
| `first_name` | string | yes | `FIRST` |  |
| `nickname` | string | yes | `NICKNAME` |  |
| `birthdate` | string | yes | `BIRTHDATE` |  |
| `birth_city` | string | yes | `BIRTH.CITY` |  |
| `birth_state` | string | yes | `BIRTH.STATE` |  |
| `birth_country` | string | yes | `BIRTH.COUNTRY` |  |
| `play_debut` | date32[day] (`%m/%d/%Y`) | yes | `PLAY.DEBUT` |  |
| `play_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `PLAY.LASTGAME` |  |
| `mgr_debut` | date32[day] (`%m/%d/%Y`) | yes | `MGR.DEBUT` |  |
| `mgr_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `MGR.LASTGAME` |  |
| `coach_debut` | date32[day] (`%m/%d/%Y`) | yes | `COACH.DEBUT` |  |
| `coach_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `COACH.LASTGAME` |  |
| `ump_debut` | date32[day] (`%m/%d/%Y`) | yes | `UMP.DEBUT` |  |
| `ump_lastgame` | date32[day] (`%m/%d/%Y`) | yes | `UMP.LASTGAME` |  |
| `deathdate` | string | yes | `DEATHDATE` |  |
| `death_city` | string | yes | `DEATH.CITY` |  |
| `death_state` | string | yes | `DEATH.STATE` |  |
| `death_country` | string | yes | `DEATH.COUNTRY` |  |
| `bats` | string | yes | `BATS` |  |
| `throws` | string | yes | `THROWS` |  |
| `height` | string | yes | `HEIGHT` |  |
| `weight` | double | yes | `WEIGHT` |  |
| `cemetery` | string | yes | `CEMETERY` |  |
| `ceme_city` | string | yes | `CEME.CITY` |  |
| `ceme_state` | string | yes | `CEME.STATE` |  |
| `ceme_country` | string | yes | `CEME.COUNTRY` |  |
| `ceme_note` | string | yes | `CEME.NOTE` |  |
| `birth_name` | string | yes | `BIRTH.NAME` |  |
| `name_chg` | string | yes | `NAME.CHG` |  |
| `bat_chg` | string | yes | `BAT.CHG` |  |
| `hof` | string | yes | `HOF` |  |
| `_extras` | string | yes | — |  |

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
| `player_id` | string | yes | `id` |  |
| `last_name` | string | yes | `lastname` |  |
| `use_name` | string | yes | `usename` |  |
| `full_name` | string | yes | `fullname` |  |
| `birthdate` | string | yes | — |  |
| `birthcity` | string | yes | — |  |
| `birthstate` | string | yes | — |  |
| `birthcountry` | string | yes | — |  |
| `deathdate` | string | yes | — |  |
| `deathcity` | string | yes | — |  |
| `deathstate` | string | yes | — |  |
| `deathcountry` | string | yes | — |  |
| `cemetery` | string | yes | — |  |
| `cem_city` | string | yes | — |  |
| `cem_state` | string | yes | — |  |
| `cem_ctry` | string | yes | — |  |
| `cem_note` | string | yes | — |  |
| `birth_name` | string | yes | `birthname` |  |
| `alt_name` | string | yes | `altname` |  |
| `debut_p` | date32[day] (`%Y%m%d`) | yes | — |  |
| `last_p` | date32[day] (`%Y%m%d`) | yes | — |  |
| `debut_c` | date32[day] (`%Y%m%d`) | yes | — |  |
| `last_c` | date32[day] (`%Y%m%d`) | yes | — |  |
| `debut_m` | date32[day] (`%Y%m%d`) | yes | — |  |
| `last_m` | date32[day] (`%Y%m%d`) | yes | — |  |
| `debut_u` | date32[day] (`%Y%m%d`) | yes | — |  |
| `last_u` | date32[day] (`%Y%m%d`) | yes | — |  |
| `bats` | string | yes | — |  |
| `throws` | string | yes | — |  |
| `height` | double | yes | — |  |
| `weight` | double | yes | — |  |
| `hof` | string | yes | `HOF` |  |
| `_extras` | string | yes | — |  |

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
| `person_id` | string | yes | `id` |  |
| `year` | int16 | yes | — |  |
| `team_id` | string | yes | `team` |  |
| `role` | string | yes | — |  |
| `start_date` | date32[day] (`%m/%d/%Y`) | yes | `start` |  |
| `end_date` | date32[day] (`%m/%d/%Y`) | yes | `end` |  |
| `_extras` | string | yes | — |  |

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
| `game_id` | string | yes | `GAMEID` |  |
| `ejection_date` | date32[day] (`%m/%d/%Y`) | yes | `DATE` |  |
| `dh` | int16 | yes | `DH` |  |
| `ejectee_id` | string | yes | `EJECTEE` |  |
| `ejectee_name` | string | yes | `EJECTEENAME` |  |
| `team_id` | string | yes | `TEAM` |  |
| `job` | string | yes | `JOB` |  |
| `umpire_id` | string | yes | `UMPIRE` |  |
| `umpire_name` | string | yes | `UMPIRENAME` |  |
| `inning` | int16 | yes | `INNING` |  |
| `reason` | string | yes | `REASON` |  |
| `_extras` | string | yes | — |  |

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
| `person_id_1` | string | yes | `id1` |  |
| `relation` | string | yes | — |  |
| `person_id_2` | string | yes | `id2` |  |
| `_extras` | string | yes | — |  |

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
| `team_id` | string | yes | `TEAM` |  |
| `league` | string | yes | `LEAGUE` |  |
| `city` | string | yes | `CITY` |  |
| `nickname` | string | yes | `NICKNAME` |  |
| `first_year` | int16 | yes | `FIRST` |  |
| `last_year` | int16 | yes | `LAST` |  |
| `_extras` | string | yes | — |  |

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
| `player_id` | string | yes | — |  |
| `last_name` | string | yes | — |  |
| `first_name` | string | yes | — |  |
| `bats` | string | yes | — |  |
| `throws` | string | yes | — |  |
| `team` | string | yes | — |  |
| `position` | string | yes | — |  |
| `year` | int16 | yes | — |  |

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
| `game_date` | date32[day] (`%Y%m%d`) | yes | `Date` |  |
| `game_number` | int16 | yes | `Num` |  |
| `day_of_week` | string | yes | `Day` |  |
| `visitor_team` | string | yes | `Visitor` |  |
| `visitor_league` | string | yes | `League` |  |
| `visitor_game_number` | int16 | yes | `Game` |  |
| `home_team` | string | yes | `Home` |  |
| `home_league` | string | yes | `League__2` |  |
| `home_game_number` | int16 | yes | `Game__2` |  |
| `day_night` | string | yes | `Day/Night` |  |
| `postponed` | string | yes | `Postponed` |  |
| `makeup_date` | string | yes | `Makeup` |  |
| `park_id` | string | yes | `Location` |  |
| `_extras` | string | yes | — |  |

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
| `GAME_ID` | string | yes | — |  |
| `INN_CT` | int16 | yes | — |  |
| `BAT_HOME_ID` | int16 | yes | — |  |
| `SUB_ID` | string | yes | — |  |
| `SUB_HOME_ID` | int16 | yes | — |  |
| `SUB_LINEUP_ID` | int16 | yes | — |  |
| `SUB_FLD_CD` | int16 | yes | — |  |
| `REMOVED_ID` | string | yes | — |  |
| `REMOVED_FLD_CD` | int16 | yes | — |  |
| `EVENT_ID` | int16 | yes | — |  |
| `BALLS_CT` | int16 | yes | — |  |
| `STRIKES_CT` | int16 | yes | — |  |
| `PITCH_SEQ_TX` | string | yes | — |  |
| `PA_BALL_CT` | int16 | yes | — |  |
| `PA_CALLED_BALL_CT` | int16 | yes | — |  |
| `PA_INTENT_BALL_CT` | int16 | yes | — |  |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — |  |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — |  |
| `PA_OTHER_BALL_CT` | int16 | yes | — |  |
| `PA_STRIKE_CT` | int16 | yes | — |  |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — |  |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — |  |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — |  |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — |  |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — |  |
| `COUNT_TX` | string | yes | — |  |

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
| `umpire_id` | string | yes | `ID` |  |
| `last_name` | string | yes | `last` |  |
| `first_name` | string | yes | `first` |  |
| `_extras` | string | yes | — |  |

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
| `game_date` | date32[day] (`%Y%m%d`) | yes | `Date` |  |
| `game_number` | int16 | yes | `Num` |  |
| `day_of_week` | string | yes | `Day` |  |
| `visitor_team` | string | yes | `Visitor` |  |
| `visitor_league` | string | yes | `League` |  |
| `visitor_game_number` | int16 | yes | `Game` |  |
| `home_team` | string | yes | `Home` |  |
| `home_league` | string | yes | `League__2` |  |
| `home_game_number` | int16 | yes | `Game__2` |  |
| `day_night` | string | yes | `Day/Night` |  |
| `postponed` | string | yes | `Postponed` |  |
| `makeup_date` | string | yes | `Makeup` |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:retrosheet.schedule_original -->
