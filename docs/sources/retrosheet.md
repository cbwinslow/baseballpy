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
- **Parsing:** CPU-bound and offline; files are parsed one at a time (optionally in a bounded process pool, `LakeConfig.parse_workers`). Event, daily, substitution, roster, game-log and flat-file datasets stream into the Parquet writer one file per row group; the derived box scores and the box accounts hold one season in memory (a few MB) before writing. Never more than one season is held at once, and export (`baseballpy export`) also reads, writes and verifies one season at a time.
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

#### Box-score info fields and their sentinels (spec: retrosheet.org/eventfile.htm, read 2026-11-12)
The scoring and entry fields were hidden in `_extras` for 8,787 games until the round-trip check; they are now typed columns of `box_games`: `scorer`, `howscored`, `pitches` (`pitches`, `count` or `none`), `inputter`, `inputtime`, `inputprogvers`, `edittime`, `translator` (text) and `htbf` (boolean: the home team batted first, normally absent). `fieldcon` (127 games) is an upstream misspelling of `fieldcond` and is kept as its own column as written. Values that mean "unknown" are **kept as written, not turned into NULL**: `temp` `0`, `attendance` `0` (also the first game of a doubleheader), `timeofgame` `0`, `windspeed` `-1`, `starttime` `0:00` or `unknown`, and the text `unknown` in `precip`, `sky`, `winddir`, `fieldcond`, `daynight`. A model must treat them as missing. `gametype` was added in 2023 (`regular`, `exhibition`, `preseason`, `allstar`, `playoff`, `worldseries`, `lcs`, `divisionseries`, `wildcard`, `championship`). Roster lines without a 7th field have a NULL `position`.

### 4. Daily Player Splits (`daily`)
Derived with `chadwickpy.tools.daily.daily_lines` (154 columns) — dataset `daily_splits`.

### 5. Substitutions (`sub`)
Derived with `chadwickpy.tools.sub.sub_lines` (26 columns) — dataset `substitutions`.

### 6. Rosters, schedules, umpires, discrepancies
- `rosters`: `.ROS` files are header-less (`player_id,last,first,bats,throws,team,position`). The `roster` column holds the file's team code (`HOU`, or `ALS`/`NLS` for the all-star rosters, which repeat each player's club line), so the key is `(year, roster, player_id)`.
- `schedule`: header-based; a few old files (1904, 1921, 1933) ship **without a header row** and get the documented default header; 2022 has two doubleheader games numbered `0` (the key includes the per-team game number); only the schedule exists for 2026.
- `umpires`: `UMPIRES<year>.txt` (`ID,last,first`), one file per season, so `umpire_id` repeats across seasons.
- `discrepancies`: the AL/NL/federal discrepancy lists. About 5,300 rows in the 1900–1949 files have 14 instead of 15 fields and are padded with NULLs (logged); an unnamed 13th column is exposed as `flag`.

### 7. Reference Directories (`reference/`)
Every CSV in the tree's `reference/` directory is ingested by header name: `ballparks`, `teams`, `ejections`, `coaches`, `relatives`, `biofile` and `biofile0`. Quirks verified on the real files:
- Dates are `M/D/YYYY` (single digits allowed) in `biofile`, `ballparks`, `coaches`, `ejections` and `YYYYMMDD` in `biofile0`.
- Birth/death dates in both biofiles can be **partial** (`1906`, `5/1906`, `19010000`); those two columns stay text, all other dates are `date32`.
- `biofile` and `biofile0` describe the same 27,049 people with different headers and encodings; both are kept.
- Column order never matters: columns are matched by upstream header name, unknown columns land in `_extras` (JSON) with a one-time `schema_drift` warning.

### 8. Files from retrosheet.org (opt-in, the `site` unit)
The GitHub mirror does not carry everything Retrosheet publishes. Eighteen more datasets are parsed from zips on retrosheet.org itself; they are **opt-in**, so a default `baseballpy ingest retrosheet` never contacts that site. Ingest them with `baseballpy ingest retrosheet -d site` (all) or `-d transactions -d umpire_logs` (some); read them with `baseballpy.read("retrosheet.transactions")` or SQL on the view `retrosheet_transactions`.
- `transactions` (`tranDB.zip`): trades, draft, free agency, injured list and more, 101,594 rows. Dates stay text because some are partial (`19520000`: month and day unknown); `transaction_id` is shared by the players of a trade.
- `managers0`, `umpires0`, `coaches0`, `ballparks0`, `teams0` (`biodata.zip`): biography tables with first and last game dates.
- `player_batting_logs`, `player_fielding_logs`, `player_pitching_logs` (`playerlogs.zip`, one CSV per player): every player game line, 5.8 million, 5.3 million and 1.3 million rows.
- `negro_players`, `negro_games`, `negro_team_stats`, `negro_batting`, `negro_pitching`, `negro_fielding`, `negro_plays` (`negroleagues.zip`): the Negro Leagues, 8,215 games (1903 to 1962) with play-by-play (168,152 plays). Our event tables hold none of these games and the box-score tables only 4,647 of them, so these are the full record. Line scores stay text (`x` = inning not played).
- `manager_logs` (`mgrlogs.zip`): 506,098 team game lines; `umpire_logs` (`umplogs.zip`): 771,683 rows, with an `umpire_id` column taken from the file name.
A zip already in `raw/retrosheet/site_files/` is never requested again; a missing one is fetched politely: robots.txt obeyed, one request every four seconds, the run stops at the first 403, 429 or 503. A few rows are exact duplicates upstream (2 in transactions, 7 in batting logs, 3 in umpire logs) and are kept. The event CSV bundles (`csvdownloads.zip`, `basiccsvs.zip`: parsed play-by-play that repeats the event files we already parse) and the 184 official-totals ledgers (hundreds of MB each, format not yet opened) are downloadable raw files only, not tables. Attribution: "The information used here was obtained free of charge from and is copyrighted by Retrosheet."

## Freshness
Retrosheet data is immutable at a pinned commit, and what is stored is judged by git fingerprints (ADR 43, ADR 48):
- **Raw files:** each file records the git blob SHA the pinned tree lists for it. When the pin moves (`baseballpy refs update`) only files whose blob SHA changed are downloaded again; unchanged files are kept. A file stored before fingerprints existed is judged by the pinned commit it was recorded at.
- **Processed chunks:** each chunk records one fingerprint (a digest of the blob SHAs of the raw files it was built from). It is served only while that fingerprint matches the tree; after a pin move, only chunks built from changed files are rebuilt. When the tree cannot be listed (offline) the chunk's recorded pinned commit decides.
- `refresh=True` (or `ingest --refresh`) downloads each needed file once and rebuilds the selected chunks. `baseballpy cache check` compares the stored fingerprints with upstream.
- **Kept documents:** the repository's `README.md` (the Retrosheet copyright and terms-of-use notice), `.gitattributes` and any file under the data folders that no pattern covers are stored raw in `raw/retrosheet/documents/` and `raw/retrosheet/unclassified/`.

## Selecting and reading datasets
- **Ingest:** `baseballpy ingest retrosheet -d <name> --seasons 2023` accepts any registered dataset name (`events`, `box_games`, `boxscores_batting`, `reference_teams`, ...). A name is resolved to the unit that writes it, so `box_games` builds all four `box_*` datasets and `reference_teams` ingests every `reference/*.csv` table and the postseason game logs. Season datasets need `--seasons`; only the raw files the selection reads are downloaded.
- **Python:** `baseballpy.sources.retrosheet.table(name, season)` returns any registered dataset (`table("box_games", 2023)`, `table("reference_teams")`, `table("gamelogs_postseason", kind="world_series")`); the named functions (`events`, `rosters`, ...) remain.

## Data quality
After the datasets of a season are stored, `ingest` checks them and records the findings in the processed manifest (shown by `baseballpy catalog status`; they never stop an ingest): duplicate keys, and player ids in events, box scores, daily splits, substitutions and rosters that match no roster of the same season (rosters themselves are compared with the Chadwick register's `key_retro` when it is cached). `boxscores_batting` is keyed `(game_id, team_id, slot, seq)`: `seq` numbers the occupants of a batting slot (starter first), so a player who re-enters in the same slot gets two rows (checked unique on 12,112 real rows).

**Export** (`baseballpy export retrosheet --to parquet|csv|duckdb|postgres`, checked 2026-10-30 on the 2015-2026 lake with read-back verification): all 23 stored datasets verify as Parquet (6.67 million rows, 40 s, peak memory 1.3 GB); 22 verify as CSV, DuckDB and PostgreSQL. The one exception is `box_records` as CSV, which is refused because its `fields` column is a list (Parquet, DuckDB and PostgreSQL keep it; PostgreSQL stores it as JSON). Seasons are exported one after another, so a season subset with `--mode replace` leaves only those seasons in the table. `--mode merge` uses the registry keys, which are unique on the real data. Empty event text is stored as NULL so the CSV round trip is exact (ADR 51).

## Dataset reference (generated)

<!-- BEGIN GENERATED:retrosheet.description_sources -->
### Description sources

- `chadwick_cwdaily`: https://raw.githubusercontent.com/chadwickbureau/chadwick/b0002b6a0c98f800f899635f5de17ebfcc976333/doc/cwdaily.rst
- `chadwick_cwevent`: https://raw.githubusercontent.com/chadwickbureau/chadwick/b0002b6a0c98f800f899635f5de17ebfcc976333/doc/cwevent.rst
- `chadwick_cwsub`: https://raw.githubusercontent.com/chadwickbureau/chadwick/b0002b6a0c98f800f899635f5de17ebfcc976333/doc/cwsub.rst
- `retrosheet_glfields`: Retrosheet game-log field guide (glfields.txt), read from the copy in the book companion repository maxtoki/baseball_R because retrosheet.org was unreachable: https://raw.githubusercontent.com/maxtoki/baseball_R/3117ffda2b8d33397095a74b3ab27b4bbb2df2a5/data/glfields.txt

<!-- END GENERATED:retrosheet.description_sources -->

<!-- BEGIN GENERATED:retrosheet.boxscores_batting -->
### Dataset: boxscores_batting

Batting box score lines.

- **View:** `retrosheet_boxscores_batting`
- **Processed path:** `processed/retrosheet/boxscores_batting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `game_id`, `team_id`, `slot`, `seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `team_id` | string | yes | — | TODO |
| `player_id` | string | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `slot` | int8 | yes | — | TODO |
| `seq` | int8 | yes | — | TODO |
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
- **Key:** `GAME_ID`, `TEAM_ID`, `PLAYER_ID`, `SLOT_CT`, `SEQ_CT`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `GAME_ID` | string | yes | — | Game ID (src: chadwick_cwdaily) |
| `GAME_DT` | date32[day] | yes | — | Game date (src: chadwick_cwdaily) |
| `GAME_CT` | int16 | yes | — | Game number (src: chadwick_cwdaily) |
| `APPEAR_DT` | date32[day] | yes | — | Player appearance date (src: chadwick_cwdaily) |
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
| `F_P_G` | int16 | yes | — | Games at the position (pitcher) (src: chadwick_cwdaily) |
| `F_P_GS` | int16 | yes | — | Games started at the position (pitcher) (src: chadwick_cwdaily) |
| `F_P_OUT` | int16 | yes | — | Outs recorded while at the position (pitcher) (src: chadwick_cwdaily) |
| `F_P_TC` | int16 | yes | — | Total chances (pitcher) (src: chadwick_cwdaily) |
| `F_P_PO` | int16 | yes | — | Putouts (pitcher) (src: chadwick_cwdaily) |
| `F_P_A` | int16 | yes | — | Assists (pitcher) (src: chadwick_cwdaily) |
| `F_P_E` | int16 | yes | — | Errors (pitcher) (src: chadwick_cwdaily) |
| `F_P_DP` | int16 | yes | — | Double plays (pitcher) (src: chadwick_cwdaily) |
| `F_P_TP` | int16 | yes | — | Triple plays (pitcher) (src: chadwick_cwdaily) |
| `F_C_G` | int16 | yes | — | Games at the position (catcher) (src: chadwick_cwdaily) |
| `F_C_GS` | int16 | yes | — | Games started at the position (catcher) (src: chadwick_cwdaily) |
| `F_C_OUT` | int16 | yes | — | Outs recorded while at the position (catcher) (src: chadwick_cwdaily) |
| `F_C_TC` | int16 | yes | — | Total chances (catcher) (src: chadwick_cwdaily) |
| `F_C_PO` | int16 | yes | — | Putouts (catcher) (src: chadwick_cwdaily) |
| `F_C_A` | int16 | yes | — | Assists (catcher) (src: chadwick_cwdaily) |
| `F_C_E` | int16 | yes | — | Errors (catcher) (src: chadwick_cwdaily) |
| `F_C_DP` | int16 | yes | — | Double plays (catcher) (src: chadwick_cwdaily) |
| `F_C_TP` | int16 | yes | — | Triple plays (catcher) (src: chadwick_cwdaily) |
| `F_C_PB` | int16 | yes | — | Passed balls (src: chadwick_cwdaily) |
| `F_C_XI` | int16 | yes | — | Catcher's interference (src: chadwick_cwdaily) |
| `F_1B_G` | int16 | yes | — | Games at the position (first base) (src: chadwick_cwdaily) |
| `F_1B_GS` | int16 | yes | — | Games started at the position (first base) (src: chadwick_cwdaily) |
| `F_1B_OUT` | int16 | yes | — | Outs recorded while at the position (first base) (src: chadwick_cwdaily) |
| `F_1B_TC` | int16 | yes | — | Total chances (first base) (src: chadwick_cwdaily) |
| `F_1B_PO` | int16 | yes | — | Putouts (first base) (src: chadwick_cwdaily) |
| `F_1B_A` | int16 | yes | — | Assists (first base) (src: chadwick_cwdaily) |
| `F_1B_E` | int16 | yes | — | Errors (first base) (src: chadwick_cwdaily) |
| `F_1B_DP` | int16 | yes | — | Double plays (first base) (src: chadwick_cwdaily) |
| `F_1B_TP` | int16 | yes | — | Triple plays (first base) (src: chadwick_cwdaily) |
| `F_2B_G` | int16 | yes | — | Games at the position (second base) (src: chadwick_cwdaily) |
| `F_2B_GS` | int16 | yes | — | Games started at the position (second base) (src: chadwick_cwdaily) |
| `F_2B_OUT` | int16 | yes | — | Outs recorded while at the position (second base) (src: chadwick_cwdaily) |
| `F_2B_TC` | int16 | yes | — | Total chances (second base) (src: chadwick_cwdaily) |
| `F_2B_PO` | int16 | yes | — | Putouts (second base) (src: chadwick_cwdaily) |
| `F_2B_A` | int16 | yes | — | Assists (second base) (src: chadwick_cwdaily) |
| `F_2B_E` | int16 | yes | — | Errors (second base) (src: chadwick_cwdaily) |
| `F_2B_DP` | int16 | yes | — | Double plays (second base) (src: chadwick_cwdaily) |
| `F_2B_TP` | int16 | yes | — | Triple plays (second base) (src: chadwick_cwdaily) |
| `F_3B_G` | int16 | yes | — | Games at the position (third base) (src: chadwick_cwdaily) |
| `F_3B_GS` | int16 | yes | — | Games started at the position (third base) (src: chadwick_cwdaily) |
| `F_3B_OUT` | int16 | yes | — | Outs recorded while at the position (third base) (src: chadwick_cwdaily) |
| `F_3B_TC` | int16 | yes | — | Total chances (third base) (src: chadwick_cwdaily) |
| `F_3B_PO` | int16 | yes | — | Putouts (third base) (src: chadwick_cwdaily) |
| `F_3B_A` | int16 | yes | — | Assists (third base) (src: chadwick_cwdaily) |
| `F_3B_E` | int16 | yes | — | Errors (third base) (src: chadwick_cwdaily) |
| `F_3B_DP` | int16 | yes | — | Double plays (third base) (src: chadwick_cwdaily) |
| `F_3B_TP` | int16 | yes | — | Triple plays (third base) (src: chadwick_cwdaily) |
| `F_SS_G` | int16 | yes | — | Games at the position (shortstop) (src: chadwick_cwdaily) |
| `F_SS_GS` | int16 | yes | — | Games started at the position (shortstop) (src: chadwick_cwdaily) |
| `F_SS_OUT` | int16 | yes | — | Outs recorded while at the position (shortstop) (src: chadwick_cwdaily) |
| `F_SS_TC` | int16 | yes | — | Total chances (shortstop) (src: chadwick_cwdaily) |
| `F_SS_PO` | int16 | yes | — | Putouts (shortstop) (src: chadwick_cwdaily) |
| `F_SS_A` | int16 | yes | — | Assists (shortstop) (src: chadwick_cwdaily) |
| `F_SS_E` | int16 | yes | — | Errors (shortstop) (src: chadwick_cwdaily) |
| `F_SS_DP` | int16 | yes | — | Double plays (shortstop) (src: chadwick_cwdaily) |
| `F_SS_TP` | int16 | yes | — | Triple plays (shortstop) (src: chadwick_cwdaily) |
| `F_LF_G` | int16 | yes | — | Games at the position (left field) (src: chadwick_cwdaily) |
| `F_LF_GS` | int16 | yes | — | Games started at the position (left field) (src: chadwick_cwdaily) |
| `F_LF_OUT` | int16 | yes | — | Outs recorded while at the position (left field) (src: chadwick_cwdaily) |
| `F_LF_TC` | int16 | yes | — | Total chances (left field) (src: chadwick_cwdaily) |
| `F_LF_PO` | int16 | yes | — | Putouts (left field) (src: chadwick_cwdaily) |
| `F_LF_A` | int16 | yes | — | Assists (left field) (src: chadwick_cwdaily) |
| `F_LF_E` | int16 | yes | — | Errors (left field) (src: chadwick_cwdaily) |
| `F_LF_DP` | int16 | yes | — | Double plays (left field) (src: chadwick_cwdaily) |
| `F_LF_TP` | int16 | yes | — | Triple plays (left field) (src: chadwick_cwdaily) |
| `F_CF_G` | int16 | yes | — | Games at the position (center field) (src: chadwick_cwdaily) |
| `F_CF_GS` | int16 | yes | — | Games started at the position (center field) (src: chadwick_cwdaily) |
| `F_CF_OUT` | int16 | yes | — | Outs recorded while at the position (center field) (src: chadwick_cwdaily) |
| `F_CF_TC` | int16 | yes | — | Total chances (center field) (src: chadwick_cwdaily) |
| `F_CF_PO` | int16 | yes | — | Putouts (center field) (src: chadwick_cwdaily) |
| `F_CF_A` | int16 | yes | — | Assists (center field) (src: chadwick_cwdaily) |
| `F_CF_E` | int16 | yes | — | Errors (center field) (src: chadwick_cwdaily) |
| `F_CF_DP` | int16 | yes | — | Double plays (center field) (src: chadwick_cwdaily) |
| `F_CF_TP` | int16 | yes | — | Triple plays (center field) (src: chadwick_cwdaily) |
| `F_RF_G` | int16 | yes | — | Games at the position (right field) (src: chadwick_cwdaily) |
| `F_RF_GS` | int16 | yes | — | Games started at the position (right field) (src: chadwick_cwdaily) |
| `F_RF_OUT` | int16 | yes | — | Outs recorded while at the position (right field) (src: chadwick_cwdaily) |
| `F_RF_TC` | int16 | yes | — | Total chances (right field) (src: chadwick_cwdaily) |
| `F_RF_PO` | int16 | yes | — | Putouts (right field) (src: chadwick_cwdaily) |
| `F_RF_A` | int16 | yes | — | Assists (right field) (src: chadwick_cwdaily) |
| `F_RF_E` | int16 | yes | — | Errors (right field) (src: chadwick_cwdaily) |
| `F_RF_DP` | int16 | yes | — | Double plays (right field) (src: chadwick_cwdaily) |
| `F_RF_TP` | int16 | yes | — | Triple plays (right field) (src: chadwick_cwdaily) |

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
| `ASS4_FLD_CD` | int16 | yes | — | Fielder with fourth assist (src: chadwick_cwevent) |
| `ASS5_FLD_CD` | int16 | yes | — | Fielder with fifth assist (src: chadwick_cwevent) |
| `EVENT_ID` | int16 | yes | — | Event number (src: chadwick_cwevent) |
| `HOME_TEAM_ID` | string | yes | — | home team id (src: chadwick_cwevent) |
| `BAT_TEAM_ID` | string | yes | — | batting team id (src: chadwick_cwevent) |
| `FLD_TEAM_ID` | string | yes | — | fielding team id (src: chadwick_cwevent) |
| `BAT_LAST_ID` | int8 | yes | — | half inning (differs from batting team if home team bats first) (src: chadwick_cwevent) |
| `INN_NEW_FL` | bool | yes | — | start of half inning flag (src: chadwick_cwevent) |
| `INN_END_FL` | bool | yes | — | end of half inning flag (src: chadwick_cwevent) |
| `START_BAT_SCORE_CT` | int16 | yes | — | score for team on offense (src: chadwick_cwevent) |
| `START_FLD_SCORE_CT` | int16 | yes | — | score for team on defense (src: chadwick_cwevent) |
| `INN_RUNS_CT` | int16 | yes | — | runs scored in this half inning (src: chadwick_cwevent) |
| `GAME_PA_CT` | int16 | yes | — | number of plate appearances in game for team on offense (src: chadwick_cwevent) |
| `INN_PA_CT` | int16 | yes | — | number of plate appearances in inning for team on offense (src: chadwick_cwevent) |
| `PA_NEW_FL` | bool | yes | — | start of plate appearance flag (src: chadwick_cwevent) |
| `PA_TRUNC_FL` | bool | yes | — | truncated plate appearance flag (src: chadwick_cwevent) |
| `START_BASES_CD` | int16 | yes | — | base state at start of play (src: chadwick_cwevent) |
| `END_BASES_CD` | int16 | yes | — | base state at end of play (src: chadwick_cwevent) |
| `BAT_START_FL` | bool | yes | — | batter is starter flag (src: chadwick_cwevent) |
| `RESP_BAT_START_FL` | bool | yes | — | result batter is starter flag (src: chadwick_cwevent) |
| `BAT_ON_DECK_ID` | string | yes | — | ID of the batter on deck (src: chadwick_cwevent) |
| `BAT_IN_HOLD_ID` | string | yes | — | ID of the batter in the hold (src: chadwick_cwevent) |
| `PIT_START_FL` | bool | yes | — | pitcher is starter flag (src: chadwick_cwevent) |
| `RESP_PIT_START_FL` | bool | yes | — | result pitcher is starter flag (src: chadwick_cwevent) |
| `RUN1_FLD_CD` | int16 | yes | — | defensive position of runner on first (src: chadwick_cwevent) |
| `RUN1_LINEUP_CD` | int16 | yes | — | lineup position of runner on first (src: chadwick_cwevent) |
| `RUN1_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on first reached base (src: chadwick_cwevent) |
| `RUN2_FLD_CD` | int16 | yes | — | defensive position of runner on second (src: chadwick_cwevent) |
| `RUN2_LINEUP_CD` | int16 | yes | — | lineup position of runner on second (src: chadwick_cwevent) |
| `RUN2_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on second reached base (src: chadwick_cwevent) |
| `RUN3_FLD_CD` | int16 | yes | — | defensive position of runner on third (src: chadwick_cwevent) |
| `RUN3_LINEUP_CD` | int16 | yes | — | lineup position of runner on third (src: chadwick_cwevent) |
| `RUN3_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on third reached base (src: chadwick_cwevent) |
| `RUN1_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on first (src: chadwick_cwevent) |
| `RUN2_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on second (src: chadwick_cwevent) |
| `RUN3_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on third (src: chadwick_cwevent) |
| `PA_BALL_CT` | int16 | yes | — | number of balls in plate appearance (src: chadwick_cwevent) |
| `PA_CALLED_BALL_CT` | int16 | yes | — | number of called balls in plate appearance (src: chadwick_cwevent) |
| `PA_INTENT_BALL_CT` | int16 | yes | — | number of intentional balls in plate appearance (src: chadwick_cwevent) |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | number of pitchouts in plate appearance (src: chadwick_cwevent) |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | number of pitches hitting batter in plate appearance (src: chadwick_cwevent) |
| `PA_OTHER_BALL_CT` | int16 | yes | — | number of other balls in plate appearance (src: chadwick_cwevent) |
| `PA_STRIKE_CT` | int16 | yes | — | number of strikes in plate appearance (src: chadwick_cwevent) |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | number of called strikes in plate appearance (src: chadwick_cwevent) |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | number of swinging strikes in plate appearance (src: chadwick_cwevent) |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | number of foul balls in plate appearance (src: chadwick_cwevent) |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | number of balls in play in plate appearance (src: chadwick_cwevent) |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | number of other strikes in plate appearance (src: chadwick_cwevent) |
| `EVENT_RUNS_CT` | int16 | yes | — | number of runs on play (src: chadwick_cwevent) |
| `FLD_ID` | string | yes | — | id of player fielding batted ball (src: chadwick_cwevent) |
| `BASE2_FORCE_FL` | bool | yes | — | force play at second flag (src: chadwick_cwevent) |
| `BASE3_FORCE_FL` | bool | yes | — | force play at third flag (src: chadwick_cwevent) |
| `BASE4_FORCE_FL` | bool | yes | — | force play at home flag (src: chadwick_cwevent) |
| `BAT_SAFE_ERR_FL` | bool | yes | — | batter safe on error flag (src: chadwick_cwevent) |
| `BAT_FATE_ID` | int16 | yes | — | fate of batter (base ultimately advanced to) (src: chadwick_cwevent) |
| `RUN1_FATE_ID` | int16 | yes | — | fate of runner on first (src: chadwick_cwevent) |
| `RUN2_FATE_ID` | int16 | yes | — | fate of runner on second (src: chadwick_cwevent) |
| `RUN3_FATE_ID` | int16 | yes | — | fate of runner on third (src: chadwick_cwevent) |
| `FATE_RUNS_CT` | int16 | yes | — | runs scored in half inning after this event (src: chadwick_cwevent) |
| `ASS6_FLD_CD` | int16 | yes | — | fielder with sixth assist (src: chadwick_cwevent) |
| `ASS7_FLD_CD` | int16 | yes | — | fielder with seventh assist (src: chadwick_cwevent) |
| `ASS8_FLD_CD` | int16 | yes | — | fielder with eighth assist (src: chadwick_cwevent) |
| `ASS9_FLD_CD` | int16 | yes | — | fielder with ninth assist (src: chadwick_cwevent) |
| `ASS10_FLD_CD` | int16 | yes | — | fielder with tenth assist (src: chadwick_cwevent) |
| `UNKNOWN_OUT_EXC_FL` | bool | yes | — | unknown fielding credit flag (src: chadwick_cwevent) |
| `UNCERTAIN_PLAY_EXC_FL` | bool | yes | — | uncertain play flag (src: chadwick_cwevent) |
| `COUNT_TX` | string | yes | — | text of count as appears in event file (src: chadwick_cwevent) |
| `RUN1_AUTO_FL` | bool | yes | — | whether runner on first is an automatic runner (src: chadwick_cwevent) |
| `RUN2_AUTO_FL` | bool | yes | — | whether runner on second is an automatic runner (src: chadwick_cwevent) |
| `RUN3_AUTO_FL` | bool | yes | — | whether runner on third is an automatic runner (src: chadwick_cwevent) |
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
| `ASS4_FLD_CD` | int16 | yes | — | Fielder with fourth assist (src: chadwick_cwevent) |
| `ASS5_FLD_CD` | int16 | yes | — | Fielder with fifth assist (src: chadwick_cwevent) |
| `EVENT_ID` | int16 | yes | — | Event number (src: chadwick_cwevent) |
| `HOME_TEAM_ID` | string | yes | — | home team id (src: chadwick_cwevent) |
| `BAT_TEAM_ID` | string | yes | — | batting team id (src: chadwick_cwevent) |
| `FLD_TEAM_ID` | string | yes | — | fielding team id (src: chadwick_cwevent) |
| `BAT_LAST_ID` | int8 | yes | — | half inning (differs from batting team if home team bats first) (src: chadwick_cwevent) |
| `INN_NEW_FL` | bool | yes | — | start of half inning flag (src: chadwick_cwevent) |
| `INN_END_FL` | bool | yes | — | end of half inning flag (src: chadwick_cwevent) |
| `START_BAT_SCORE_CT` | int16 | yes | — | score for team on offense (src: chadwick_cwevent) |
| `START_FLD_SCORE_CT` | int16 | yes | — | score for team on defense (src: chadwick_cwevent) |
| `INN_RUNS_CT` | int16 | yes | — | runs scored in this half inning (src: chadwick_cwevent) |
| `GAME_PA_CT` | int16 | yes | — | number of plate appearances in game for team on offense (src: chadwick_cwevent) |
| `INN_PA_CT` | int16 | yes | — | number of plate appearances in inning for team on offense (src: chadwick_cwevent) |
| `PA_NEW_FL` | bool | yes | — | start of plate appearance flag (src: chadwick_cwevent) |
| `PA_TRUNC_FL` | bool | yes | — | truncated plate appearance flag (src: chadwick_cwevent) |
| `START_BASES_CD` | int16 | yes | — | base state at start of play (src: chadwick_cwevent) |
| `END_BASES_CD` | int16 | yes | — | base state at end of play (src: chadwick_cwevent) |
| `BAT_START_FL` | bool | yes | — | batter is starter flag (src: chadwick_cwevent) |
| `RESP_BAT_START_FL` | bool | yes | — | result batter is starter flag (src: chadwick_cwevent) |
| `BAT_ON_DECK_ID` | string | yes | — | ID of the batter on deck (src: chadwick_cwevent) |
| `BAT_IN_HOLD_ID` | string | yes | — | ID of the batter in the hold (src: chadwick_cwevent) |
| `PIT_START_FL` | bool | yes | — | pitcher is starter flag (src: chadwick_cwevent) |
| `RESP_PIT_START_FL` | bool | yes | — | result pitcher is starter flag (src: chadwick_cwevent) |
| `RUN1_FLD_CD` | int16 | yes | — | defensive position of runner on first (src: chadwick_cwevent) |
| `RUN1_LINEUP_CD` | int16 | yes | — | lineup position of runner on first (src: chadwick_cwevent) |
| `RUN1_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on first reached base (src: chadwick_cwevent) |
| `RUN2_FLD_CD` | int16 | yes | — | defensive position of runner on second (src: chadwick_cwevent) |
| `RUN2_LINEUP_CD` | int16 | yes | — | lineup position of runner on second (src: chadwick_cwevent) |
| `RUN2_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on second reached base (src: chadwick_cwevent) |
| `RUN3_FLD_CD` | int16 | yes | — | defensive position of runner on third (src: chadwick_cwevent) |
| `RUN3_LINEUP_CD` | int16 | yes | — | lineup position of runner on third (src: chadwick_cwevent) |
| `RUN3_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on third reached base (src: chadwick_cwevent) |
| `RUN1_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on first (src: chadwick_cwevent) |
| `RUN2_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on second (src: chadwick_cwevent) |
| `RUN3_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on third (src: chadwick_cwevent) |
| `PA_BALL_CT` | int16 | yes | — | number of balls in plate appearance (src: chadwick_cwevent) |
| `PA_CALLED_BALL_CT` | int16 | yes | — | number of called balls in plate appearance (src: chadwick_cwevent) |
| `PA_INTENT_BALL_CT` | int16 | yes | — | number of intentional balls in plate appearance (src: chadwick_cwevent) |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | number of pitchouts in plate appearance (src: chadwick_cwevent) |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | number of pitches hitting batter in plate appearance (src: chadwick_cwevent) |
| `PA_OTHER_BALL_CT` | int16 | yes | — | number of other balls in plate appearance (src: chadwick_cwevent) |
| `PA_STRIKE_CT` | int16 | yes | — | number of strikes in plate appearance (src: chadwick_cwevent) |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | number of called strikes in plate appearance (src: chadwick_cwevent) |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | number of swinging strikes in plate appearance (src: chadwick_cwevent) |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | number of foul balls in plate appearance (src: chadwick_cwevent) |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | number of balls in play in plate appearance (src: chadwick_cwevent) |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | number of other strikes in plate appearance (src: chadwick_cwevent) |
| `EVENT_RUNS_CT` | int16 | yes | — | number of runs on play (src: chadwick_cwevent) |
| `FLD_ID` | string | yes | — | id of player fielding batted ball (src: chadwick_cwevent) |
| `BASE2_FORCE_FL` | bool | yes | — | force play at second flag (src: chadwick_cwevent) |
| `BASE3_FORCE_FL` | bool | yes | — | force play at third flag (src: chadwick_cwevent) |
| `BASE4_FORCE_FL` | bool | yes | — | force play at home flag (src: chadwick_cwevent) |
| `BAT_SAFE_ERR_FL` | bool | yes | — | batter safe on error flag (src: chadwick_cwevent) |
| `BAT_FATE_ID` | int16 | yes | — | fate of batter (base ultimately advanced to) (src: chadwick_cwevent) |
| `RUN1_FATE_ID` | int16 | yes | — | fate of runner on first (src: chadwick_cwevent) |
| `RUN2_FATE_ID` | int16 | yes | — | fate of runner on second (src: chadwick_cwevent) |
| `RUN3_FATE_ID` | int16 | yes | — | fate of runner on third (src: chadwick_cwevent) |
| `FATE_RUNS_CT` | int16 | yes | — | runs scored in half inning after this event (src: chadwick_cwevent) |
| `ASS6_FLD_CD` | int16 | yes | — | fielder with sixth assist (src: chadwick_cwevent) |
| `ASS7_FLD_CD` | int16 | yes | — | fielder with seventh assist (src: chadwick_cwevent) |
| `ASS8_FLD_CD` | int16 | yes | — | fielder with eighth assist (src: chadwick_cwevent) |
| `ASS9_FLD_CD` | int16 | yes | — | fielder with ninth assist (src: chadwick_cwevent) |
| `ASS10_FLD_CD` | int16 | yes | — | fielder with tenth assist (src: chadwick_cwevent) |
| `UNKNOWN_OUT_EXC_FL` | bool | yes | — | unknown fielding credit flag (src: chadwick_cwevent) |
| `UNCERTAIN_PLAY_EXC_FL` | bool | yes | — | uncertain play flag (src: chadwick_cwevent) |
| `COUNT_TX` | string | yes | — | text of count as appears in event file (src: chadwick_cwevent) |
| `RUN1_AUTO_FL` | bool | yes | — | whether runner on first is an automatic runner (src: chadwick_cwevent) |
| `RUN2_AUTO_FL` | bool | yes | — | whether runner on second is an automatic runner (src: chadwick_cwevent) |
| `RUN3_AUTO_FL` | bool | yes | — | whether runner on third is an automatic runner (src: chadwick_cwevent) |
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
| `ASS4_FLD_CD` | int16 | yes | — | Fielder with fourth assist (src: chadwick_cwevent) |
| `ASS5_FLD_CD` | int16 | yes | — | Fielder with fifth assist (src: chadwick_cwevent) |
| `EVENT_ID` | int16 | yes | — | Event number (src: chadwick_cwevent) |
| `HOME_TEAM_ID` | string | yes | — | home team id (src: chadwick_cwevent) |
| `BAT_TEAM_ID` | string | yes | — | batting team id (src: chadwick_cwevent) |
| `FLD_TEAM_ID` | string | yes | — | fielding team id (src: chadwick_cwevent) |
| `BAT_LAST_ID` | int8 | yes | — | half inning (differs from batting team if home team bats first) (src: chadwick_cwevent) |
| `INN_NEW_FL` | bool | yes | — | start of half inning flag (src: chadwick_cwevent) |
| `INN_END_FL` | bool | yes | — | end of half inning flag (src: chadwick_cwevent) |
| `START_BAT_SCORE_CT` | int16 | yes | — | score for team on offense (src: chadwick_cwevent) |
| `START_FLD_SCORE_CT` | int16 | yes | — | score for team on defense (src: chadwick_cwevent) |
| `INN_RUNS_CT` | int16 | yes | — | runs scored in this half inning (src: chadwick_cwevent) |
| `GAME_PA_CT` | int16 | yes | — | number of plate appearances in game for team on offense (src: chadwick_cwevent) |
| `INN_PA_CT` | int16 | yes | — | number of plate appearances in inning for team on offense (src: chadwick_cwevent) |
| `PA_NEW_FL` | bool | yes | — | start of plate appearance flag (src: chadwick_cwevent) |
| `PA_TRUNC_FL` | bool | yes | — | truncated plate appearance flag (src: chadwick_cwevent) |
| `START_BASES_CD` | int16 | yes | — | base state at start of play (src: chadwick_cwevent) |
| `END_BASES_CD` | int16 | yes | — | base state at end of play (src: chadwick_cwevent) |
| `BAT_START_FL` | bool | yes | — | batter is starter flag (src: chadwick_cwevent) |
| `RESP_BAT_START_FL` | bool | yes | — | result batter is starter flag (src: chadwick_cwevent) |
| `BAT_ON_DECK_ID` | string | yes | — | ID of the batter on deck (src: chadwick_cwevent) |
| `BAT_IN_HOLD_ID` | string | yes | — | ID of the batter in the hold (src: chadwick_cwevent) |
| `PIT_START_FL` | bool | yes | — | pitcher is starter flag (src: chadwick_cwevent) |
| `RESP_PIT_START_FL` | bool | yes | — | result pitcher is starter flag (src: chadwick_cwevent) |
| `RUN1_FLD_CD` | int16 | yes | — | defensive position of runner on first (src: chadwick_cwevent) |
| `RUN1_LINEUP_CD` | int16 | yes | — | lineup position of runner on first (src: chadwick_cwevent) |
| `RUN1_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on first reached base (src: chadwick_cwevent) |
| `RUN2_FLD_CD` | int16 | yes | — | defensive position of runner on second (src: chadwick_cwevent) |
| `RUN2_LINEUP_CD` | int16 | yes | — | lineup position of runner on second (src: chadwick_cwevent) |
| `RUN2_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on second reached base (src: chadwick_cwevent) |
| `RUN3_FLD_CD` | int16 | yes | — | defensive position of runner on third (src: chadwick_cwevent) |
| `RUN3_LINEUP_CD` | int16 | yes | — | lineup position of runner on third (src: chadwick_cwevent) |
| `RUN3_ORIGIN_EVENT_ID` | int16 | yes | — | event number on which runner on third reached base (src: chadwick_cwevent) |
| `RUN1_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on first (src: chadwick_cwevent) |
| `RUN2_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on second (src: chadwick_cwevent) |
| `RUN3_RESP_CAT_ID` | string | yes | — | Responsible catcher for runner on third (src: chadwick_cwevent) |
| `PA_BALL_CT` | int16 | yes | — | number of balls in plate appearance (src: chadwick_cwevent) |
| `PA_CALLED_BALL_CT` | int16 | yes | — | number of called balls in plate appearance (src: chadwick_cwevent) |
| `PA_INTENT_BALL_CT` | int16 | yes | — | number of intentional balls in plate appearance (src: chadwick_cwevent) |
| `PA_PITCHOUT_BALL_CT` | int16 | yes | — | number of pitchouts in plate appearance (src: chadwick_cwevent) |
| `PA_HITBATTER_BALL_CT` | int16 | yes | — | number of pitches hitting batter in plate appearance (src: chadwick_cwevent) |
| `PA_OTHER_BALL_CT` | int16 | yes | — | number of other balls in plate appearance (src: chadwick_cwevent) |
| `PA_STRIKE_CT` | int16 | yes | — | number of strikes in plate appearance (src: chadwick_cwevent) |
| `PA_CALLED_STRIKE_CT` | int16 | yes | — | number of called strikes in plate appearance (src: chadwick_cwevent) |
| `PA_SWINGMISS_STRIKE_CT` | int16 | yes | — | number of swinging strikes in plate appearance (src: chadwick_cwevent) |
| `PA_FOUL_STRIKE_CT` | int16 | yes | — | number of foul balls in plate appearance (src: chadwick_cwevent) |
| `PA_INPLAY_STRIKE_CT` | int16 | yes | — | number of balls in play in plate appearance (src: chadwick_cwevent) |
| `PA_OTHER_STRIKE_CT` | int16 | yes | — | number of other strikes in plate appearance (src: chadwick_cwevent) |
| `EVENT_RUNS_CT` | int16 | yes | — | number of runs on play (src: chadwick_cwevent) |
| `FLD_ID` | string | yes | — | id of player fielding batted ball (src: chadwick_cwevent) |
| `BASE2_FORCE_FL` | bool | yes | — | force play at second flag (src: chadwick_cwevent) |
| `BASE3_FORCE_FL` | bool | yes | — | force play at third flag (src: chadwick_cwevent) |
| `BASE4_FORCE_FL` | bool | yes | — | force play at home flag (src: chadwick_cwevent) |
| `BAT_SAFE_ERR_FL` | bool | yes | — | batter safe on error flag (src: chadwick_cwevent) |
| `BAT_FATE_ID` | int16 | yes | — | fate of batter (base ultimately advanced to) (src: chadwick_cwevent) |
| `RUN1_FATE_ID` | int16 | yes | — | fate of runner on first (src: chadwick_cwevent) |
| `RUN2_FATE_ID` | int16 | yes | — | fate of runner on second (src: chadwick_cwevent) |
| `RUN3_FATE_ID` | int16 | yes | — | fate of runner on third (src: chadwick_cwevent) |
| `FATE_RUNS_CT` | int16 | yes | — | runs scored in half inning after this event (src: chadwick_cwevent) |
| `ASS6_FLD_CD` | int16 | yes | — | fielder with sixth assist (src: chadwick_cwevent) |
| `ASS7_FLD_CD` | int16 | yes | — | fielder with seventh assist (src: chadwick_cwevent) |
| `ASS8_FLD_CD` | int16 | yes | — | fielder with eighth assist (src: chadwick_cwevent) |
| `ASS9_FLD_CD` | int16 | yes | — | fielder with ninth assist (src: chadwick_cwevent) |
| `ASS10_FLD_CD` | int16 | yes | — | fielder with tenth assist (src: chadwick_cwevent) |
| `UNKNOWN_OUT_EXC_FL` | bool | yes | — | unknown fielding credit flag (src: chadwick_cwevent) |
| `UNCERTAIN_PLAY_EXC_FL` | bool | yes | — | uncertain play flag (src: chadwick_cwevent) |
| `COUNT_TX` | string | yes | — | text of count as appears in event file (src: chadwick_cwevent) |
| `RUN1_AUTO_FL` | bool | yes | — | whether runner on first is an automatic runner (src: chadwick_cwevent) |
| `RUN2_AUTO_FL` | bool | yes | — | whether runner on second is an automatic runner (src: chadwick_cwevent) |
| `RUN3_AUTO_FL` | bool | yes | — | whether runner on third is an automatic runner (src: chadwick_cwevent) |
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
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
- **Key:** `year`, `roster`, `player_id`

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
| `roster` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

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
- **Key:** `GAME_ID`, `EVENT_ID`, `SUB_ID`, `SUB_FLD_CD`

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
| `rbi_qualifier` | string | yes | — | TODO |
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
| `attendance_qualifier` | string | yes | — | TODO |
| `temp` | int16 | yes | — | TODO |
| `winddir` | string | yes | — | TODO |
| `windspeed` | int16 | yes | — | TODO |
| `fieldcond` | string | yes | — | TODO |
| `precip` | string | yes | — | TODO |
| `sky` | string | yes | — | TODO |
| `timeofgame` | int16 | yes | — | TODO |
| `innings` | int16 | yes | — | TODO |
| `tiebreaker` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `wp` | string | yes | — | TODO |
| `lp` | string | yes | — | TODO |
| `save` | string | yes | — | TODO |
| `gwrbi` | string | yes | — | TODO |
| `oscorer` | string | yes | — | TODO |
| `scorer` | string | yes | — | TODO |
| `howscored` | string | yes | — | TODO |
| `pitches` | string | yes | — | TODO |
| `inputter` | string | yes | — | TODO |
| `inputtime` | string | yes | — | TODO |
| `inputprogvers` | string | yes | — | TODO |
| `edittime` | string | yes | — | TODO |
| `translator` | string | yes | — | TODO |
| `htbf` | bool | yes | — | TODO |
| `fieldcon` | string | yes | — | TODO |
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
- **Key:** `game_id`, `player_id`, `side`, `position`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `game_id` | string | yes | — | TODO |
| `player_id` | string | yes | — | TODO |
| `player_name` | string | yes | — | TODO |
| `side` | int8 | yes | — | TODO |
| `batting_order` | int8 | yes | — | TODO |
| `position` | int8 | yes | — | TODO |

<!-- END GENERATED:retrosheet.box_starters -->

<!-- BEGIN GENERATED:retrosheet.site_ballparks0 -->
### Dataset: site_ballparks0

Ballparks with first and last game dates (biodata.zip ballparks0.csv).

- **View:** `retrosheet_site_ballparks0`
- **Processed path:** `processed/retrosheet/site_ballparks0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `park_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `park_id` | string | yes | `site` | TODO |
| `name` | string | yes | — | TODO |
| `city` | string | yes | — | TODO |
| `state` | string | yes | — | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.site_ballparks0 -->

<!-- BEGIN GENERATED:retrosheet.site_coaches0 -->
### Dataset: site_coaches0

Coaches by year, team and role (biodata.zip coaches0.csv).

- **View:** `retrosheet_site_coaches0`
- **Processed path:** `processed/retrosheet/site_coaches0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `coach_id`, `year`, `team_id`, `role`, `first_g`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `coach_id` | string | yes | `id` | TODO |
| `year` | int16 | yes | — | TODO |
| `team_id` | string | yes | `team` | TODO |
| `role` | string | yes | — | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.site_coaches0 -->

<!-- BEGIN GENERATED:retrosheet.site_managers0 -->
### Dataset: site_managers0

Managers with first and last game dates (biodata.zip managers0.csv).

- **View:** `retrosheet_site_managers0`
- **Processed path:** `processed/retrosheet/site_managers0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `manager_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `manager_id` | string | yes | `id` | TODO |
| `last_name` | string | yes | `lastname` | TODO |
| `first_name` | string | yes | `firstname` | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.site_managers0 -->

<!-- BEGIN GENERATED:retrosheet.site_teams0 -->
### Dataset: site_teams0

Teams with first and last game dates (biodata.zip teams0.csv).

- **View:** `retrosheet_site_teams0`
- **Processed path:** `processed/retrosheet/site_teams0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `team_id`, `first_g`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | string | yes | `team` | TODO |
| `city` | string | yes | — | TODO |
| `nickname` | string | yes | — | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.site_teams0 -->

<!-- BEGIN GENERATED:retrosheet.site_transactions -->
### Dataset: site_transactions

Transactions database (trades, draft, free agency, injured list, ...), tranDB.zip.

- **View:** `retrosheet_site_transactions`
- **Processed path:** `processed/retrosheet/site_transactions/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `transaction_id`, `player`, `type`, `from_team`, `from_league`, `to_team`, `to_league`, `draft_type`, `draft_round`, `pick_number`, `info`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `primary_date` | string | yes | — | TODO |
| `time` | int16 | yes | — | TODO |
| `approximate` | string | yes | — | TODO |
| `secondary_date` | string | yes | — | TODO |
| `secondary_approximate` | string | yes | — | TODO |
| `transaction_id` | int32 | yes | — | TODO |
| `player` | string | yes | — | TODO |
| `type` | string | yes | — | TODO |
| `from_team` | string | yes | — | TODO |
| `from_league` | string | yes | — | TODO |
| `to_team` | string | yes | — | TODO |
| `to_league` | string | yes | — | TODO |
| `draft_type` | string | yes | — | TODO |
| `draft_round` | int16 | yes | — | TODO |
| `pick_number` | int16 | yes | — | TODO |
| `info` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.site_transactions -->

<!-- BEGIN GENERATED:retrosheet.site_umpires0 -->
### Dataset: site_umpires0

Umpires with first and last game dates (biodata.zip umpires0.csv).

- **View:** `retrosheet_site_umpires0`
- **Processed path:** `processed/retrosheet/site_umpires0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `umpire_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `umpire_id` | string | yes | `id` | TODO |
| `last_name` | string | yes | `lastname` | TODO |
| `first_name` | string | yes | `firstname` | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.site_umpires0 -->

<!-- BEGIN GENERATED:retrosheet.ballparks0 -->
### Dataset: ballparks0

Ballparks with first and last game dates (biodata.zip ballparks0.csv).

- **View:** `retrosheet_ballparks0`
- **Processed path:** `processed/retrosheet/ballparks0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `park_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `park_id` | string | yes | `site` | TODO |
| `name` | string | yes | — | TODO |
| `city` | string | yes | — | TODO |
| `state` | string | yes | — | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.ballparks0 -->

<!-- BEGIN GENERATED:retrosheet.coaches0 -->
### Dataset: coaches0

Coaches by year, team and role (biodata.zip coaches0.csv).

- **View:** `retrosheet_coaches0`
- **Processed path:** `processed/retrosheet/coaches0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `coach_id`, `year`, `team_id`, `role`, `first_g`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `coach_id` | string | yes | `id` | TODO |
| `year` | int16 | yes | — | TODO |
| `team_id` | string | yes | `team` | TODO |
| `role` | string | yes | — | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.coaches0 -->

<!-- BEGIN GENERATED:retrosheet.manager_logs -->
### Dataset: manager_logs

Team lines of every game a manager managed (mgrlogs.zip: <id>_mlog.csv).

- **View:** `retrosheet_manager_logs`
- **Processed path:** `processed/retrosheet/manager_logs/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `mgr`, `gid`, `team`, `stattype`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `inn1` | string | yes | — | TODO |
| `inn2` | string | yes | — | TODO |
| `inn3` | string | yes | — | TODO |
| `inn4` | string | yes | — | TODO |
| `inn5` | string | yes | — | TODO |
| `inn6` | string | yes | — | TODO |
| `inn7` | string | yes | — | TODO |
| `inn8` | string | yes | — | TODO |
| `inn9` | string | yes | — | TODO |
| `inn10` | string | yes | — | TODO |
| `inn11` | string | yes | — | TODO |
| `inn12` | string | yes | — | TODO |
| `inn13` | string | yes | — | TODO |
| `inn14` | string | yes | — | TODO |
| `inn15` | string | yes | — | TODO |
| `inn16` | string | yes | — | TODO |
| `inn17` | string | yes | — | TODO |
| `inn18` | string | yes | — | TODO |
| `inn19` | string | yes | — | TODO |
| `inn20` | string | yes | — | TODO |
| `inn21` | string | yes | — | TODO |
| `inn22` | string | yes | — | TODO |
| `inn23` | string | yes | — | TODO |
| `inn24` | string | yes | — | TODO |
| `inn25` | string | yes | — | TODO |
| `inn26` | string | yes | — | TODO |
| `inn27` | string | yes | — | TODO |
| `inn28` | string | yes | — | TODO |
| `lob` | int16 | yes | — | TODO |
| `mgr` | string | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `b_pa` | int16 | yes | — | TODO |
| `b_ab` | int16 | yes | — | TODO |
| `b_r` | int16 | yes | — | TODO |
| `b_h` | int16 | yes | — | TODO |
| `b_d` | int16 | yes | — | TODO |
| `b_t` | int16 | yes | — | TODO |
| `b_hr` | int16 | yes | — | TODO |
| `b_rbi` | int16 | yes | — | TODO |
| `b_sh` | int16 | yes | — | TODO |
| `b_sf` | int16 | yes | — | TODO |
| `b_hbp` | int16 | yes | — | TODO |
| `b_w` | int16 | yes | — | TODO |
| `b_iw` | int16 | yes | — | TODO |
| `b_k` | int16 | yes | — | TODO |
| `b_sb` | int16 | yes | — | TODO |
| `b_cs` | int16 | yes | — | TODO |
| `b_gdp` | int16 | yes | — | TODO |
| `b_xi` | int16 | yes | — | TODO |
| `b_roe` | int16 | yes | — | TODO |
| `p_ipouts` | int16 | yes | — | TODO |
| `p_noout` | int16 | yes | — | TODO |
| `p_bfp` | int16 | yes | — | TODO |
| `p_h` | int16 | yes | — | TODO |
| `p_d` | int16 | yes | — | TODO |
| `p_t` | int16 | yes | — | TODO |
| `p_hr` | int16 | yes | — | TODO |
| `p_r` | int16 | yes | — | TODO |
| `p_er` | int16 | yes | — | TODO |
| `p_w` | int16 | yes | — | TODO |
| `p_iw` | int16 | yes | — | TODO |
| `p_k` | int16 | yes | — | TODO |
| `p_hbp` | int16 | yes | — | TODO |
| `p_wp` | int16 | yes | — | TODO |
| `p_bk` | int16 | yes | — | TODO |
| `p_sh` | int16 | yes | — | TODO |
| `p_sf` | int16 | yes | — | TODO |
| `p_sb` | int16 | yes | — | TODO |
| `p_cs` | int16 | yes | — | TODO |
| `p_pb` | int16 | yes | — | TODO |
| `d_po` | int16 | yes | — | TODO |
| `d_a` | int16 | yes | — | TODO |
| `d_e` | int16 | yes | — | TODO |
| `d_dp` | int16 | yes | — | TODO |
| `d_tp` | int16 | yes | — | TODO |
| `d_pb` | int16 | yes | — | TODO |
| `d_wp` | int16 | yes | — | TODO |
| `d_sb` | int16 | yes | — | TODO |
| `d_cs` | int16 | yes | — | TODO |
| `start_l1` | string | yes | — | TODO |
| `start_l2` | string | yes | — | TODO |
| `start_l3` | string | yes | — | TODO |
| `start_l4` | string | yes | — | TODO |
| `start_l5` | string | yes | — | TODO |
| `start_l6` | string | yes | — | TODO |
| `start_l7` | string | yes | — | TODO |
| `start_l8` | string | yes | — | TODO |
| `start_l9` | string | yes | — | TODO |
| `start_f1` | string | yes | — | TODO |
| `start_f2` | string | yes | — | TODO |
| `start_f3` | string | yes | — | TODO |
| `start_f4` | string | yes | — | TODO |
| `start_f5` | string | yes | — | TODO |
| `start_f6` | string | yes | — | TODO |
| `start_f7` | string | yes | — | TODO |
| `start_f8` | string | yes | — | TODO |
| `start_f9` | string | yes | — | TODO |
| `start_f10` | string | yes | — | TODO |
| `date` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `eject` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.manager_logs -->

<!-- BEGIN GENERATED:retrosheet.managers0 -->
### Dataset: managers0

Managers with first and last game dates (biodata.zip managers0.csv).

- **View:** `retrosheet_managers0`
- **Processed path:** `processed/retrosheet/managers0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `manager_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `manager_id` | string | yes | `id` | TODO |
| `last_name` | string | yes | `lastname` | TODO |
| `first_name` | string | yes | `firstname` | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.managers0 -->

<!-- BEGIN GENERATED:retrosheet.player_batting_logs -->
### Dataset: player_batting_logs

Batting lines of every player game (playerlogs.zip, one file per player: <id>_b.csv).

- **View:** `retrosheet_player_batting_logs`
- **Processed path:** `processed/retrosheet/player_batting_logs/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `gid`, `team`, `stattype`, `b_lp`, `b_seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `id` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `b_lp` | int16 | yes | — | TODO |
| `b_seq` | int16 | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `b_pa` | int16 | yes | — | TODO |
| `b_ab` | int16 | yes | — | TODO |
| `b_r` | int16 | yes | — | TODO |
| `b_h` | int16 | yes | — | TODO |
| `b_d` | int16 | yes | — | TODO |
| `b_t` | int16 | yes | — | TODO |
| `b_hr` | int16 | yes | — | TODO |
| `b_rbi` | int16 | yes | — | TODO |
| `b_sh` | int16 | yes | — | TODO |
| `b_sf` | int16 | yes | — | TODO |
| `b_hbp` | int16 | yes | — | TODO |
| `b_w` | int16 | yes | — | TODO |
| `b_iw` | int16 | yes | — | TODO |
| `b_k` | int16 | yes | — | TODO |
| `b_sb` | int16 | yes | — | TODO |
| `b_cs` | int16 | yes | — | TODO |
| `b_gdp` | int16 | yes | — | TODO |
| `b_xi` | int16 | yes | — | TODO |
| `b_roe` | int16 | yes | — | TODO |
| `dh` | int16 | yes | — | TODO |
| `ph` | int16 | yes | — | TODO |
| `pr` | int16 | yes | — | TODO |
| `date` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `eject` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.player_batting_logs -->

<!-- BEGIN GENERATED:retrosheet.player_fielding_logs -->
### Dataset: player_fielding_logs

Fielding lines of every player game (playerlogs.zip: <id>_f.csv).

- **View:** `retrosheet_player_fielding_logs`
- **Processed path:** `processed/retrosheet/player_fielding_logs/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `gid`, `team`, `stattype`, `d_seq`, `d_pos`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `id` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `d_seq` | int16 | yes | — | TODO |
| `d_pos` | int16 | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `d_ifouts` | int16 | yes | — | TODO |
| `d_po` | int16 | yes | — | TODO |
| `d_a` | int16 | yes | — | TODO |
| `d_e` | int16 | yes | — | TODO |
| `d_dp` | int16 | yes | — | TODO |
| `d_tp` | int16 | yes | — | TODO |
| `d_pb` | int16 | yes | — | TODO |
| `d_wp` | int16 | yes | — | TODO |
| `d_sb` | int16 | yes | — | TODO |
| `d_cs` | int16 | yes | — | TODO |
| `d_gs` | int16 | yes | — | TODO |
| `date` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `eject` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.player_fielding_logs -->

<!-- BEGIN GENERATED:retrosheet.player_pitching_logs -->
### Dataset: player_pitching_logs

Pitching lines of every player game (playerlogs.zip: <id>_p.csv).

- **View:** `retrosheet_player_pitching_logs`
- **Processed path:** `processed/retrosheet/player_pitching_logs/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `gid`, `stattype`, `p_seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `id` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `p_seq` | int16 | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `p_ipouts` | int16 | yes | — | TODO |
| `p_noout` | int16 | yes | — | TODO |
| `p_bfp` | int16 | yes | — | TODO |
| `p_h` | int16 | yes | — | TODO |
| `p_d` | int16 | yes | — | TODO |
| `p_t` | int16 | yes | — | TODO |
| `p_hr` | int16 | yes | — | TODO |
| `p_r` | int16 | yes | — | TODO |
| `p_er` | int16 | yes | — | TODO |
| `p_w` | int16 | yes | — | TODO |
| `p_iw` | int16 | yes | — | TODO |
| `p_k` | int16 | yes | — | TODO |
| `p_hbp` | int16 | yes | — | TODO |
| `p_wp` | int16 | yes | — | TODO |
| `p_bk` | int16 | yes | — | TODO |
| `p_sh` | int16 | yes | — | TODO |
| `p_sf` | int16 | yes | — | TODO |
| `p_sb` | int16 | yes | — | TODO |
| `p_cs` | int16 | yes | — | TODO |
| `p_pb` | int16 | yes | — | TODO |
| `wp` | int16 | yes | — | TODO |
| `lp` | int16 | yes | — | TODO |
| `save` | int16 | yes | — | TODO |
| `p_gs` | int16 | yes | — | TODO |
| `p_gf` | int16 | yes | — | TODO |
| `p_cg` | int16 | yes | — | TODO |
| `date` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `eject` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.player_pitching_logs -->

<!-- BEGIN GENERATED:retrosheet.teams0 -->
### Dataset: teams0

Teams with first and last game dates (biodata.zip teams0.csv).

- **View:** `retrosheet_teams0`
- **Processed path:** `processed/retrosheet/teams0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `team_id`, `first_g`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team_id` | string | yes | `team` | TODO |
| `city` | string | yes | — | TODO |
| `nickname` | string | yes | — | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.teams0 -->

<!-- BEGIN GENERATED:retrosheet.transactions -->
### Dataset: transactions

Transactions database (trades, draft, free agency, injured list, ...), tranDB.zip.

- **View:** `retrosheet_transactions`
- **Processed path:** `processed/retrosheet/transactions/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `transaction_id`, `player`, `type`, `from_team`, `from_league`, `to_team`, `to_league`, `draft_type`, `draft_round`, `pick_number`, `info`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `primary_date` | string | yes | — | TODO |
| `time` | int16 | yes | — | TODO |
| `approximate` | string | yes | — | TODO |
| `secondary_date` | string | yes | — | TODO |
| `secondary_approximate` | string | yes | — | TODO |
| `transaction_id` | int32 | yes | — | TODO |
| `player` | string | yes | — | TODO |
| `type` | string | yes | — | TODO |
| `from_team` | string | yes | — | TODO |
| `from_league` | string | yes | — | TODO |
| `to_team` | string | yes | — | TODO |
| `to_league` | string | yes | — | TODO |
| `draft_type` | string | yes | — | TODO |
| `draft_round` | int16 | yes | — | TODO |
| `pick_number` | int16 | yes | — | TODO |
| `info` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.transactions -->

<!-- BEGIN GENERATED:retrosheet.umpire_logs -->
### Dataset: umpire_logs

Game info and ejections of every game an umpire worked (umplogs.zip: <id>_ulog.csv).

- **View:** `retrosheet_umpire_logs`
- **Processed path:** `processed/retrosheet/umpire_logs/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `umpire_id`, `gid`, `gs`, `inn`, `pos`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `visteam` | string | yes | — | TODO |
| `hometeam` | string | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `date` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `gs` | int16 | yes | — | TODO |
| `inn` | int16 | yes | — | TODO |
| `pos` | string | yes | — | TODO |
| `starttime` | string | yes | — | TODO |
| `daynight` | string | yes | — | TODO |
| `innings` | int16 | yes | — | TODO |
| `tiebreaker` | int16 | yes | — | TODO |
| `usedh` | string | yes | — | TODO |
| `htbf` | string | yes | — | TODO |
| `timeofgame` | int16 | yes | — | TODO |
| `attendance` | int32 | yes | — | TODO |
| `fieldcond` | string | yes | — | TODO |
| `precip` | string | yes | — | TODO |
| `sky` | string | yes | — | TODO |
| `temp` | int16 | yes | — | TODO |
| `winddir` | string | yes | — | TODO |
| `windspeed` | int16 | yes | — | TODO |
| `oscorer` | string | yes | — | TODO |
| `forfeit` | string | yes | — | TODO |
| `suspend` | int32 | yes | — | TODO |
| `umphome` | string | yes | — | TODO |
| `ump1b` | string | yes | — | TODO |
| `ump2b` | string | yes | — | TODO |
| `ump3b` | string | yes | — | TODO |
| `umplf` | string | yes | — | TODO |
| `umprf` | string | yes | — | TODO |
| `wp` | string | yes | — | TODO |
| `lp` | string | yes | — | TODO |
| `save` | string | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `vruns` | int16 | yes | — | TODO |
| `hruns` | int16 | yes | — | TODO |
| `wteam` | string | yes | — | TODO |
| `lteam` | string | yes | — | TODO |
| `line` | string | yes | — | TODO |
| `batteries` | string | yes | — | TODO |
| `lineups` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `season` | int16 | yes | — | TODO |
| `uid` | string | yes | — | TODO |
| `eject` | int16 | yes | — | TODO |
| `umpire_id` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.umpire_logs -->

<!-- BEGIN GENERATED:retrosheet.umpires0 -->
### Dataset: umpires0

Umpires with first and last game dates (biodata.zip umpires0.csv).

- **View:** `retrosheet_umpires0`
- **Processed path:** `processed/retrosheet/umpires0/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `umpire_id`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `umpire_id` | string | yes | `id` | TODO |
| `last_name` | string | yes | `lastname` | TODO |
| `first_name` | string | yes | `firstname` | TODO |
| `first_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `last_g` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.umpires0 -->

<!-- BEGIN GENERATED:retrosheet.negro_batting -->
### Dataset: negro_batting

Negro Leagues batting lines per player game (negroleagues.zip batting.csv).

- **View:** `retrosheet_negro_batting`
- **Processed path:** `processed/retrosheet/negro_batting/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `gid`, `team`, `stattype`, `b_lp`, `b_seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `id` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `b_lp` | int16 | yes | — | TODO |
| `b_seq` | int16 | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `b_pa` | int16 | yes | — | TODO |
| `b_ab` | int16 | yes | — | TODO |
| `b_r` | int16 | yes | — | TODO |
| `b_h` | int16 | yes | — | TODO |
| `b_d` | int16 | yes | — | TODO |
| `b_t` | int16 | yes | — | TODO |
| `b_hr` | int16 | yes | — | TODO |
| `b_rbi` | int16 | yes | — | TODO |
| `b_sh` | int16 | yes | — | TODO |
| `b_sf` | int16 | yes | — | TODO |
| `b_hbp` | int16 | yes | — | TODO |
| `b_w` | int16 | yes | — | TODO |
| `b_iw` | int16 | yes | — | TODO |
| `b_k` | int16 | yes | — | TODO |
| `b_sb` | int16 | yes | — | TODO |
| `b_cs` | int16 | yes | — | TODO |
| `b_gdp` | int16 | yes | — | TODO |
| `b_xi` | int16 | yes | — | TODO |
| `b_roe` | int16 | yes | — | TODO |
| `dh` | int16 | yes | — | TODO |
| `ph` | int16 | yes | — | TODO |
| `pr` | int16 | yes | — | TODO |
| `date` | int32 | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_batting -->

<!-- BEGIN GENERATED:retrosheet.negro_fielding -->
### Dataset: negro_fielding

Negro Leagues fielding lines per player game (negroleagues.zip fielding.csv).

- **View:** `retrosheet_negro_fielding`
- **Processed path:** `processed/retrosheet/negro_fielding/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `gid`, `team`, `stattype`, `d_seq`, `d_pos`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `id` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `d_seq` | int16 | yes | — | TODO |
| `d_pos` | string | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `d_ifouts` | int16 | yes | — | TODO |
| `d_po` | int16 | yes | — | TODO |
| `d_a` | int16 | yes | — | TODO |
| `d_e` | int16 | yes | — | TODO |
| `d_dp` | int16 | yes | — | TODO |
| `d_tp` | int16 | yes | — | TODO |
| `d_pb` | int16 | yes | — | TODO |
| `d_wp` | int16 | yes | — | TODO |
| `d_sb` | int16 | yes | — | TODO |
| `d_cs` | int16 | yes | — | TODO |
| `d_gs` | int16 | yes | — | TODO |
| `date` | int32 | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_fielding -->

<!-- BEGIN GENERATED:retrosheet.negro_games -->
### Dataset: negro_games

Negro Leagues game information, one row per game (negroleagues.zip gameinfo.csv).

- **View:** `retrosheet_negro_games`
- **Processed path:** `processed/retrosheet/negro_games/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `gid`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `visteam` | string | yes | — | TODO |
| `hometeam` | string | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `date` | date32[day] (`%Y%m%d`) | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `starttime` | string | yes | — | TODO |
| `daynight` | string | yes | — | TODO |
| `innings` | int16 | yes | — | TODO |
| `tiebreaker` | string | yes | — | TODO |
| `usedh` | string | yes | — | TODO |
| `htbf` | string | yes | — | TODO |
| `timeofgame` | int16 | yes | — | TODO |
| `attendance` | string | yes | — | TODO |
| `fieldcond` | string | yes | — | TODO |
| `precip` | string | yes | — | TODO |
| `sky` | string | yes | — | TODO |
| `temp` | string | yes | — | TODO |
| `winddir` | string | yes | — | TODO |
| `windspeed` | int16 | yes | — | TODO |
| `oscorer` | string | yes | — | TODO |
| `forfeit` | string | yes | — | TODO |
| `suspend` | int32 | yes | — | TODO |
| `umphome` | string | yes | — | TODO |
| `ump1b` | string | yes | — | TODO |
| `ump2b` | string | yes | — | TODO |
| `ump3b` | string | yes | — | TODO |
| `umplf` | string | yes | — | TODO |
| `umprf` | string | yes | — | TODO |
| `wp` | string | yes | — | TODO |
| `lp` | string | yes | — | TODO |
| `save` | string | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `vruns` | int16 | yes | — | TODO |
| `hruns` | int16 | yes | — | TODO |
| `wteam` | string | yes | — | TODO |
| `lteam` | string | yes | — | TODO |
| `line` | string | yes | — | TODO |
| `batteries` | string | yes | — | TODO |
| `lineups` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `season` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_games -->

<!-- BEGIN GENERATED:retrosheet.negro_pitching -->
### Dataset: negro_pitching

Negro Leagues pitching lines per player game (negroleagues.zip pitching.csv).

- **View:** `retrosheet_negro_pitching`
- **Processed path:** `processed/retrosheet/negro_pitching/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `gid`, `team`, `stattype`, `p_seq`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `id` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `p_seq` | int16 | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `p_ipouts` | int16 | yes | — | TODO |
| `p_noout` | int16 | yes | — | TODO |
| `p_bfp` | int16 | yes | — | TODO |
| `p_h` | int16 | yes | — | TODO |
| `p_d` | int16 | yes | — | TODO |
| `p_t` | int16 | yes | — | TODO |
| `p_hr` | int16 | yes | — | TODO |
| `p_r` | int16 | yes | — | TODO |
| `p_er` | int16 | yes | — | TODO |
| `p_w` | int16 | yes | — | TODO |
| `p_iw` | int16 | yes | — | TODO |
| `p_k` | int16 | yes | — | TODO |
| `p_hbp` | int16 | yes | — | TODO |
| `p_wp` | int16 | yes | — | TODO |
| `p_bk` | int16 | yes | — | TODO |
| `p_sh` | int16 | yes | — | TODO |
| `p_sf` | int16 | yes | — | TODO |
| `p_sb` | int16 | yes | — | TODO |
| `p_cs` | int16 | yes | — | TODO |
| `p_pb` | int16 | yes | — | TODO |
| `wp` | int16 | yes | — | TODO |
| `lp` | int16 | yes | — | TODO |
| `save` | int16 | yes | — | TODO |
| `p_gs` | int16 | yes | — | TODO |
| `p_gf` | int16 | yes | — | TODO |
| `p_cg` | int16 | yes | — | TODO |
| `date` | int32 | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_pitching -->

<!-- BEGIN GENERATED:retrosheet.negro_players -->
### Dataset: negro_players

Negro Leagues players with games by position per team (negroleagues.zip allplayers.csv).

- **View:** `retrosheet_negro_players`
- **Processed path:** `processed/retrosheet/negro_players/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `id`, `team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `id` | string | yes | — | TODO |
| `last_name` | string | yes | `last` | TODO |
| `first_name` | string | yes | `first` | TODO |
| `bat` | string | yes | — | TODO |
| `throw` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `g` | int16 | yes | — | TODO |
| `g_p` | int16 | yes | — | TODO |
| `g_sp` | int16 | yes | — | TODO |
| `g_rp` | int16 | yes | — | TODO |
| `g_c` | int16 | yes | — | TODO |
| `g_1b` | int16 | yes | — | TODO |
| `g_2b` | int16 | yes | — | TODO |
| `g_3b` | int16 | yes | — | TODO |
| `g_ss` | int16 | yes | — | TODO |
| `g_lf` | int16 | yes | — | TODO |
| `g_cf` | int16 | yes | — | TODO |
| `g_rf` | int16 | yes | — | TODO |
| `g_of` | int16 | yes | — | TODO |
| `g_dh` | int16 | yes | — | TODO |
| `g_ph` | int16 | yes | — | TODO |
| `g_pr` | int16 | yes | — | TODO |
| `first_g` | int32 | yes | — | TODO |
| `last_g` | int32 | yes | — | TODO |
| `season` | int16 | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_players -->

<!-- BEGIN GENERATED:retrosheet.negro_plays -->
### Dataset: negro_plays

Negro Leagues play-by-play, one row per play (negroleagues.zip plays.csv).

- **View:** `retrosheet_negro_plays`
- **Processed path:** `processed/retrosheet/negro_plays/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `gid`, `pn`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `event` | string | yes | — | TODO |
| `inning` | int16 | yes | — | TODO |
| `top_bot` | int16 | yes | — | TODO |
| `vis_home` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `batteam` | string | yes | — | TODO |
| `pitteam` | string | yes | — | TODO |
| `score_v` | int16 | yes | — | TODO |
| `score_h` | int16 | yes | — | TODO |
| `batter` | string | yes | — | TODO |
| `pitcher` | string | yes | — | TODO |
| `lp` | int16 | yes | — | TODO |
| `bat_f` | int16 | yes | — | TODO |
| `bathand` | string | yes | — | TODO |
| `pithand` | string | yes | — | TODO |
| `balls` | string | yes | — | TODO |
| `strikes` | string | yes | — | TODO |
| `count` | string | yes | — | TODO |
| `pitches` | string | yes | — | TODO |
| `nump` | int16 | yes | — | TODO |
| `pa` | int16 | yes | — | TODO |
| `ab` | int16 | yes | — | TODO |
| `single` | int16 | yes | — | TODO |
| `double` | int16 | yes | — | TODO |
| `triple` | int16 | yes | — | TODO |
| `hr` | int16 | yes | — | TODO |
| `sh` | int16 | yes | — | TODO |
| `sf` | int16 | yes | — | TODO |
| `hbp` | int16 | yes | — | TODO |
| `walk` | int16 | yes | — | TODO |
| `k` | int16 | yes | — | TODO |
| `xi` | int16 | yes | — | TODO |
| `roe` | int16 | yes | — | TODO |
| `fc` | int16 | yes | — | TODO |
| `othout` | int16 | yes | — | TODO |
| `noout` | int16 | yes | — | TODO |
| `oth` | int16 | yes | — | TODO |
| `bip` | int16 | yes | — | TODO |
| `bunt` | int16 | yes | — | TODO |
| `ground` | int16 | yes | — | TODO |
| `fly` | int16 | yes | — | TODO |
| `line` | int16 | yes | — | TODO |
| `iw` | int16 | yes | — | TODO |
| `gdp` | int16 | yes | — | TODO |
| `othdp` | int16 | yes | — | TODO |
| `tp` | int16 | yes | — | TODO |
| `fle` | int16 | yes | — | TODO |
| `wp` | int16 | yes | — | TODO |
| `pb` | int16 | yes | — | TODO |
| `bk` | int16 | yes | — | TODO |
| `oa` | int16 | yes | — | TODO |
| `di` | int16 | yes | — | TODO |
| `sb2` | int16 | yes | — | TODO |
| `sb3` | int16 | yes | — | TODO |
| `sbh` | int16 | yes | — | TODO |
| `cs2` | int16 | yes | — | TODO |
| `cs3` | int16 | yes | — | TODO |
| `csh` | int16 | yes | — | TODO |
| `pko1` | int16 | yes | — | TODO |
| `pko2` | int16 | yes | — | TODO |
| `pko3` | int16 | yes | — | TODO |
| `k_safe` | int16 | yes | — | TODO |
| `e1` | int16 | yes | — | TODO |
| `e2` | int16 | yes | — | TODO |
| `e3` | int16 | yes | — | TODO |
| `e4` | int16 | yes | — | TODO |
| `e5` | int16 | yes | — | TODO |
| `e6` | int16 | yes | — | TODO |
| `e7` | int16 | yes | — | TODO |
| `e8` | int16 | yes | — | TODO |
| `e9` | int16 | yes | — | TODO |
| `outs_pre` | int16 | yes | — | TODO |
| `outs_post` | int16 | yes | — | TODO |
| `br1_pre` | string | yes | — | TODO |
| `br2_pre` | string | yes | — | TODO |
| `br3_pre` | string | yes | — | TODO |
| `br1_post` | string | yes | — | TODO |
| `br2_post` | string | yes | — | TODO |
| `br3_post` | string | yes | — | TODO |
| `lob_id1` | string | yes | — | TODO |
| `lob_id2` | string | yes | — | TODO |
| `lob_id3` | string | yes | — | TODO |
| `pr1_pre` | string | yes | — | TODO |
| `pr2_pre` | string | yes | — | TODO |
| `pr3_pre` | string | yes | — | TODO |
| `pr1_post` | string | yes | — | TODO |
| `pr2_post` | string | yes | — | TODO |
| `pr3_post` | string | yes | — | TODO |
| `run_b` | string | yes | — | TODO |
| `run1` | string | yes | — | TODO |
| `run2` | string | yes | — | TODO |
| `run3` | string | yes | — | TODO |
| `prun_b` | string | yes | — | TODO |
| `prun1` | string | yes | — | TODO |
| `prun2` | string | yes | — | TODO |
| `prun3` | string | yes | — | TODO |
| `ur_b` | int16 | yes | — | TODO |
| `ur1` | int16 | yes | — | TODO |
| `ur2` | int16 | yes | — | TODO |
| `ur3` | int16 | yes | — | TODO |
| `rbi_b` | int16 | yes | — | TODO |
| `rbi1` | int16 | yes | — | TODO |
| `rbi2` | int16 | yes | — | TODO |
| `rbi3` | int16 | yes | — | TODO |
| `runs` | int16 | yes | — | TODO |
| `rbi` | int16 | yes | — | TODO |
| `er` | int16 | yes | — | TODO |
| `tur` | int16 | yes | — | TODO |
| `l1` | string | yes | — | TODO |
| `l2` | string | yes | — | TODO |
| `l3` | string | yes | — | TODO |
| `l4` | string | yes | — | TODO |
| `l5` | string | yes | — | TODO |
| `l6` | string | yes | — | TODO |
| `l7` | string | yes | — | TODO |
| `l8` | string | yes | — | TODO |
| `l9` | string | yes | — | TODO |
| `lf1` | int16 | yes | — | TODO |
| `lf2` | int16 | yes | — | TODO |
| `lf3` | int16 | yes | — | TODO |
| `lf4` | int16 | yes | — | TODO |
| `lf5` | int16 | yes | — | TODO |
| `lf6` | int16 | yes | — | TODO |
| `lf7` | int16 | yes | — | TODO |
| `lf8` | int16 | yes | — | TODO |
| `lf9` | int16 | yes | — | TODO |
| `f2` | string | yes | — | TODO |
| `f3` | string | yes | — | TODO |
| `f4` | string | yes | — | TODO |
| `f5` | string | yes | — | TODO |
| `f6` | string | yes | — | TODO |
| `f7` | string | yes | — | TODO |
| `f8` | string | yes | — | TODO |
| `f9` | string | yes | — | TODO |
| `po0` | int16 | yes | — | TODO |
| `po1` | int16 | yes | — | TODO |
| `po2` | int16 | yes | — | TODO |
| `po3` | int16 | yes | — | TODO |
| `po4` | int16 | yes | — | TODO |
| `po5` | int16 | yes | — | TODO |
| `po6` | int16 | yes | — | TODO |
| `po7` | int16 | yes | — | TODO |
| `po8` | int16 | yes | — | TODO |
| `po9` | int16 | yes | — | TODO |
| `a1` | int16 | yes | — | TODO |
| `a2` | int16 | yes | — | TODO |
| `a3` | int16 | yes | — | TODO |
| `a4` | int16 | yes | — | TODO |
| `a5` | int16 | yes | — | TODO |
| `a6` | int16 | yes | — | TODO |
| `a7` | int16 | yes | — | TODO |
| `a8` | int16 | yes | — | TODO |
| `a9` | int16 | yes | — | TODO |
| `fseq` | int32 | yes | — | TODO |
| `batout1` | int16 | yes | — | TODO |
| `batout2` | int16 | yes | — | TODO |
| `batout3` | int16 | yes | — | TODO |
| `brout_b` | int16 | yes | — | TODO |
| `brout1` | int16 | yes | — | TODO |
| `brout2` | int16 | yes | — | TODO |
| `brout3` | int16 | yes | — | TODO |
| `firstf` | int16 | yes | — | TODO |
| `loc` | string | yes | — | TODO |
| `hittype` | string | yes | — | TODO |
| `dpopp` | int16 | yes | — | TODO |
| `pivot` | int16 | yes | — | TODO |
| `pn` | int16 | yes | — | TODO |
| `umphome` | string | yes | — | TODO |
| `ump1b` | string | yes | — | TODO |
| `ump2b` | string | yes | — | TODO |
| `ump3b` | string | yes | — | TODO |
| `umplf` | string | yes | — | TODO |
| `umprf` | string | yes | — | TODO |
| `date` | int32 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_plays -->

<!-- BEGIN GENERATED:retrosheet.negro_team_stats -->
### Dataset: negro_team_stats

Negro Leagues team game lines with line scores (negroleagues.zip teamstats.csv).

- **View:** `retrosheet_negro_team_stats`
- **Processed path:** `processed/retrosheet/negro_team_stats/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `gid`, `team`, `stattype`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `gid` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `inn1` | string | yes | — | TODO |
| `inn2` | string | yes | — | TODO |
| `inn3` | string | yes | — | TODO |
| `inn4` | string | yes | — | TODO |
| `inn5` | string | yes | — | TODO |
| `inn6` | string | yes | — | TODO |
| `inn7` | string | yes | — | TODO |
| `inn8` | string | yes | — | TODO |
| `inn9` | string | yes | — | TODO |
| `inn10` | string | yes | — | TODO |
| `inn11` | string | yes | — | TODO |
| `inn12` | string | yes | — | TODO |
| `inn13` | string | yes | — | TODO |
| `inn14` | string | yes | — | TODO |
| `inn15` | string | yes | — | TODO |
| `inn16` | string | yes | — | TODO |
| `inn17` | string | yes | — | TODO |
| `inn18` | string | yes | — | TODO |
| `inn19` | string | yes | — | TODO |
| `inn20` | string | yes | — | TODO |
| `inn21` | string | yes | — | TODO |
| `inn22` | string | yes | — | TODO |
| `inn23` | string | yes | — | TODO |
| `inn24` | string | yes | — | TODO |
| `inn25` | string | yes | — | TODO |
| `inn26` | string | yes | — | TODO |
| `inn27` | string | yes | — | TODO |
| `inn28` | string | yes | — | TODO |
| `lob` | int16 | yes | — | TODO |
| `mgr` | string | yes | — | TODO |
| `stattype` | string | yes | — | TODO |
| `b_pa` | int16 | yes | — | TODO |
| `b_ab` | int16 | yes | — | TODO |
| `b_r` | int16 | yes | — | TODO |
| `b_h` | int16 | yes | — | TODO |
| `b_d` | int16 | yes | — | TODO |
| `b_t` | int16 | yes | — | TODO |
| `b_hr` | int16 | yes | — | TODO |
| `b_rbi` | int16 | yes | — | TODO |
| `b_sh` | int16 | yes | — | TODO |
| `b_sf` | int16 | yes | — | TODO |
| `b_hbp` | int16 | yes | — | TODO |
| `b_w` | string | yes | — | TODO |
| `b_iw` | int16 | yes | — | TODO |
| `b_k` | string | yes | — | TODO |
| `b_sb` | int16 | yes | — | TODO |
| `b_cs` | int16 | yes | — | TODO |
| `b_gdp` | int16 | yes | — | TODO |
| `b_xi` | int16 | yes | — | TODO |
| `b_roe` | int16 | yes | — | TODO |
| `p_ipouts` | int16 | yes | — | TODO |
| `p_noout` | int16 | yes | — | TODO |
| `p_bfp` | int16 | yes | — | TODO |
| `p_h` | int16 | yes | — | TODO |
| `p_d` | int16 | yes | — | TODO |
| `p_t` | int16 | yes | — | TODO |
| `p_hr` | int16 | yes | — | TODO |
| `p_r` | int16 | yes | — | TODO |
| `p_er` | int16 | yes | — | TODO |
| `p_w` | string | yes | — | TODO |
| `p_iw` | int16 | yes | — | TODO |
| `p_k` | string | yes | — | TODO |
| `p_hbp` | int16 | yes | — | TODO |
| `p_wp` | int16 | yes | — | TODO |
| `p_bk` | int16 | yes | — | TODO |
| `p_sh` | int16 | yes | — | TODO |
| `p_sf` | int16 | yes | — | TODO |
| `p_sb` | int16 | yes | — | TODO |
| `p_cs` | int16 | yes | — | TODO |
| `p_pb` | int16 | yes | — | TODO |
| `d_po` | int16 | yes | — | TODO |
| `d_a` | int16 | yes | — | TODO |
| `d_e` | int16 | yes | — | TODO |
| `d_dp` | int16 | yes | — | TODO |
| `d_tp` | int16 | yes | — | TODO |
| `d_pb` | int16 | yes | — | TODO |
| `d_wp` | int16 | yes | — | TODO |
| `d_sb` | int16 | yes | — | TODO |
| `d_cs` | int16 | yes | — | TODO |
| `start_l1` | string | yes | — | TODO |
| `start_l2` | string | yes | — | TODO |
| `start_l3` | string | yes | — | TODO |
| `start_l4` | string | yes | — | TODO |
| `start_l5` | string | yes | — | TODO |
| `start_l6` | string | yes | — | TODO |
| `start_l7` | string | yes | — | TODO |
| `start_l8` | string | yes | — | TODO |
| `start_l9` | string | yes | — | TODO |
| `start_f1` | string | yes | — | TODO |
| `start_f2` | string | yes | — | TODO |
| `start_f3` | string | yes | — | TODO |
| `start_f4` | string | yes | — | TODO |
| `start_f5` | string | yes | — | TODO |
| `start_f6` | string | yes | — | TODO |
| `start_f7` | string | yes | — | TODO |
| `start_f8` | string | yes | — | TODO |
| `start_f9` | string | yes | — | TODO |
| `start_f10` | string | yes | — | TODO |
| `date` | int32 | yes | — | TODO |
| `number` | int16 | yes | — | TODO |
| `site` | string | yes | — | TODO |
| `vishome` | string | yes | — | TODO |
| `opp` | string | yes | — | TODO |
| `win` | int16 | yes | — | TODO |
| `loss` | int16 | yes | — | TODO |
| `tie` | int16 | yes | — | TODO |
| `gametype` | string | yes | — | TODO |
| `box` | string | yes | — | TODO |
| `pbp` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:retrosheet.negro_team_stats -->
