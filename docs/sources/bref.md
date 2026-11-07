# Baseball-Reference WAR Endpoint & Schema Catalog

## Upstream Overview
- **Provider:** Baseball-Reference (Sports Reference). It publishes its WAR tables as plain download files linked from its About page. These two files are the only thing baseballpy asks for; no page is scraped (see `docs/DATA_LICENSES.md`).
- **Rules that shaped this source** (read 2026-11-06 on `sports-reference.com/bot-traffic.html` and `/data_use.html`): more than 20 requests a minute puts a session "in jail for up to a day"; "please do not attempt to aggressively spider data from our web sites"; do not create websites or tools based on scraped data; do not use the data to train generative AI without permission. Facts cannot be copyrighted. baseballpy ships code, never data.
- **Files** (base `https://www.baseball-reference.com`)
  | Dataset | Path | Size when probed | Rows |
  | --- | --- | --- | --- |
  | `war_batting` | `/data/war_daily_bat.txt` | 35.6 MB | 126,547 (1871 to 2026) |
  | `war_pitching` | `/data/war_daily_pitch.txt` | 15.4 MB | 57,884 (1871 to 2026) |
- **Request budget:** two requests per ingest, and none when a file was downloaded in the last 12 hours (it is read from `raw/`). The host is capped at 6 requests a minute (`BASEBALLPY_RATE_BREF_RPS`, default 0.1) with one request in flight, and a refusal is never retried (`host_max_attempts`): a second request after a block only lengthens it. A refusal (HTTP error) or a web page instead of the file stops the run with a message to wait 24 hours.
- **Daily archive (not ingested yet):** `/data/` also lists `war_archive-YYYY-MM-DD.zip`, one file per day (the page lists them back to 2018). They would give WAR *as it was on each day* (Baseball-Reference revises past seasons), which a backtest needs; the files here are a snapshot of today. Recorded as a later opt-in.
- **Storage:** raw files at `raw/bref/<dataset>/war_daily_<bat|pitch>.txt.gz` (gzip, sha256 of the original bytes and the download time in the manifest); typed Parquet at `processed/bref/<dataset>/season=YYYY/part-<year>.parquet`, one chunk per season.

## Datasets
| Dataset | View | Upstream file | Key |
| --- | --- | --- | --- |
| `war_batting` | `bref_war_batting` | `war_daily_bat.txt` | `player_ID`, `year_ID`, `stint_ID` |
| `war_pitching` | `bref_war_pitching` | `war_daily_pitch.txt` | `player_ID`, `year_ID`, `stint_ID` |

## Schema notes (verified against the real data)
- Schemas are **generated from the whole files** (`scripts/gen_bref_schemas.py`): each header gets the narrowest exact type that holds every value; types never come from column names. Column names are the file's own headers (`WAR`, `runs_bat`, `mlb_ID`); the glossary of their meaning is Baseball-Reference's "WAR Download Glossary".
- The files write a missing value as `NULL` (24 of 49 batting columns and 19 of 43 pitching columns have some); it becomes SQL NULL. `NA` is a real league code (`lg_ID`), not a missing value. WAR, runs and rates are exact `decimal` columns (`WAR` is `decimal(9,2)`).
- A header the generator has not seen goes to `_extras` with a one-time `schema_drift` warning; rerun the generator to type it.
- `player_ID` is Baseball-Reference's id (`judgeaa01`); `mlb_ID` is the MLBAM id and joins to `statcast` and `mlb_api`; the Chadwick register maps the others.

## Dataset reference (generated)

<!-- BEGIN GENERATED:bref.description_sources -->
### Description sources

No column descriptions have been written for this source yet.

<!-- END GENERATED:bref.description_sources -->

<!-- BEGIN GENERATED:bref.war_batting -->
### Dataset: war_batting

Baseball-Reference WAR, batting side: one row per player, season and stint.

- **View:** `bref_war_batting`
- **Processed path:** `processed/bref/war_batting/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_ID`, `year_ID`, `stint_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name_common` | string | yes | — | TODO |
| `age` | int32 | yes | — | TODO |
| `mlb_ID` | int32 | yes | — | TODO |
| `player_ID` | string | yes | — | TODO |
| `year_ID` | int32 | yes | — | TODO |
| `team_ID` | string | yes | — | TODO |
| `stint_ID` | int32 | yes | — | TODO |
| `lg_ID` | string | yes | — | TODO |
| `PA` | int32 | yes | — | TODO |
| `G` | int32 | yes | — | TODO |
| `Inn` | decimal128(9, 1) | yes | — | TODO |
| `runs_bat` | decimal128(9, 2) | yes | — | TODO |
| `runs_br` | decimal128(9, 2) | yes | — | TODO |
| `runs_dp` | decimal128(9, 2) | yes | — | TODO |
| `runs_field` | decimal128(9, 2) | yes | — | TODO |
| `runs_infield` | decimal128(9, 2) | yes | — | TODO |
| `runs_outfield` | decimal128(9, 2) | yes | — | TODO |
| `runs_catcher` | decimal128(9, 2) | yes | — | TODO |
| `runs_good_plays` | decimal128(9, 2) | yes | — | TODO |
| `runs_defense` | decimal128(9, 2) | yes | — | TODO |
| `runs_position` | decimal128(9, 2) | yes | — | TODO |
| `runs_position_p` | decimal128(9, 2) | yes | — | TODO |
| `runs_replacement` | decimal128(9, 2) | yes | — | TODO |
| `runs_above_rep` | decimal128(9, 1) | yes | — | TODO |
| `runs_above_avg` | decimal128(9, 1) | yes | — | TODO |
| `runs_above_avg_off` | decimal128(9, 1) | yes | — | TODO |
| `runs_above_avg_def` | decimal128(9, 1) | yes | — | TODO |
| `WAA` | decimal128(9, 2) | yes | — | TODO |
| `WAA_off` | decimal128(9, 2) | yes | — | TODO |
| `WAA_def` | decimal128(9, 2) | yes | — | TODO |
| `WAR` | decimal128(9, 2) | yes | — | TODO |
| `WAR_def` | decimal128(9, 2) | yes | — | TODO |
| `WAR_off` | decimal128(9, 2) | yes | — | TODO |
| `WAR_rep` | decimal128(9, 2) | yes | — | TODO |
| `salary` | int32 | yes | — | TODO |
| `pitcher` | string | yes | — | TODO |
| `teamRpG` | decimal128(18, 5) | yes | — | TODO |
| `oppRpG` | decimal128(18, 5) | yes | — | TODO |
| `oppRpPA_rep` | decimal128(18, 5) | yes | — | TODO |
| `oppRpG_rep` | decimal128(18, 5) | yes | — | TODO |
| `pyth_exponent` | decimal128(9, 3) | yes | — | TODO |
| `pyth_exponent_rep` | decimal128(9, 3) | yes | — | TODO |
| `waa_win_perc` | decimal128(9, 4) | yes | — | TODO |
| `waa_win_perc_off` | decimal128(9, 4) | yes | — | TODO |
| `waa_win_perc_def` | decimal128(9, 4) | yes | — | TODO |
| `waa_win_perc_rep` | decimal128(9, 4) | yes | — | TODO |
| `OPS_plus` | decimal128(18, 10) | yes | — | TODO |
| `TOB_lg` | decimal128(18, 3) | yes | — | TODO |
| `TB_lg` | decimal128(18, 3) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:bref.war_batting -->

<!-- BEGIN GENERATED:bref.war_pitching -->
### Dataset: war_pitching

Baseball-Reference WAR, pitching side: one row per player, season and stint.

- **View:** `bref_war_pitching`
- **Processed path:** `processed/bref/war_pitching/season=YYYY/part-<chunk>.parquet`
- **Partitioning:** Hive `season=YYYY`
- **Key:** `player_ID`, `year_ID`, `stint_ID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name_common` | string | yes | — | TODO |
| `age` | int32 | yes | — | TODO |
| `mlb_ID` | int32 | yes | — | TODO |
| `player_ID` | string | yes | — | TODO |
| `year_ID` | int32 | yes | — | TODO |
| `team_ID` | string | yes | — | TODO |
| `stint_ID` | int32 | yes | — | TODO |
| `lg_ID` | string | yes | — | TODO |
| `G` | int32 | yes | — | TODO |
| `GS` | int32 | yes | — | TODO |
| `IPouts` | int32 | yes | — | TODO |
| `IPouts_start` | int32 | yes | — | TODO |
| `IPouts_relief` | int32 | yes | — | TODO |
| `RA` | int32 | yes | — | TODO |
| `xRA` | decimal128(18, 3) | yes | — | TODO |
| `xRA_sprp_adj` | decimal128(9, 3) | yes | — | TODO |
| `xRA_extras_adj` | decimal128(9, 3) | yes | — | TODO |
| `xRA_def_pitcher` | decimal128(9, 3) | yes | — | TODO |
| `PPF` | int32 | yes | — | TODO |
| `PPF_custom` | decimal128(18, 3) | yes | — | TODO |
| `xRA_final` | decimal128(18, 3) | yes | — | TODO |
| `BIP` | int32 | yes | — | TODO |
| `BIP_perc` | decimal128(9, 4) | yes | — | TODO |
| `RS_def_total` | decimal128(18, 3) | yes | — | TODO |
| `runs_above_avg` | decimal128(18, 3) | yes | — | TODO |
| `runs_above_avg_adj` | decimal128(18, 3) | yes | — | TODO |
| `runs_above_rep` | decimal128(18, 3) | yes | — | TODO |
| `RpO_replacement` | decimal128(9, 3) | yes | — | TODO |
| `GR_leverage_index_avg` | decimal128(18, 4) | yes | — | TODO |
| `WAR` | decimal128(9, 2) | yes | — | TODO |
| `salary` | int32 | yes | — | TODO |
| `teamRpG` | decimal128(18, 5) | yes | — | TODO |
| `oppRpG` | decimal128(18, 5) | yes | — | TODO |
| `pyth_exponent` | decimal128(9, 3) | yes | — | TODO |
| `waa_win_perc` | decimal128(9, 4) | yes | — | TODO |
| `WAA` | decimal128(18, 4) | yes | — | TODO |
| `WAA_adj` | decimal128(9, 4) | yes | — | TODO |
| `oppRpG_rep` | decimal128(18, 5) | yes | — | TODO |
| `pyth_exponent_rep` | decimal128(9, 3) | yes | — | TODO |
| `waa_win_perc_rep` | decimal128(9, 4) | yes | — | TODO |
| `WAR_rep` | decimal128(9, 4) | yes | — | TODO |
| `ERA_plus` | decimal128(38, 13) | yes | — | TODO |
| `ER_lg` | decimal128(18, 3) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:bref.war_pitching -->
