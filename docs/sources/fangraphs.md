# FanGraphs (a slow honest downloader, plus files you supply)

## What FanGraphs says, and what baseballpy does about it
- **What FanGraphs says** (read 2026-11-06): its contact page says that outside of the one-click data export for FanGraphs Members it does not support exporting data in any other way, and lists web scraping, API endpoints and importing data automatically as unsupported. Its 2026 "State of FanGraphs" post says at least 60 percent of its traffic is from non-human sources (crawlers, AI bots, scrapers). Its FAQ says the data is for private, non-commercial use or fair use. Its robots.txt disallows only a few legacy pages and sets no crawl delay.
- **What baseballpy does:** it can download the website's own JSON data (leaderboards and projections) because the website serves it to an ordinary client, but it does so in the most considerate way it can: **one request every two seconds, one at a time, an honest user agent** (`baseballpy/<version> (research use; +https://github.com/cbwinslow/baseballpy)`), **no retry after a refusal**, and **a hard stop at the first sign of a bot challenge** (HTTP 403, 429 or 503, or a web page where data should be). It never changes its identity, adds browser headers or uses another client to get past bot protection. If FanGraphs starts refusing, the downloader stops with a message and the files-you-supply route (below) carries on.
- **Your responsibility:** FanGraphs does not support this kind of access and could block it at any time. The data is for private, non-commercial use. Use the downloader at your own risk and keep the downloaded data to yourself.

## Download it (`-o download=yes`)
```bash
# the current season's leaderboards (3 requests)
uv run baseballpy ingest fangraphs -d batting -d pitching -d fielding --seasons 2026 -o download=yes
# any seasons (2 seconds per request: 1871 to now is about 15 minutes per leaderboard)
uv run baseballpy ingest fangraphs -d batting --seasons 2015-2024 -o download=yes
# one snapshot of every projection system (32 requests, only changed rows are stored)
uv run baseballpy ingest fangraphs -d projection -o download=yes
```
- **Leaderboards** (`batting`, `pitching`, `fielding`): `GET /api/leaders/major-league/data`, one request per season, every player (`qual=0`), one row per player and season; a past season already stored is skipped, the current one is fetched again. About 480 columns for batting, 550 for pitching.
- **Projections** (`projection`): `GET /api/projections`, one request per system (16: Steamer, ZiPS, ZiPS DC, Depth Charts, ATC, THE BAT, THE BAT X, OOPSY, and the rest-of-season versions) and stat group (batting, pitching). A row is stored only when its values changed since that player's last stored snapshot (md5 of the row's values, the same hash the files carry), as chunk `capture-<date>-<system>-<group>`. Run it daily to follow how projections move.
- **Not downloadable yet** (type them from files): `guts` and `park_factors*` (FanGraphs serves them only as web pages), `split_*` (a POST route the shared client does not send) and `prospects`.
- **Same tables as the files:** keys are renamed by one rule (lowercase; anything that is not a letter, digit or `_` becomes `_`; a leading digit gets an `n`: `1B` is `n1b`, `BB%` is `bb_`; four colliding pairs such as `-WPA` are renamed first), so a download lands in the same typed columns. Checked on a real run: the 2024 batting download had the same 478 columns, the same 1,454 players and identical counting stats as the homelab copy; 17 of 478 columns differ (WAR, dollars, runs: FanGraphs recalculated them after the season) and 9 names changed (a spelling, position lists).
- **Raw answers** are kept (gzip, sha256) in `raw/fangraphs/<dataset>/`.

## Or type files you supply (private research data)
- **`baseballpy ingest fangraphs`** (no option) reads CSV files from `inbox/fangraphs/<dataset>.csv` (or `.csv.gz`) and types them. It makes no network request. A file whose bytes are unchanged since the last ingest is skipped; `--refresh` types it again. Each file is cut into the same chunks a download writes (one per season, or per capture date for projections), so a season that arrives both ways is stored once, the newer source replacing the older.
- **Where the files come from:** the owner's homelab database holds FanGraphs tables (collected by the separate homelab project). `uv run python scripts/export_homelab_fangraphs.py` copies the ten tables read only (`ssh` key login, `psql \copy`, gzipped) into the inbox; it is for that one database. Anyone else can drop a member's one-click export (or any CSV with these column names) into the same folder; unknown headers are kept in `_extras`.
- **Private use only.** These datasets are marked private in their description and baseballpy ships no data. If you share a lake, leave `processed/fangraphs`, `raw/fangraphs` and `inbox/` out.

## Datasets
- **Rows when imported 2026-11-06; each equals the homelab table row for row, and column totals were compared against the homelab):

| Dataset | Rows | Columns | Key |
| --- | --- | --- | --- |
| `batting` | 108,947 | 477 | `playerid`, `season` |
| `pitching` | 52,989 | 546 | `playerid`, `season` |
| `fielding` | 183,284 | 86 | `playerid`, `season`, `pos` |
| `guts` | 156 | 15 | `season` |
| `park_factors` | 3,135 | 18 | `season`, `team` (9 repeated pairs in the 1800s) |
| `park_factors_handedness` | 750 | 12 | `season`, `team` |
| `projection` | 547,980 | 120 | `playerid`, `_projection_system`, `_stat_group`, `_horizon`, `_captured_date`, `_row_hash` |
| `prospects` | 19,153 | 137 | `season`, `playerid`, `minormasterid` (8,330 repeated rows) |
| `split_batting` | 167,929 | 22 | `playerid`, `season`, `_split`, `_scope` |
| `split_pitching` | 135,000 | 23 | `playerid`, `season`, `_split`, `_scope` |

- **Column names** are the homelab table's (lowercase, `_` for `%`: `bb_`, `k_`); columns starting with `_` were added by the homelab loader (`_loaded_at`, `_projection_system`, `_captured_date`, `_row_hash`). `xmlbamid` is the MLBAM id and joins to Statcast and the MLB API; `playerid` is FanGraphs' own id (`sa...` for prospects).
- **Types** are generated from the whole files (`scripts/gen_fangraphs_schemas.py`): counts are integers (the homelab stored them as text such as `157.0`), rates with more than 8 decimals or in scientific notation are `float64`, shorter decimals are exact `decimal`, times are `timestamp`. Everything else stays text (for example `ager`, `21 - 21`). Empty cells are NULL.
- **Projections** are snapshots: the homelab job appends a row only when a projected value changes, so a player-system-date can have several rows; `_row_hash` tells them apart. Use the latest `_captured_date` at or before a game for an as-of projection.
- **Prospects and old park factors** repeat some keys (the same board row loaded twice; two clubs called "Grays" in 1878 and 1885). They are kept; `baseballpy catalog status` shows the duplicate-key count.

## How the owner's homelab project gets FanGraphs data (read 2026-11-06, `~/workspace/mlb`)
- It uses `fungo`, a small client for FanGraphs' unofficial mobile-app JSON API, and sends `User-Agent: okhttp/4.12.0` (the Android app's HTTP library), "the one client Cloudflare does not block"; `pybaseball`'s FanGraphs functions return HTTP 403 and are not used. A cron job refreshes projections every 6 hours (about 60 requests a run) and appends changed rows only.
- That project's own rights table calls this "owner-risk research only": no permission evidence for automated collection, redistribution or model training, and `gold.fangraphs_*` is never public. FanGraphs says it does not support API endpoints or scraping.
- baseballpy does not copy this approach: presenting as the mobile app to pass the site's bot protection is the kind of workaround this project does not build into code that others will run. The downloader above uses the website's own routes with an honest identity and stops if it is refused. The homelab project keeps collecting on its own; baseballpy only types the copy.

## Alternatives
- **Baseball-Reference WAR** is built (`docs/sources/bref.md`); **Statcast** leaderboards and the **MLB Stats API** stat pools are in the lake.
- **A member export** (click FanGraphs' own Export Data button) follows FanGraphs' rules exactly and works with the same inbox.

## Dataset reference (generated)

<!-- BEGIN GENERATED:fangraphs.description_sources -->
### Description sources

- `babip`: https://library.fangraphs.com/offense/babip/
- `batted_ball`: https://library.fangraphs.com/offense/batted-ball/
- `fip`: https://library.fangraphs.com/pitching/fip/
- `iso`: https://library.fangraphs.com/offense/iso/
- `lob`: https://library.fangraphs.com/pitching/lob/
- `plate_discipline`: https://library.fangraphs.com/offense/plate-discipline/
- `rate_stats`: https://library.fangraphs.com/offense/rate-stats/
- `siera`: https://library.fangraphs.com/pitching/siera/
- `spd`: https://library.fangraphs.com/offense/spd/
- `ubr`: https://library.fangraphs.com/offense/ubr/
- `uzr`: https://library.fangraphs.com/defense/uzr/
- `war`: https://library.fangraphs.com/misc/war/
- `woba`: https://library.fangraphs.com/offense/woba/
- `wrc`: https://library.fangraphs.com/offense/wrc/
- `xfip`: https://library.fangraphs.com/pitching/xfip/

<!-- END GENERATED:fangraphs.description_sources -->

<!-- BEGIN GENERATED:fangraphs.batting -->
### Dataset: batting

FanGraphs season batting leaderboard (private research data): one row per player and season.

- **View:** `fangraphs_batting`
- **Processed path:** `processed/fangraphs/batting/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerid`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `bats` | string | yes | — | TODO |
| `xmlbamid` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `season` | int32 | yes | — | TODO |
| `age` | int32 | yes | — | TODO |
| `ager` | string | yes | — | TODO |
| `seasonmin` | int32 | yes | — | TODO |
| `seasonmax` | int32 | yes | — | TODO |
| `g` | int32 | yes | — | TODO |
| `ab` | int32 | yes | — | TODO |
| `pa` | int32 | yes | — | TODO |
| `h` | int32 | yes | — | TODO |
| `n1b` | int32 | yes | — | TODO |
| `n2b` | int32 | yes | — | TODO |
| `n3b` | int32 | yes | — | TODO |
| `hr` | int32 | yes | — | TODO |
| `r` | int32 | yes | — | TODO |
| `rbi` | int32 | yes | — | TODO |
| `bb` | int32 | yes | — | TODO |
| `ibb` | int32 | yes | — | TODO |
| `so` | int32 | yes | — | TODO |
| `hbp` | int32 | yes | — | TODO |
| `sf` | int32 | yes | — | TODO |
| `sh` | int32 | yes | — | TODO |
| `gdp` | int32 | yes | — | TODO |
| `sb` | int32 | yes | — | TODO |
| `cs` | int32 | yes | — | TODO |
| `avg` | double | yes | — | TODO |
| `gb` | int32 | yes | — | TODO |
| `fb` | int32 | yes | — | TODO |
| `ld` | int32 | yes | — | TODO |
| `iffb` | int32 | yes | — | TODO |
| `pitches` | int32 | yes | — | TODO |
| `balls` | int32 | yes | — | TODO |
| `strikes` | int32 | yes | — | TODO |
| `ifh` | int32 | yes | — | TODO |
| `bu` | int32 | yes | — | TODO |
| `buh` | int32 | yes | — | TODO |
| `bb_` | double | yes | — | Walk rate: the share of plate appearances that end in a walk (BB / PA). (src: rate_stats) |
| `k_` | double | yes | — | Strikeout rate: the share of plate appearances that end in a strikeout (K / PA). (src: rate_stats) |
| `bb_k` | double | yes | — | TODO |
| `obp` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `ops` | double | yes | — | TODO |
| `iso` | double | yes | — | Isolated Power: a measure of a hitter's raw power, how often a player hits for extra bases. (src: iso) |
| `babip` | double | yes | — | Batting Average on Balls In Play: how often a ball in play goes for a hit. (src: babip) |
| `gb_fb` | double | yes | — | TODO |
| `ld_` | double | yes | — | Line Drive Percentage: line drives divided by balls in play. (src: batted_ball) |
| `gb_` | double | yes | — | Ground Ball Percentage: ground balls divided by balls in play. (src: batted_ball) |
| `fb_` | double | yes | — | Fly Ball Percentage: fly balls divided by balls in play. (src: batted_ball) |
| `iffb_` | double | yes | — | Infield Fly Ball Percentage: infield fly balls divided by fly balls. (src: batted_ball) |
| `hr_fb` | double | yes | — | TODO |
| `ifh_` | double | yes | — | TODO |
| `buh_` | double | yes | — | TODO |
| `tto_` | decimal128(18, 8) | yes | — | TODO |
| `woba` | double | yes | — | Weighted On-Base Average: combines all the different aspects of hitting into one metric. (src: woba) |
| `wraa` | double | yes | — | Weighted Runs Above Average: the non-park-adjusted version of Batting Runs. (src: woba) |
| `wrc` | double | yes | — | Weighted Runs Created: an improved version of Bill James' Runs Created, in runs. (src: wrc) |
| `batting` | double | yes | — | TODO |
| `fielding` | double | yes | — | TODO |
| `replacement` | double | yes | — | TODO |
| `positional` | double | yes | — | TODO |
| `wleague` | double | yes | — | TODO |
| `cframing` | double | yes | — | TODO |
| `defense` | double | yes | — | TODO |
| `offense` | double | yes | — | TODO |
| `rar` | double | yes | — | TODO |
| `war` | double | yes | — | Wins Above Replacement: an attempt to summarize a player's total contributions to the team. (src: war) |
| `warold` | double | yes | — | TODO |
| `dollars` | double | yes | — | TODO |
| `baserunning` | double | yes | — | TODO |
| `spd` | double | yes | — | Speed Score: a Bill James statistic that rates a player on speed and baserunning ability. (src: spd) |
| `wrc_` | double | yes | — | wRC+: how a player's wRC compares with league average after controlling for park effects. (src: wrc) |
| `wbsr` | double | yes | — | TODO |
| `wpa` | double | yes | — | TODO |
| `wpa_neg` | double | yes | — | TODO |
| `wpa_pos` | double | yes | — | TODO |
| `re24` | double | yes | — | TODO |
| `rew` | double | yes | — | TODO |
| `pli` | double | yes | — | TODO |
| `phli` | double | yes | — | TODO |
| `ph` | int32 | yes | — | TODO |
| `wpa_li` | double | yes | — | TODO |
| `clutch` | double | yes | — | TODO |
| `fb_1` | decimal128(18, 8) | yes | — | TODO |
| `fbv` | decimal128(18, 8) | yes | — | TODO |
| `sl_` | decimal128(18, 8) | yes | — | TODO |
| `slv` | decimal128(18, 8) | yes | — | TODO |
| `ct_` | decimal128(18, 8) | yes | — | TODO |
| `ctv` | decimal128(18, 8) | yes | — | TODO |
| `cb_` | decimal128(18, 8) | yes | — | TODO |
| `cbv` | decimal128(18, 8) | yes | — | TODO |
| `ch_` | decimal128(18, 8) | yes | — | TODO |
| `chv` | decimal128(18, 8) | yes | — | TODO |
| `sf_` | decimal128(18, 8) | yes | — | TODO |
| `sfv` | decimal128(18, 8) | yes | — | TODO |
| `kn_` | decimal128(18, 8) | yes | — | TODO |
| `knv` | decimal128(18, 8) | yes | — | TODO |
| `xx_` | decimal128(18, 8) | yes | — | TODO |
| `po_` | decimal128(18, 8) | yes | — | TODO |
| `wfb` | double | yes | — | TODO |
| `wsl` | double | yes | — | TODO |
| `wct` | double | yes | — | TODO |
| `wcb` | double | yes | — | TODO |
| `wch` | double | yes | — | TODO |
| `wsf` | double | yes | — | TODO |
| `wkn` | double | yes | — | TODO |
| `wfb_c` | double | yes | — | TODO |
| `wsl_c` | double | yes | — | TODO |
| `wct_c` | double | yes | — | TODO |
| `wcb_c` | double | yes | — | TODO |
| `wch_c` | double | yes | — | TODO |
| `wsf_c` | double | yes | — | TODO |
| `wkn_c` | double | yes | — | TODO |
| `o_swing_` | decimal128(18, 8) | yes | — | Swings at pitches outside the zone divided by pitches outside the zone. (src: plate_discipline) |
| `z_swing_` | decimal128(18, 8) | yes | — | Swings at pitches inside the zone divided by pitches inside the zone. (src: plate_discipline) |
| `swing_` | decimal128(18, 8) | yes | — | Swings divided by pitches. (src: plate_discipline) |
| `o_contact_` | decimal128(18, 8) | yes | — | Contact made on pitches outside the zone divided by swings on pitches outside the zone. (src: plate_discipline) |
| `z_contact_` | decimal128(18, 8) | yes | — | Contact made on pitches inside the zone divided by swings on pitches inside the zone. (src: plate_discipline) |
| `contact_` | decimal128(18, 8) | yes | — | Pitches on which contact was made divided by swings. (src: plate_discipline) |
| `zone_` | decimal128(18, 8) | yes | — | Pitches in the strike zone divided by total pitches. (src: plate_discipline) |
| `f_strike_` | decimal128(18, 8) | yes | — | First-pitch strikes divided by plate appearances. (src: plate_discipline) |
| `swstr_` | decimal128(18, 8) | yes | — | Swings and misses divided by total pitches. (src: plate_discipline) |
| `cstr_` | decimal128(18, 8) | yes | — | TODO |
| `c_swstr_` | decimal128(18, 8) | yes | — | TODO |
| `pull` | int32 | yes | — | TODO |
| `cent` | int32 | yes | — | TODO |
| `oppo` | int32 | yes | — | TODO |
| `soft` | int32 | yes | — | TODO |
| `med` | int32 | yes | — | TODO |
| `hard` | int32 | yes | — | TODO |
| `bipcount` | int32 | yes | — | TODO |
| `pull_` | decimal128(18, 8) | yes | — | TODO |
| `cent_` | decimal128(18, 8) | yes | — | TODO |
| `oppo_` | decimal128(18, 8) | yes | — | TODO |
| `soft_` | decimal128(18, 8) | yes | — | TODO |
| `med_` | decimal128(18, 8) | yes | — | TODO |
| `hard_` | decimal128(18, 8) | yes | — | TODO |
| `ubr` | double | yes | — | Ultimate Base Running: the value a player adds through base running on non-stolen-base plays. (src: ubr) |
| `gdpruns` | double | yes | — | TODO |
| `avg_` | double | yes | — | TODO |
| `bb__` | double | yes | — | TODO |
| `k__` | double | yes | — | TODO |
| `obp_` | double | yes | — | TODO |
| `slg_` | double | yes | — | TODO |
| `iso_` | double | yes | — | TODO |
| `babip_` | double | yes | — | TODO |
| `ld__` | double | yes | — | TODO |
| `gb__` | double | yes | — | TODO |
| `fb__` | double | yes | — | TODO |
| `hrfb__` | double | yes | — | TODO |
| `pull__` | double | yes | — | TODO |
| `cent__` | double | yes | — | TODO |
| `oppo__` | double | yes | — | TODO |
| `soft__` | double | yes | — | TODO |
| `med__` | double | yes | — | TODO |
| `hard__` | double | yes | — | TODO |
| `xwoba` | double | yes | — | TODO |
| `xavg` | double | yes | — | TODO |
| `xslg` | double | yes | — | TODO |
| `xbr` | double | yes | — | TODO |
| `pptv` | int32 | yes | — | TODO |
| `cptv` | int32 | yes | — | TODO |
| `bptv` | int32 | yes | — | TODO |
| `dsv` | int32 | yes | — | TODO |
| `dgv` | int32 | yes | — | TODO |
| `btv` | int32 | yes | — | TODO |
| `rpptv` | double | yes | — | TODO |
| `rcptv` | double | yes | — | TODO |
| `rbptv` | double | yes | — | TODO |
| `rdsv` | double | yes | — | TODO |
| `rdgv` | double | yes | — | TODO |
| `rbtv` | double | yes | — | TODO |
| `ebv` | int32 | yes | — | TODO |
| `esv` | int32 | yes | — | TODO |
| `rfteamv` | double | yes | — | TODO |
| `rbteamv` | double | yes | — | TODO |
| `rtv` | double | yes | — | TODO |
| `breview` | int32 | yes | — | TODO |
| `boverturned` | int32 | yes | — | TODO |
| `bcorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wbreview` | double | yes | — | TODO |
| `preview` | int32 | yes | — | TODO |
| `poverturned` | int32 | yes | — | TODO |
| `pcorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wpreview` | double | yes | — | TODO |
| `creview` | int32 | yes | — | TODO |
| `coverturned` | int32 | yes | — | TODO |
| `ccorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wcreview` | double | yes | — | TODO |
| `ascreview` | int32 | yes | — | TODO |
| `ascoverturned` | int32 | yes | — | TODO |
| `asccorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wascreview` | double | yes | — | TODO |
| `pfxfa_` | decimal128(18, 8) | yes | — | TODO |
| `pfxft_` | string | yes | — | TODO |
| `pfxfc_` | decimal128(18, 8) | yes | — | TODO |
| `pfxfs_` | decimal128(18, 8) | yes | — | TODO |
| `pfxfo_` | decimal128(18, 8) | yes | — | TODO |
| `pfxsi_` | decimal128(18, 8) | yes | — | TODO |
| `pfxsl_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcu_` | decimal128(18, 8) | yes | — | TODO |
| `pfxkc_` | decimal128(18, 8) | yes | — | TODO |
| `pfxep_` | decimal128(18, 8) | yes | — | TODO |
| `pfxch_` | decimal128(18, 8) | yes | — | TODO |
| `pfxsc_` | decimal128(18, 8) | yes | — | TODO |
| `pfxkn_` | decimal128(18, 8) | yes | — | TODO |
| `pfxun_` | decimal128(18, 8) | yes | — | TODO |
| `pfxslo_` | decimal128(18, 8) | yes | — | TODO |
| `pfxst_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcuo_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcv_` | decimal128(18, 8) | yes | — | TODO |
| `pfxvfa` | double | yes | — | TODO |
| `pfxvft` | string | yes | — | TODO |
| `pfxvfc` | double | yes | — | TODO |
| `pfxvfs` | double | yes | — | TODO |
| `pfxvfo` | double | yes | — | TODO |
| `pfxvsi` | double | yes | — | TODO |
| `pfxvsl` | double | yes | — | TODO |
| `pfxvcu` | double | yes | — | TODO |
| `pfxvkc` | double | yes | — | TODO |
| `pfxvep` | double | yes | — | TODO |
| `pfxvch` | double | yes | — | TODO |
| `pfxvsc` | double | yes | — | TODO |
| `pfxvkn` | double | yes | — | TODO |
| `pfxvslo` | double | yes | — | TODO |
| `pfxvst` | double | yes | — | TODO |
| `pfxvcuo` | double | yes | — | TODO |
| `pfxvcv` | double | yes | — | TODO |
| `pfxfa_x` | double | yes | — | TODO |
| `pfxft_x` | string | yes | — | TODO |
| `pfxfc_x` | double | yes | — | TODO |
| `pfxfs_x` | double | yes | — | TODO |
| `pfxfo_x` | double | yes | — | TODO |
| `pfxsi_x` | double | yes | — | TODO |
| `pfxsl_x` | double | yes | — | TODO |
| `pfxcu_x` | double | yes | — | TODO |
| `pfxkc_x` | double | yes | — | TODO |
| `pfxep_x` | double | yes | — | TODO |
| `pfxch_x` | double | yes | — | TODO |
| `pfxsc_x` | double | yes | — | TODO |
| `pfxkn_x` | double | yes | — | TODO |
| `pfxslo_x` | double | yes | — | TODO |
| `pfxst_x` | double | yes | — | TODO |
| `pfxcuo_x` | double | yes | — | TODO |
| `pfxcv_x` | double | yes | — | TODO |
| `pfxfa_z` | double | yes | — | TODO |
| `pfxft_z` | string | yes | — | TODO |
| `pfxfc_z` | double | yes | — | TODO |
| `pfxfs_z` | double | yes | — | TODO |
| `pfxfo_z` | double | yes | — | TODO |
| `pfxsi_z` | double | yes | — | TODO |
| `pfxsl_z` | double | yes | — | TODO |
| `pfxcu_z` | double | yes | — | TODO |
| `pfxkc_z` | double | yes | — | TODO |
| `pfxep_z` | double | yes | — | TODO |
| `pfxch_z` | double | yes | — | TODO |
| `pfxsc_z` | double | yes | — | TODO |
| `pfxkn_z` | double | yes | — | TODO |
| `pfxslo_z` | double | yes | — | TODO |
| `pfxst_z` | double | yes | — | TODO |
| `pfxcuo_z` | double | yes | — | TODO |
| `pfxcv_z` | double | yes | — | TODO |
| `pfxwfa` | double | yes | — | TODO |
| `pfxwft` | string | yes | — | TODO |
| `pfxwfc` | double | yes | — | TODO |
| `pfxwfs` | double | yes | — | TODO |
| `pfxwfo` | double | yes | — | TODO |
| `pfxwsi` | double | yes | — | TODO |
| `pfxwsl` | double | yes | — | TODO |
| `pfxwcu` | double | yes | — | TODO |
| `pfxwkc` | double | yes | — | TODO |
| `pfxwep` | double | yes | — | TODO |
| `pfxwch` | double | yes | — | TODO |
| `pfxwsc` | double | yes | — | TODO |
| `pfxwkn` | double | yes | — | TODO |
| `pfxwslo` | double | yes | — | TODO |
| `pfxwst` | double | yes | — | TODO |
| `pfxwcuo` | double | yes | — | TODO |
| `pfxwcv` | double | yes | — | TODO |
| `pfxwfa_c` | double | yes | — | TODO |
| `pfxwft_c` | string | yes | — | TODO |
| `pfxwfc_c` | double | yes | — | TODO |
| `pfxwfs_c` | double | yes | — | TODO |
| `pfxwfo_c` | double | yes | — | TODO |
| `pfxwsi_c` | double | yes | — | TODO |
| `pfxwsl_c` | double | yes | — | TODO |
| `pfxwcu_c` | double | yes | — | TODO |
| `pfxwkc_c` | double | yes | — | TODO |
| `pfxwep_c` | double | yes | — | TODO |
| `pfxwch_c` | double | yes | — | TODO |
| `pfxwsc_c` | double | yes | — | TODO |
| `pfxwkn_c` | double | yes | — | TODO |
| `pfxwslo_c` | double | yes | — | TODO |
| `pfxwst_c` | double | yes | — | TODO |
| `pfxwcuo_c` | double | yes | — | TODO |
| `pfxwcv_c` | double | yes | — | TODO |
| `pfxaafa` | double | yes | — | TODO |
| `pfxaaft` | string | yes | — | TODO |
| `pfxaafc` | double | yes | — | TODO |
| `pfxaafs` | double | yes | — | TODO |
| `pfxaafo` | double | yes | — | TODO |
| `pfxaasi` | double | yes | — | TODO |
| `pfxaasl` | double | yes | — | TODO |
| `pfxaacu` | double | yes | — | TODO |
| `pfxaakc` | double | yes | — | TODO |
| `pfxaaep` | double | yes | — | TODO |
| `pfxaach` | double | yes | — | TODO |
| `pfxaasc` | double | yes | — | TODO |
| `pfxaakn` | double | yes | — | TODO |
| `pfxaaslo` | double | yes | — | TODO |
| `pfxaast` | double | yes | — | TODO |
| `pfxaacuo` | double | yes | — | TODO |
| `pfxaacv` | double | yes | — | TODO |
| `pfxspfa` | double | yes | — | TODO |
| `pfxspft` | string | yes | — | TODO |
| `pfxspfc` | double | yes | — | TODO |
| `pfxspfs` | double | yes | — | TODO |
| `pfxspfo` | double | yes | — | TODO |
| `pfxspsi` | double | yes | — | TODO |
| `pfxspsl` | double | yes | — | TODO |
| `pfxspcu` | double | yes | — | TODO |
| `pfxspkc` | double | yes | — | TODO |
| `pfxspep` | double | yes | — | TODO |
| `pfxspch` | double | yes | — | TODO |
| `pfxspsc` | double | yes | — | TODO |
| `pfxspkn` | double | yes | — | TODO |
| `pfxspslo` | double | yes | — | TODO |
| `pfxspst` | double | yes | — | TODO |
| `pfxspcuo` | double | yes | — | TODO |
| `pfxspcv` | double | yes | — | TODO |
| `pfxo_swing_` | decimal128(18, 8) | yes | — | TODO |
| `pfxz_swing_` | decimal128(18, 8) | yes | — | TODO |
| `pfxswing_` | decimal128(18, 8) | yes | — | TODO |
| `pfxo_contact_` | decimal128(18, 8) | yes | — | TODO |
| `pfxz_contact_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcontact_` | decimal128(18, 8) | yes | — | TODO |
| `pfxzone_` | decimal128(18, 8) | yes | — | TODO |
| `pfxpace` | decimal128(18, 8) | yes | — | TODO |
| `avgbatspeed` | double | yes | — | TODO |
| `fastswing_` | decimal128(18, 8) | yes | — | TODO |
| `swinglength` | double | yes | — | TODO |
| `squaredupcontact_` | decimal128(18, 8) | yes | — | TODO |
| `squaredupswing_` | decimal128(18, 8) | yes | — | TODO |
| `blastcontact_` | decimal128(18, 8) | yes | — | TODO |
| `blastswing_` | decimal128(18, 8) | yes | — | TODO |
| `swords` | int32 | yes | — | TODO |
| `competitiveswings` | int32 | yes | — | TODO |
| `tilt` | double | yes | — | TODO |
| `attackangle` | double | yes | — | TODO |
| `attackdirection` | double | yes | — | TODO |
| `idealattackangle_` | decimal128(18, 8) | yes | — | TODO |
| `depthinbox` | double | yes | — | TODO |
| `distanceoffplate` | double | yes | — | TODO |
| `sch_swing_` | decimal128(18, 8) | yes | — | TODO |
| `sch_contact_` | decimal128(18, 8) | yes | — | TODO |
| `sch_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scs_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scs_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scs_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scc_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scc_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scc_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scw_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scw_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scw_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scsi_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scsi_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scsi_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scso_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scso_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scso_zone_` | decimal128(18, 8) | yes | — | TODO |
| `sco_swing_` | decimal128(18, 8) | yes | — | TODO |
| `sco_contact_` | decimal128(18, 8) | yes | — | TODO |
| `sco_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scz_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scz_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scz_zone_` | decimal128(18, 8) | yes | — | TODO |
| `pich_` | decimal128(18, 8) | yes | — | TODO |
| `pics_` | decimal128(18, 8) | yes | — | TODO |
| `picu_` | decimal128(18, 8) | yes | — | TODO |
| `pifa_` | decimal128(18, 8) | yes | — | TODO |
| `pifc_` | decimal128(18, 8) | yes | — | TODO |
| `pifs_` | decimal128(18, 8) | yes | — | TODO |
| `pikn_` | decimal128(18, 8) | yes | — | TODO |
| `pisb_` | decimal128(18, 8) | yes | — | TODO |
| `pisi_` | decimal128(18, 8) | yes | — | TODO |
| `pisl_` | decimal128(18, 8) | yes | — | TODO |
| `pixx_` | decimal128(18, 8) | yes | — | TODO |
| `pivch` | double | yes | — | TODO |
| `pivcs` | double | yes | — | TODO |
| `pivcu` | double | yes | — | TODO |
| `pivfa` | double | yes | — | TODO |
| `pivfc` | double | yes | — | TODO |
| `pivfs` | double | yes | — | TODO |
| `pivkn` | double | yes | — | TODO |
| `pivsb` | double | yes | — | TODO |
| `pivsi` | double | yes | — | TODO |
| `pivsl` | double | yes | — | TODO |
| `pivxx` | double | yes | — | TODO |
| `pich_x` | double | yes | — | TODO |
| `pics_x` | double | yes | — | TODO |
| `picu_x` | double | yes | — | TODO |
| `pifa_x` | double | yes | — | TODO |
| `pifc_x` | double | yes | — | TODO |
| `pifs_x` | double | yes | — | TODO |
| `pikn_x` | double | yes | — | TODO |
| `pisb_x` | double | yes | — | TODO |
| `pisi_x` | double | yes | — | TODO |
| `pisl_x` | double | yes | — | TODO |
| `pixx_x` | double | yes | — | TODO |
| `pich_z` | double | yes | — | TODO |
| `pics_z` | double | yes | — | TODO |
| `picu_z` | double | yes | — | TODO |
| `pifa_z` | double | yes | — | TODO |
| `pifc_z` | double | yes | — | TODO |
| `pifs_z` | double | yes | — | TODO |
| `pikn_z` | double | yes | — | TODO |
| `pisb_z` | double | yes | — | TODO |
| `pisi_z` | double | yes | — | TODO |
| `pisl_z` | double | yes | — | TODO |
| `pixx_z` | double | yes | — | TODO |
| `piwch` | double | yes | — | TODO |
| `piwcs` | double | yes | — | TODO |
| `piwcu` | double | yes | — | TODO |
| `piwfa` | double | yes | — | TODO |
| `piwfc` | double | yes | — | TODO |
| `piwfs` | double | yes | — | TODO |
| `piwkn` | double | yes | — | TODO |
| `piwsb` | double | yes | — | TODO |
| `piwsi` | double | yes | — | TODO |
| `piwsl` | double | yes | — | TODO |
| `piwxx` | double | yes | — | TODO |
| `piwch_c` | double | yes | — | TODO |
| `piwcs_c` | double | yes | — | TODO |
| `piwcu_c` | double | yes | — | TODO |
| `piwfa_c` | double | yes | — | TODO |
| `piwfc_c` | double | yes | — | TODO |
| `piwfs_c` | double | yes | — | TODO |
| `piwkn_c` | double | yes | — | TODO |
| `piwsb_c` | double | yes | — | TODO |
| `piwsi_c` | double | yes | — | TODO |
| `piwsl_c` | double | yes | — | TODO |
| `piwxx_c` | double | yes | — | TODO |
| `pio_swing_` | decimal128(18, 8) | yes | — | TODO |
| `piz_swing_` | decimal128(18, 8) | yes | — | TODO |
| `piswing_` | decimal128(18, 8) | yes | — | TODO |
| `pio_contact_` | decimal128(18, 8) | yes | — | TODO |
| `piz_contact_` | decimal128(18, 8) | yes | — | TODO |
| `picontact_` | decimal128(18, 8) | yes | — | TODO |
| `pizone_` | decimal128(18, 8) | yes | — | TODO |
| `pipace` | decimal128(18, 8) | yes | — | TODO |
| `events` | int32 | yes | — | TODO |
| `ev` | double | yes | — | TODO |
| `la` | double | yes | — | TODO |
| `barrels` | int32 | yes | — | TODO |
| `barrel_` | decimal128(18, 8) | yes | — | TODO |
| `maxev` | decimal128(9, 1) | yes | — | TODO |
| `hardhit` | int32 | yes | — | TODO |
| `hardhit_` | decimal128(18, 8) | yes | — | TODO |
| `q` | decimal128(18, 8) | yes | — | TODO |
| `tg` | int32 | yes | — | TODO |
| `tpa` | int32 | yes | — | TODO |
| `playernameroute` | string | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `positiondb` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `playerid` | int32 | yes | — | TODO |
| `teamname` | string | yes | — | TODO |
| `teamnameabb` | string | yes | — | TODO |
| `teamid` | int32 | yes | — | TODO |
| `playerteamid` | int32 | yes | — | TODO |
| `pos` | decimal128(18, 8) | yes | — | TODO |
| `ev90` | decimal128(9, 1) | yes | — | TODO |
| `_season` | int32 | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.batting -->

<!-- BEGIN GENERATED:fangraphs.fielding -->
### Dataset: fielding

FanGraphs season fielding leaderboard (private research data): one row per player, season and position.

- **View:** `fangraphs_fielding`
- **Processed path:** `processed/fangraphs/fielding/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerid`, `season`, `pos`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `name` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `season` | int32 | yes | — | TODO |
| `seasonmin` | int32 | yes | — | TODO |
| `seasonmax` | int32 | yes | — | TODO |
| `pos` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `g` | int32 | yes | — | TODO |
| `gs` | int32 | yes | — | TODO |
| `inn` | decimal128(9, 1) | yes | — | TODO |
| `po` | int32 | yes | — | TODO |
| `a` | int32 | yes | — | TODO |
| `e` | int32 | yes | — | TODO |
| `fe` | int32 | yes | — | TODO |
| `te` | int32 | yes | — | TODO |
| `dp` | int32 | yes | — | TODO |
| `dps` | int32 | yes | — | TODO |
| `dpt` | int32 | yes | — | TODO |
| `dpf` | int32 | yes | — | TODO |
| `scp` | int32 | yes | — | TODO |
| `sb` | int32 | yes | — | TODO |
| `cs` | int32 | yes | — | TODO |
| `pb` | int32 | yes | — | TODO |
| `wp` | int32 | yes | — | TODO |
| `fp` | decimal128(18, 8) | yes | — | TODO |
| `tz` | int32 | yes | — | TODO |
| `rsb` | int32 | yes | — | TODO |
| `rgdp` | int32 | yes | — | TODO |
| `rarm` | int32 | yes | — | TODO |
| `rgfp` | int32 | yes | — | TODO |
| `rpm` | int32 | yes | — | TODO |
| `rsz` | double | yes | — | TODO |
| `rts` | string | yes | — | TODO |
| `rcera` | int32 | yes | — | TODO |
| `drs` | int32 | yes | — | TODO |
| `biz` | int32 | yes | — | TODO |
| `plays` | int32 | yes | — | TODO |
| `rzr` | decimal128(18, 8) | yes | — | TODO |
| `ooz` | int32 | yes | — | TODO |
| `tzl` | string | yes | — | TODO |
| `fsr` | int32 | yes | — | TODO |
| `cpp` | double | yes | — | TODO |
| `rpp` | double | yes | — | TODO |
| `arm` | double | yes | — | TODO |
| `dpr` | double | yes | — | Double-Play Runs: runs an infielder adds above average by turning double plays. (src: uzr) |
| `rngr` | double | yes | — | Range Runs: whether a fielder reaches more balls than average at their position. (src: uzr) |
| `errr` | double | yes | — | Error Runs: runs gained or lost by committing fewer or more errors than a league-average player at the position. (src: uzr) |
| `uzr` | double | yes | — | Ultimate Zone Rating: puts a run value to defense. (src: uzr) |
| `uzr_150` | double | yes | — | TODO |
| `defense` | double | yes | — | TODO |
| `made0` | int32 | yes | — | TODO |
| `prob0` | int32 | yes | — | TODO |
| `made10` | decimal128(18, 8) | yes | — | TODO |
| `prob10` | int32 | yes | — | TODO |
| `made40` | decimal128(18, 8) | yes | — | TODO |
| `prob40` | int32 | yes | — | TODO |
| `made60` | decimal128(18, 8) | yes | — | TODO |
| `prob60` | int32 | yes | — | TODO |
| `made90` | decimal128(18, 8) | yes | — | TODO |
| `prob90` | int32 | yes | — | TODO |
| `made100` | decimal128(18, 8) | yes | — | TODO |
| `prob100` | int32 | yes | — | TODO |
| `cstrikes` | double | yes | — | TODO |
| `cframing` | double | yes | — | TODO |
| `oaa` | int32 | yes | — | TODO |
| `rfrp` | int32 | yes | — | TODO |
| `afrp` | int32 | yes | — | TODO |
| `dfrp` | int32 | yes | — | TODO |
| `cfrp` | int32 | yes | — | TODO |
| `bfrp` | int32 | yes | — | TODO |
| `tfrp` | int32 | yes | — | TODO |
| `ffrp` | int32 | yes | — | TODO |
| `frp` | int32 | yes | — | TODO |
| `q` | double | yes | — | TODO |
| `tinn` | double | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `playernameroute` | string | yes | — | TODO |
| `positiondb` | string | yes | — | TODO |
| `playerid` | int32 | yes | — | TODO |
| `xmlbamid` | int32 | yes | — | TODO |
| `teamid` | int32 | yes | — | TODO |
| `teamname` | string | yes | — | TODO |
| `teamnameabb` | string | yes | — | TODO |
| `playerteamid` | int32 | yes | — | TODO |
| `_season` | int32 | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.fielding -->

<!-- BEGIN GENERATED:fangraphs.guts -->
### Dataset: guts

FanGraphs Guts! constants (private research data): wOBA weights, FIP constant, run values per season.

- **View:** `fangraphs_guts`
- **Processed path:** `processed/fangraphs/guts/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season` | int32 | yes | — | TODO |
| `woba` | decimal128(9, 3) | yes | — | Weighted On-Base Average: combines all the different aspects of hitting into one metric. (src: woba) |
| `wobascale` | decimal128(9, 3) | yes | — | TODO |
| `wbb` | decimal128(9, 3) | yes | — | TODO |
| `whbp` | decimal128(9, 3) | yes | — | TODO |
| `w1b` | decimal128(9, 3) | yes | — | TODO |
| `w2b` | decimal128(9, 3) | yes | — | TODO |
| `w3b` | decimal128(9, 3) | yes | — | TODO |
| `whr` | decimal128(9, 3) | yes | — | TODO |
| `runsb` | decimal128(9, 3) | yes | — | TODO |
| `runcs` | decimal128(9, 3) | yes | — | TODO |
| `r_pa` | decimal128(9, 3) | yes | — | TODO |
| `r_w` | decimal128(9, 3) | yes | — | TODO |
| `cfip` | decimal128(9, 3) | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.guts -->

<!-- BEGIN GENERATED:fangraphs.park_factors -->
### Dataset: park_factors

FanGraphs park factors (private research data): one row per season and team.

- **View:** `fangraphs_park_factors`
- **Processed path:** `processed/fangraphs/park_factors/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `season`, `team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season` | int32 | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `basic__5yr_` | int32 | yes | — | TODO |
| `n3yr` | int32 | yes | — | TODO |
| `n1yr` | int32 | yes | — | TODO |
| `n1b` | int32 | yes | — | TODO |
| `n2b` | int32 | yes | — | TODO |
| `n3b` | int32 | yes | — | TODO |
| `hr` | int32 | yes | — | TODO |
| `so` | int32 | yes | — | TODO |
| `bb` | int32 | yes | — | TODO |
| `gb` | int32 | yes | — | TODO |
| `fb` | int32 | yes | — | TODO |
| `ld` | int32 | yes | — | TODO |
| `iffb` | int32 | yes | — | TODO |
| `fip` | int32 | yes | — | Fielding Independent Pitching: what a pitcher's ERA would look like with typical results on balls in play. (src: fip) |
| `_season` | int32 | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.park_factors -->

<!-- BEGIN GENERATED:fangraphs.park_factors_handedness -->
### Dataset: park_factors_handedness

FanGraphs park factors by batter handedness (private research data), from 2002.

- **View:** `fangraphs_park_factors_handedness`
- **Processed path:** `processed/fangraphs/park_factors_handedness/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `season`, `team`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season` | int32 | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `n1b_as_l` | int32 | yes | — | TODO |
| `n1b_as_r` | int32 | yes | — | TODO |
| `n2b_as_l` | int32 | yes | — | TODO |
| `n2b_as_r` | int32 | yes | — | TODO |
| `n3b_as_l` | int32 | yes | — | TODO |
| `n3b_as_r` | int32 | yes | — | TODO |
| `hr_as_l` | int32 | yes | — | TODO |
| `hr_as_r` | int32 | yes | — | TODO |
| `_season` | int32 | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.park_factors_handedness -->

<!-- BEGIN GENERATED:fangraphs.pitching -->
### Dataset: pitching

FanGraphs season pitching leaderboard (private research data): one row per player and season.

- **View:** `fangraphs_pitching`
- **Processed path:** `processed/fangraphs/pitching/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerid`, `season`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `throws` | string | yes | — | TODO |
| `xmlbamid` | int32 | yes | — | TODO |
| `name` | string | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `season` | int32 | yes | — | TODO |
| `age` | int32 | yes | — | TODO |
| `ager` | string | yes | — | TODO |
| `seasonmin` | int32 | yes | — | TODO |
| `seasonmax` | int32 | yes | — | TODO |
| `w` | int32 | yes | — | TODO |
| `l` | int32 | yes | — | TODO |
| `era` | double | yes | — | TODO |
| `g` | int32 | yes | — | TODO |
| `gs` | int32 | yes | — | TODO |
| `qs` | int32 | yes | — | TODO |
| `cg` | int32 | yes | — | TODO |
| `sho` | int32 | yes | — | TODO |
| `sv` | int32 | yes | — | TODO |
| `bs` | int32 | yes | — | TODO |
| `ip` | decimal128(9, 1) | yes | — | TODO |
| `tbf` | int32 | yes | — | TODO |
| `h` | int32 | yes | — | TODO |
| `r` | int32 | yes | — | TODO |
| `er` | int32 | yes | — | TODO |
| `hr` | int32 | yes | — | TODO |
| `bb` | int32 | yes | — | TODO |
| `ibb` | int32 | yes | — | TODO |
| `hbp` | int32 | yes | — | TODO |
| `wp` | int32 | yes | — | TODO |
| `bk` | int32 | yes | — | TODO |
| `so` | int32 | yes | — | TODO |
| `gb` | int32 | yes | — | TODO |
| `fb` | int32 | yes | — | TODO |
| `ld` | int32 | yes | — | TODO |
| `iffb` | int32 | yes | — | TODO |
| `pitches` | int32 | yes | — | TODO |
| `balls` | int32 | yes | — | TODO |
| `strikes` | int32 | yes | — | TODO |
| `rs` | int32 | yes | — | TODO |
| `ifh` | int32 | yes | — | TODO |
| `bu` | int32 | yes | — | TODO |
| `buh` | int32 | yes | — | TODO |
| `k_9` | double | yes | — | TODO |
| `bb_9` | double | yes | — | TODO |
| `k_bb` | decimal128(18, 8) | yes | — | TODO |
| `h_9` | double | yes | — | TODO |
| `hr_9` | double | yes | — | TODO |
| `avg` | double | yes | — | TODO |
| `whip` | double | yes | — | TODO |
| `babip` | double | yes | — | Batting Average on Balls In Play: how often a ball in play goes for a hit. (src: babip) |
| `lob_` | decimal128(18, 8) | yes | — | Left On Base Percentage: the percentage of base runners a pitcher strands on base. (src: lob) |
| `fip` | double | yes | — | Fielding Independent Pitching: what a pitcher's ERA would look like with typical results on balls in play. (src: fip) |
| `gb_fb` | double | yes | — | TODO |
| `ld_` | double | yes | — | Line Drive Percentage: line drives divided by balls in play. (src: batted_ball) |
| `gb_` | double | yes | — | Ground Ball Percentage: ground balls divided by balls in play. (src: batted_ball) |
| `fb_` | double | yes | — | Fly Ball Percentage: fly balls divided by balls in play. (src: batted_ball) |
| `iffb_` | double | yes | — | Infield Fly Ball Percentage: infield fly balls divided by fly balls. (src: batted_ball) |
| `hr_fb` | double | yes | — | TODO |
| `ifh_` | double | yes | — | TODO |
| `buh_` | double | yes | — | TODO |
| `tto_` | decimal128(18, 8) | yes | — | TODO |
| `cframing` | double | yes | — | TODO |
| `starting` | double | yes | — | TODO |
| `start_ip` | double | yes | — | TODO |
| `relieving` | double | yes | — | TODO |
| `relief_ip` | double | yes | — | TODO |
| `rar` | double | yes | — | TODO |
| `war` | double | yes | — | Wins Above Replacement: an attempt to summarize a player's total contributions to the team. (src: war) |
| `dollars` | double | yes | — | TODO |
| `ra9_wins` | double | yes | — | TODO |
| `lob_wins` | double | yes | — | TODO |
| `bip_wins` | double | yes | — | TODO |
| `bs_wins` | double | yes | — | TODO |
| `tera` | double | yes | — | TODO |
| `xfip` | double | yes | — | Expected FIP: a regressed version of FIP that uses the league-average HR/FB rate on fly balls. (src: xfip) |
| `wpa` | double | yes | — | TODO |
| `wpa_neg` | double | yes | — | TODO |
| `wpa_pos` | double | yes | — | TODO |
| `re24` | double | yes | — | TODO |
| `rew` | double | yes | — | TODO |
| `pli` | double | yes | — | TODO |
| `inli` | double | yes | — | TODO |
| `gmli` | double | yes | — | TODO |
| `exli` | double | yes | — | TODO |
| `pulls` | int32 | yes | — | TODO |
| `games` | int32 | yes | — | TODO |
| `wpa_li` | double | yes | — | TODO |
| `clutch` | double | yes | — | TODO |
| `fb_1` | decimal128(18, 8) | yes | — | TODO |
| `fbv` | decimal128(18, 8) | yes | — | TODO |
| `sl_` | decimal128(18, 8) | yes | — | TODO |
| `slv` | decimal128(18, 8) | yes | — | TODO |
| `ct_` | decimal128(18, 8) | yes | — | TODO |
| `ctv` | decimal128(18, 8) | yes | — | TODO |
| `cb_` | decimal128(18, 8) | yes | — | TODO |
| `cbv` | decimal128(18, 8) | yes | — | TODO |
| `ch_` | decimal128(18, 8) | yes | — | TODO |
| `chv` | decimal128(18, 8) | yes | — | TODO |
| `sf_` | decimal128(18, 8) | yes | — | TODO |
| `sfv` | decimal128(18, 8) | yes | — | TODO |
| `kn_` | decimal128(18, 8) | yes | — | TODO |
| `knv` | decimal128(18, 8) | yes | — | TODO |
| `xx_` | decimal128(18, 8) | yes | — | TODO |
| `po_` | decimal128(18, 8) | yes | — | TODO |
| `wfb` | double | yes | — | TODO |
| `wsl` | double | yes | — | TODO |
| `wct` | double | yes | — | TODO |
| `wcb` | double | yes | — | TODO |
| `wch` | double | yes | — | TODO |
| `wsf` | double | yes | — | TODO |
| `wkn` | double | yes | — | TODO |
| `wfb_c` | double | yes | — | TODO |
| `wsl_c` | double | yes | — | TODO |
| `wct_c` | double | yes | — | TODO |
| `wcb_c` | double | yes | — | TODO |
| `wch_c` | double | yes | — | TODO |
| `wsf_c` | double | yes | — | TODO |
| `wkn_c` | double | yes | — | TODO |
| `o_swing_` | decimal128(18, 8) | yes | — | Swings at pitches outside the zone divided by pitches outside the zone. (src: plate_discipline) |
| `z_swing_` | decimal128(18, 8) | yes | — | Swings at pitches inside the zone divided by pitches inside the zone. (src: plate_discipline) |
| `swing_` | decimal128(18, 8) | yes | — | Swings divided by pitches. (src: plate_discipline) |
| `o_contact_` | decimal128(18, 8) | yes | — | Contact made on pitches outside the zone divided by swings on pitches outside the zone. (src: plate_discipline) |
| `z_contact_` | decimal128(18, 8) | yes | — | Contact made on pitches inside the zone divided by swings on pitches inside the zone. (src: plate_discipline) |
| `contact_` | decimal128(18, 8) | yes | — | Pitches on which contact was made divided by swings. (src: plate_discipline) |
| `zone_` | decimal128(18, 8) | yes | — | Pitches in the strike zone divided by total pitches. (src: plate_discipline) |
| `f_strike_` | decimal128(18, 8) | yes | — | First-pitch strikes divided by plate appearances. (src: plate_discipline) |
| `swstr_` | decimal128(18, 8) | yes | — | Swings and misses divided by total pitches. (src: plate_discipline) |
| `cstr_` | decimal128(18, 8) | yes | — | TODO |
| `c_swstr_` | decimal128(18, 8) | yes | — | TODO |
| `hld` | int32 | yes | — | TODO |
| `sd` | int32 | yes | — | TODO |
| `md` | int32 | yes | — | TODO |
| `era_` | double | yes | — | TODO |
| `fip_` | double | yes | — | TODO |
| `xfip_` | double | yes | — | TODO |
| `k_` | decimal128(18, 8) | yes | — | Strikeout rate: the share of plate appearances that end in a strikeout (K / PA). (src: rate_stats) |
| `bb_` | decimal128(18, 8) | yes | — | Walk rate: the share of plate appearances that end in a walk (BB / PA). (src: rate_stats) |
| `k_minus_bb_pct` | decimal128(18, 8) | yes | — | TODO |
| `siera` | double | yes | — | Skill-Interactive ERA: an ERA estimator meant to show a pitcher's underlying skill level. (src: siera) |
| `kwera` | double | yes | — | TODO |
| `rs_9` | double | yes | — | TODO |
| `e_f` | double | yes | — | TODO |
| `pull` | int32 | yes | — | TODO |
| `cent` | int32 | yes | — | TODO |
| `oppo` | int32 | yes | — | TODO |
| `soft` | int32 | yes | — | TODO |
| `med` | int32 | yes | — | TODO |
| `hard` | int32 | yes | — | TODO |
| `bipcount` | int32 | yes | — | TODO |
| `pull_` | decimal128(18, 8) | yes | — | TODO |
| `cent_` | decimal128(18, 8) | yes | — | TODO |
| `oppo_` | decimal128(18, 8) | yes | — | TODO |
| `soft_` | decimal128(18, 8) | yes | — | TODO |
| `med_` | decimal128(18, 8) | yes | — | TODO |
| `hard_` | decimal128(18, 8) | yes | — | TODO |
| `k_9_` | double | yes | — | TODO |
| `bb_9_` | double | yes | — | TODO |
| `k_per_bb_plus` | double | yes | — | TODO |
| `h_9_` | double | yes | — | TODO |
| `hr_9_` | double | yes | — | TODO |
| `avg_` | double | yes | — | TODO |
| `whip_` | double | yes | — | TODO |
| `babip_` | double | yes | — | TODO |
| `lob__` | double | yes | — | TODO |
| `k__` | double | yes | — | TODO |
| `bb__` | double | yes | — | TODO |
| `ld__` | double | yes | — | TODO |
| `gb__` | double | yes | — | TODO |
| `fb__` | double | yes | — | TODO |
| `hrfb__` | double | yes | — | TODO |
| `pull__` | double | yes | — | TODO |
| `cent__` | double | yes | — | TODO |
| `oppo__` | double | yes | — | TODO |
| `soft__` | double | yes | — | TODO |
| `med__` | double | yes | — | TODO |
| `hard__` | double | yes | — | TODO |
| `xera` | double | yes | — | TODO |
| `pb_o_ch` | double | yes | — | TODO |
| `pb_s_ch` | double | yes | — | TODO |
| `pb_c_ch` | double | yes | — | TODO |
| `pb_o_cu` | double | yes | — | TODO |
| `pb_s_cu` | double | yes | — | TODO |
| `pb_c_cu` | double | yes | — | TODO |
| `pb_o_ff` | double | yes | — | TODO |
| `pb_s_ff` | double | yes | — | TODO |
| `pb_c_ff` | double | yes | — | TODO |
| `pb_o_si` | double | yes | — | TODO |
| `pb_s_si` | double | yes | — | TODO |
| `pb_c_si` | double | yes | — | TODO |
| `pb_o_sl` | double | yes | — | TODO |
| `pb_s_sl` | double | yes | — | TODO |
| `pb_c_sl` | double | yes | — | TODO |
| `pb_o_kc` | double | yes | — | TODO |
| `pb_s_kc` | double | yes | — | TODO |
| `pb_c_kc` | double | yes | — | TODO |
| `pb_o_fc` | double | yes | — | TODO |
| `pb_s_fc` | double | yes | — | TODO |
| `pb_c_fc` | double | yes | — | TODO |
| `pb_o_fs` | double | yes | — | TODO |
| `pb_s_fs` | double | yes | — | TODO |
| `pb_c_fs` | double | yes | — | TODO |
| `pb_overall` | double | yes | — | TODO |
| `pb_stuff` | double | yes | — | TODO |
| `pb_command` | double | yes | — | TODO |
| `pb_xrv100` | double | yes | — | TODO |
| `pb_era` | double | yes | — | TODO |
| `sp_s_ch` | double | yes | — | TODO |
| `sp_l_ch` | double | yes | — | TODO |
| `sp_p_ch` | double | yes | — | TODO |
| `sp_s_cu` | double | yes | — | TODO |
| `sp_l_cu` | double | yes | — | TODO |
| `sp_p_cu` | double | yes | — | TODO |
| `sp_s_ff` | double | yes | — | TODO |
| `sp_l_ff` | double | yes | — | TODO |
| `sp_p_ff` | double | yes | — | TODO |
| `sp_s_si` | double | yes | — | TODO |
| `sp_l_si` | double | yes | — | TODO |
| `sp_p_si` | double | yes | — | TODO |
| `sp_s_sl` | double | yes | — | TODO |
| `sp_l_sl` | double | yes | — | TODO |
| `sp_p_sl` | double | yes | — | TODO |
| `sp_s_kc` | double | yes | — | TODO |
| `sp_l_kc` | double | yes | — | TODO |
| `sp_p_kc` | double | yes | — | TODO |
| `sp_s_fc` | double | yes | — | TODO |
| `sp_l_fc` | double | yes | — | TODO |
| `sp_p_fc` | double | yes | — | TODO |
| `sp_s_fs` | double | yes | — | TODO |
| `sp_l_fs` | double | yes | — | TODO |
| `sp_p_fs` | double | yes | — | TODO |
| `sp_s_fo` | double | yes | — | TODO |
| `sp_l_fo` | double | yes | — | TODO |
| `sp_p_fo` | double | yes | — | TODO |
| `sp_stuff` | double | yes | — | TODO |
| `sp_location` | double | yes | — | TODO |
| `sp_pitching` | double | yes | — | TODO |
| `pptv` | int32 | yes | — | TODO |
| `cptv` | int32 | yes | — | TODO |
| `bptv` | int32 | yes | — | TODO |
| `dsv` | int32 | yes | — | TODO |
| `dgv` | int32 | yes | — | TODO |
| `btv` | int32 | yes | — | TODO |
| `rpptv` | double | yes | — | TODO |
| `rcptv` | double | yes | — | TODO |
| `rbptv` | double | yes | — | TODO |
| `rdsv` | double | yes | — | TODO |
| `rdgv` | double | yes | — | TODO |
| `rbtv` | double | yes | — | TODO |
| `ebv` | int32 | yes | — | TODO |
| `esv` | int32 | yes | — | TODO |
| `rfteamv` | double | yes | — | TODO |
| `rbteamv` | double | yes | — | TODO |
| `rtv` | double | yes | — | TODO |
| `breview` | int32 | yes | — | TODO |
| `boverturned` | int32 | yes | — | TODO |
| `bcorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wbreview` | double | yes | — | TODO |
| `preview` | int32 | yes | — | TODO |
| `poverturned` | int32 | yes | — | TODO |
| `pcorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wpreview` | double | yes | — | TODO |
| `creview` | int32 | yes | — | TODO |
| `coverturned` | int32 | yes | — | TODO |
| `ccorrect_` | decimal128(18, 8) | yes | — | TODO |
| `wcreview` | double | yes | — | TODO |
| `pfxfa_` | decimal128(18, 8) | yes | — | TODO |
| `pfxft_` | string | yes | — | TODO |
| `pfxfc_` | decimal128(18, 8) | yes | — | TODO |
| `pfxfs_` | decimal128(18, 8) | yes | — | TODO |
| `pfxfo_` | decimal128(18, 8) | yes | — | TODO |
| `pfxsi_` | decimal128(18, 8) | yes | — | TODO |
| `pfxsl_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcu_` | decimal128(18, 8) | yes | — | TODO |
| `pfxkc_` | decimal128(18, 8) | yes | — | TODO |
| `pfxep_` | decimal128(18, 8) | yes | — | TODO |
| `pfxch_` | decimal128(18, 8) | yes | — | TODO |
| `pfxsc_` | decimal128(18, 8) | yes | — | TODO |
| `pfxkn_` | decimal128(18, 8) | yes | — | TODO |
| `pfxun_` | decimal128(18, 8) | yes | — | TODO |
| `pfxslo_` | decimal128(18, 8) | yes | — | TODO |
| `pfxst_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcuo_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcv_` | decimal128(18, 8) | yes | — | TODO |
| `pfxvfa` | double | yes | — | TODO |
| `pfxvft` | string | yes | — | TODO |
| `pfxvfc` | double | yes | — | TODO |
| `pfxvfs` | double | yes | — | TODO |
| `pfxvfo` | double | yes | — | TODO |
| `pfxvsi` | double | yes | — | TODO |
| `pfxvsl` | double | yes | — | TODO |
| `pfxvcu` | double | yes | — | TODO |
| `pfxvkc` | double | yes | — | TODO |
| `pfxvep` | double | yes | — | TODO |
| `pfxvch` | double | yes | — | TODO |
| `pfxvsc` | double | yes | — | TODO |
| `pfxvkn` | double | yes | — | TODO |
| `pfxvslo` | double | yes | — | TODO |
| `pfxvst` | double | yes | — | TODO |
| `pfxvcuo` | double | yes | — | TODO |
| `pfxvcv` | double | yes | — | TODO |
| `pfxfa_x` | double | yes | — | TODO |
| `pfxft_x` | string | yes | — | TODO |
| `pfxfc_x` | double | yes | — | TODO |
| `pfxfs_x` | double | yes | — | TODO |
| `pfxfo_x` | double | yes | — | TODO |
| `pfxsi_x` | double | yes | — | TODO |
| `pfxsl_x` | double | yes | — | TODO |
| `pfxcu_x` | double | yes | — | TODO |
| `pfxkc_x` | double | yes | — | TODO |
| `pfxep_x` | double | yes | — | TODO |
| `pfxch_x` | double | yes | — | TODO |
| `pfxsc_x` | double | yes | — | TODO |
| `pfxkn_x` | double | yes | — | TODO |
| `pfxslo_x` | double | yes | — | TODO |
| `pfxst_x` | double | yes | — | TODO |
| `pfxcuo_x` | double | yes | — | TODO |
| `pfxcv_x` | double | yes | — | TODO |
| `pfxfa_z` | double | yes | — | TODO |
| `pfxft_z` | string | yes | — | TODO |
| `pfxfc_z` | double | yes | — | TODO |
| `pfxfs_z` | double | yes | — | TODO |
| `pfxfo_z` | double | yes | — | TODO |
| `pfxsi_z` | double | yes | — | TODO |
| `pfxsl_z` | double | yes | — | TODO |
| `pfxcu_z` | double | yes | — | TODO |
| `pfxkc_z` | double | yes | — | TODO |
| `pfxep_z` | double | yes | — | TODO |
| `pfxch_z` | double | yes | — | TODO |
| `pfxsc_z` | double | yes | — | TODO |
| `pfxkn_z` | double | yes | — | TODO |
| `pfxslo_z` | double | yes | — | TODO |
| `pfxst_z` | double | yes | — | TODO |
| `pfxcuo_z` | double | yes | — | TODO |
| `pfxcv_z` | double | yes | — | TODO |
| `pfxwfa` | double | yes | — | TODO |
| `pfxwft` | string | yes | — | TODO |
| `pfxwfc` | double | yes | — | TODO |
| `pfxwfs` | double | yes | — | TODO |
| `pfxwfo` | double | yes | — | TODO |
| `pfxwsi` | double | yes | — | TODO |
| `pfxwsl` | double | yes | — | TODO |
| `pfxwcu` | double | yes | — | TODO |
| `pfxwkc` | double | yes | — | TODO |
| `pfxwep` | double | yes | — | TODO |
| `pfxwch` | double | yes | — | TODO |
| `pfxwsc` | double | yes | — | TODO |
| `pfxwkn` | double | yes | — | TODO |
| `pfxwslo` | double | yes | — | TODO |
| `pfxwst` | double | yes | — | TODO |
| `pfxwcuo` | double | yes | — | TODO |
| `pfxwcv` | double | yes | — | TODO |
| `pfxwfa_c` | double | yes | — | TODO |
| `pfxwft_c` | string | yes | — | TODO |
| `pfxwfc_c` | double | yes | — | TODO |
| `pfxwfs_c` | double | yes | — | TODO |
| `pfxwfo_c` | double | yes | — | TODO |
| `pfxwsi_c` | double | yes | — | TODO |
| `pfxwsl_c` | double | yes | — | TODO |
| `pfxwcu_c` | double | yes | — | TODO |
| `pfxwkc_c` | double | yes | — | TODO |
| `pfxwep_c` | double | yes | — | TODO |
| `pfxwch_c` | double | yes | — | TODO |
| `pfxwsc_c` | double | yes | — | TODO |
| `pfxwkn_c` | double | yes | — | TODO |
| `pfxwslo_c` | double | yes | — | TODO |
| `pfxwst_c` | double | yes | — | TODO |
| `pfxwcuo_c` | double | yes | — | TODO |
| `pfxwcv_c` | double | yes | — | TODO |
| `pfxaafa` | double | yes | — | TODO |
| `pfxaaft` | string | yes | — | TODO |
| `pfxaafc` | double | yes | — | TODO |
| `pfxaafs` | double | yes | — | TODO |
| `pfxaafo` | double | yes | — | TODO |
| `pfxaasi` | double | yes | — | TODO |
| `pfxaasl` | double | yes | — | TODO |
| `pfxaacu` | double | yes | — | TODO |
| `pfxaakc` | double | yes | — | TODO |
| `pfxaaep` | double | yes | — | TODO |
| `pfxaach` | double | yes | — | TODO |
| `pfxaasc` | double | yes | — | TODO |
| `pfxaakn` | double | yes | — | TODO |
| `pfxaaslo` | double | yes | — | TODO |
| `pfxaast` | double | yes | — | TODO |
| `pfxaacuo` | double | yes | — | TODO |
| `pfxaacv` | double | yes | — | TODO |
| `pfxspfa` | double | yes | — | TODO |
| `pfxspft` | string | yes | — | TODO |
| `pfxspfc` | double | yes | — | TODO |
| `pfxspfs` | double | yes | — | TODO |
| `pfxspfo` | double | yes | — | TODO |
| `pfxspsi` | double | yes | — | TODO |
| `pfxspsl` | double | yes | — | TODO |
| `pfxspcu` | double | yes | — | TODO |
| `pfxspkc` | double | yes | — | TODO |
| `pfxspep` | double | yes | — | TODO |
| `pfxspch` | double | yes | — | TODO |
| `pfxspsc` | double | yes | — | TODO |
| `pfxspkn` | double | yes | — | TODO |
| `pfxspslo` | double | yes | — | TODO |
| `pfxspst` | double | yes | — | TODO |
| `pfxspcuo` | double | yes | — | TODO |
| `pfxspcv` | double | yes | — | TODO |
| `pfxo_swing_` | decimal128(18, 8) | yes | — | TODO |
| `pfxz_swing_` | decimal128(18, 8) | yes | — | TODO |
| `pfxswing_` | decimal128(18, 8) | yes | — | TODO |
| `pfxo_contact_` | decimal128(18, 8) | yes | — | TODO |
| `pfxz_contact_` | decimal128(18, 8) | yes | — | TODO |
| `pfxcontact_` | decimal128(18, 8) | yes | — | TODO |
| `pfxzone_` | decimal128(18, 8) | yes | — | TODO |
| `pfxpace` | decimal128(18, 8) | yes | — | TODO |
| `avgbatspeed` | double | yes | — | TODO |
| `fastswing_` | decimal128(18, 8) | yes | — | TODO |
| `swinglength` | double | yes | — | TODO |
| `squaredupcontact_` | decimal128(18, 8) | yes | — | TODO |
| `squaredupswing_` | decimal128(18, 8) | yes | — | TODO |
| `blastcontact_` | decimal128(18, 8) | yes | — | TODO |
| `blastswing_` | decimal128(18, 8) | yes | — | TODO |
| `swords` | int32 | yes | — | TODO |
| `competitiveswings` | int32 | yes | — | TODO |
| `tilt` | double | yes | — | TODO |
| `attackangle` | double | yes | — | TODO |
| `attackdirection` | double | yes | — | TODO |
| `idealattackangle_` | decimal128(18, 8) | yes | — | TODO |
| `depthinbox` | double | yes | — | TODO |
| `distanceoffplate` | double | yes | — | TODO |
| `sch_swing_` | decimal128(18, 8) | yes | — | TODO |
| `sch_contact_` | decimal128(18, 8) | yes | — | TODO |
| `sch_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scs_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scs_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scs_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scc_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scc_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scc_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scw_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scw_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scw_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scsi_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scsi_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scsi_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scso_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scso_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scso_zone_` | decimal128(18, 8) | yes | — | TODO |
| `sco_swing_` | decimal128(18, 8) | yes | — | TODO |
| `sco_contact_` | decimal128(18, 8) | yes | — | TODO |
| `sco_zone_` | decimal128(18, 8) | yes | — | TODO |
| `scz_swing_` | decimal128(18, 8) | yes | — | TODO |
| `scz_contact_` | decimal128(18, 8) | yes | — | TODO |
| `scz_zone_` | decimal128(18, 8) | yes | — | TODO |
| `pich_` | decimal128(18, 8) | yes | — | TODO |
| `pics_` | decimal128(18, 8) | yes | — | TODO |
| `picu_` | decimal128(18, 8) | yes | — | TODO |
| `pifa_` | decimal128(18, 8) | yes | — | TODO |
| `pifc_` | decimal128(18, 8) | yes | — | TODO |
| `pifs_` | decimal128(18, 8) | yes | — | TODO |
| `pikn_` | decimal128(18, 8) | yes | — | TODO |
| `pisb_` | decimal128(18, 8) | yes | — | TODO |
| `pisi_` | decimal128(18, 8) | yes | — | TODO |
| `pisl_` | decimal128(18, 8) | yes | — | TODO |
| `pixx_` | decimal128(18, 8) | yes | — | TODO |
| `pivch` | double | yes | — | TODO |
| `pivcs` | double | yes | — | TODO |
| `pivcu` | double | yes | — | TODO |
| `pivfa` | double | yes | — | TODO |
| `pivfc` | double | yes | — | TODO |
| `pivfs` | double | yes | — | TODO |
| `pivkn` | double | yes | — | TODO |
| `pivsb` | double | yes | — | TODO |
| `pivsi` | double | yes | — | TODO |
| `pivsl` | double | yes | — | TODO |
| `pivxx` | double | yes | — | TODO |
| `pich_x` | double | yes | — | TODO |
| `pics_x` | double | yes | — | TODO |
| `picu_x` | double | yes | — | TODO |
| `pifa_x` | double | yes | — | TODO |
| `pifc_x` | double | yes | — | TODO |
| `pifs_x` | double | yes | — | TODO |
| `pikn_x` | double | yes | — | TODO |
| `pisb_x` | double | yes | — | TODO |
| `pisi_x` | double | yes | — | TODO |
| `pisl_x` | double | yes | — | TODO |
| `pixx_x` | double | yes | — | TODO |
| `pich_z` | double | yes | — | TODO |
| `pics_z` | double | yes | — | TODO |
| `picu_z` | double | yes | — | TODO |
| `pifa_z` | double | yes | — | TODO |
| `pifc_z` | double | yes | — | TODO |
| `pifs_z` | double | yes | — | TODO |
| `pikn_z` | double | yes | — | TODO |
| `pisb_z` | double | yes | — | TODO |
| `pisi_z` | double | yes | — | TODO |
| `pisl_z` | double | yes | — | TODO |
| `pixx_z` | double | yes | — | TODO |
| `piwch` | double | yes | — | TODO |
| `piwcs` | double | yes | — | TODO |
| `piwcu` | double | yes | — | TODO |
| `piwfa` | double | yes | — | TODO |
| `piwfc` | double | yes | — | TODO |
| `piwfs` | double | yes | — | TODO |
| `piwkn` | double | yes | — | TODO |
| `piwsb` | double | yes | — | TODO |
| `piwsi` | double | yes | — | TODO |
| `piwsl` | double | yes | — | TODO |
| `piwxx` | double | yes | — | TODO |
| `piwch_c` | double | yes | — | TODO |
| `piwcs_c` | double | yes | — | TODO |
| `piwcu_c` | double | yes | — | TODO |
| `piwfa_c` | double | yes | — | TODO |
| `piwfc_c` | double | yes | — | TODO |
| `piwfs_c` | double | yes | — | TODO |
| `piwkn_c` | double | yes | — | TODO |
| `piwsb_c` | double | yes | — | TODO |
| `piwsi_c` | double | yes | — | TODO |
| `piwsl_c` | double | yes | — | TODO |
| `piwxx_c` | double | yes | — | TODO |
| `pio_swing_` | decimal128(18, 8) | yes | — | TODO |
| `piz_swing_` | decimal128(18, 8) | yes | — | TODO |
| `piswing_` | decimal128(18, 8) | yes | — | TODO |
| `pio_contact_` | decimal128(18, 8) | yes | — | TODO |
| `piz_contact_` | decimal128(18, 8) | yes | — | TODO |
| `picontact_` | decimal128(18, 8) | yes | — | TODO |
| `pizone_` | decimal128(18, 8) | yes | — | TODO |
| `pipace` | decimal128(18, 8) | yes | — | TODO |
| `events` | int32 | yes | — | TODO |
| `ev` | double | yes | — | TODO |
| `la` | double | yes | — | TODO |
| `barrels` | int32 | yes | — | TODO |
| `barrel_` | decimal128(18, 8) | yes | — | TODO |
| `maxev` | decimal128(9, 1) | yes | — | TODO |
| `hardhit` | int32 | yes | — | TODO |
| `hardhit_` | decimal128(18, 8) | yes | — | TODO |
| `q` | double | yes | — | TODO |
| `tg` | decimal128(18, 8) | yes | — | TODO |
| `tip` | double | yes | — | TODO |
| `playernameroute` | string | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `positiondb` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `teamname` | string | yes | — | TODO |
| `teamnameabb` | string | yes | — | TODO |
| `teamid` | int32 | yes | — | TODO |
| `playerteamid` | int32 | yes | — | TODO |
| `playerid` | int32 | yes | — | TODO |
| `ev90` | decimal128(9, 1) | yes | — | TODO |
| `_season` | int32 | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.pitching -->

<!-- BEGIN GENERATED:fangraphs.projection -->
### Dataset: projection

FanGraphs projection snapshots (private research data): a row per system, player, capture date and change.

- **View:** `fangraphs_projection`
- **Processed path:** `processed/fangraphs/projection/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerid`, `_projection_system`, `_stat_group`, `_horizon`, `_captured_date`, `_row_hash`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `team` | string | yes | — | TODO |
| `shortname` | string | yes | — | TODO |
| `g` | decimal128(18, 5) | yes | — | TODO |
| `ab` | decimal128(18, 6) | yes | — | TODO |
| `pa` | decimal128(18, 7) | yes | — | TODO |
| `h` | decimal128(18, 8) | yes | — | TODO |
| `n1b` | decimal128(18, 7) | yes | — | TODO |
| `n2b` | decimal128(18, 8) | yes | — | TODO |
| `n3b` | double | yes | — | TODO |
| `hr` | double | yes | — | TODO |
| `r` | decimal128(18, 7) | yes | — | TODO |
| `rbi` | decimal128(18, 7) | yes | — | TODO |
| `bb` | double | yes | — | TODO |
| `ibb` | double | yes | — | TODO |
| `so` | decimal128(18, 8) | yes | — | TODO |
| `hbp` | double | yes | — | TODO |
| `sf` | decimal128(18, 8) | yes | — | TODO |
| `sh` | double | yes | — | TODO |
| `gdp` | decimal128(18, 8) | yes | — | TODO |
| `sb` | double | yes | — | TODO |
| `cs` | double | yes | — | TODO |
| `avg` | decimal128(18, 7) | yes | — | TODO |
| `obp` | decimal128(18, 7) | yes | — | TODO |
| `slg` | decimal128(18, 6) | yes | — | TODO |
| `ops` | decimal128(18, 6) | yes | — | TODO |
| `woba` | decimal128(18, 6) | yes | — | Weighted On-Base Average: combines all the different aspects of hitting into one metric. (src: woba) |
| `bb_` | decimal128(18, 7) | yes | — | Walk rate: the share of plate appearances that end in a walk (BB / PA). (src: rate_stats) |
| `k_` | decimal128(18, 8) | yes | — | Strikeout rate: the share of plate appearances that end in a strikeout (K / PA). (src: rate_stats) |
| `bb_k` | decimal128(18, 7) | yes | — | TODO |
| `iso` | decimal128(18, 7) | yes | — | Isolated Power: a measure of a hitter's raw power, how often a player hits for extra bases. (src: iso) |
| `spd` | decimal128(18, 6) | yes | — | Speed Score: a Bill James statistic that rates a player on speed and baserunning ability. (src: spd) |
| `babip` | decimal128(18, 7) | yes | — | Batting Average on Balls In Play: how often a ball in play goes for a hit. (src: babip) |
| `ubr` | double | yes | — | Ultimate Base Running: the value a player adds through base running on non-stolen-base plays. (src: ubr) |
| `gdpruns` | string | yes | — | TODO |
| `wrc` | double | yes | — | Weighted Runs Created: an improved version of Bill James' Runs Created, in runs. (src: wrc) |
| `wraa` | double | yes | — | Weighted Runs Above Average: the non-park-adjusted version of Batting Runs. (src: woba) |
| `uzr` | double | yes | — | Ultimate Zone Rating: puts a run value to defense. (src: uzr) |
| `wbsr` | double | yes | — | TODO |
| `baserunning` | double | yes | — | TODO |
| `war` | double | yes | — | Wins Above Replacement: an attempt to summarize a player's total contributions to the team. (src: war) |
| `off` | double | yes | — | TODO |
| `def` | double | yes | — | TODO |
| `wrc_` | double | yes | — | wRC+: how a player's wRC compares with league average after controlling for park effects. (src: wrc) |
| `fpts` | double | yes | — | TODO |
| `fpts_g` | double | yes | — | TODO |
| `spts` | double | yes | — | TODO |
| `spts_g` | double | yes | — | TODO |
| `woba_sd` | decimal128(18, 6) | yes | — | TODO |
| `truetalent_sd` | decimal128(18, 7) | yes | — | TODO |
| `woba_sd_book` | decimal128(18, 6) | yes | — | TODO |
| `woba_se` | decimal128(18, 7) | yes | — | TODO |
| `total_se` | decimal128(18, 7) | yes | — | TODO |
| `q10` | decimal128(18, 5) | yes | — | TODO |
| `q20` | decimal128(18, 5) | yes | — | TODO |
| `q30` | decimal128(18, 5) | yes | — | TODO |
| `q40` | decimal128(18, 5) | yes | — | TODO |
| `q50` | decimal128(18, 5) | yes | — | TODO |
| `q60` | decimal128(18, 5) | yes | — | TODO |
| `q70` | decimal128(18, 5) | yes | — | TODO |
| `q80` | decimal128(18, 5) | yes | — | TODO |
| `q90` | decimal128(18, 5) | yes | — | TODO |
| `tt_q10` | decimal128(18, 5) | yes | — | TODO |
| `tt_q20` | decimal128(18, 5) | yes | — | TODO |
| `tt_q30` | decimal128(18, 5) | yes | — | TODO |
| `tt_q40` | decimal128(18, 5) | yes | — | TODO |
| `tt_q50` | decimal128(18, 5) | yes | — | TODO |
| `tt_q60` | decimal128(18, 5) | yes | — | TODO |
| `tt_q70` | decimal128(18, 5) | yes | — | TODO |
| `tt_q80` | decimal128(18, 5) | yes | — | TODO |
| `tt_q90` | decimal128(18, 5) | yes | — | TODO |
| `adp` | double | yes | — | TODO |
| `pos` | decimal128(18, 8) | yes | — | TODO |
| `minpos` | string | yes | — | TODO |
| `upurl` | string | yes | — | TODO |
| `positiondb` | string | yes | — | TODO |
| `teamid` | int32 | yes | — | TODO |
| `playerteamid` | int32 | yes | — | TODO |
| `league` | string | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `xmlbamid` | int32 | yes | — | TODO |
| `playerids` | string | yes | — | TODO |
| `playerid` | string | yes | — | TODO |
| `_projection_system` | string | yes | — | TODO |
| `_stat_group` | string | yes | — | TODO |
| `_horizon` | string | yes | — | TODO |
| `_captured_date` | date32[day] | yes | — | TODO |
| `_row_hash` | string | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `w` | decimal128(18, 8) | yes | — | TODO |
| `l` | double | yes | — | TODO |
| `gs` | double | yes | — | TODO |
| `sv` | double | yes | — | TODO |
| `hld` | decimal128(18, 7) | yes | — | TODO |
| `bs` | decimal128(18, 7) | yes | — | TODO |
| `ip` | decimal128(18, 6) | yes | — | TODO |
| `tbf` | decimal128(18, 7) | yes | — | TODO |
| `er` | decimal128(18, 5) | yes | — | TODO |
| `era` | decimal128(18, 5) | yes | — | TODO |
| `whip` | decimal128(18, 6) | yes | — | TODO |
| `k_9` | decimal128(18, 6) | yes | — | TODO |
| `bb_9` | decimal128(18, 5) | yes | — | TODO |
| `k_bb` | decimal128(18, 7) | yes | — | TODO |
| `hr_9` | decimal128(18, 6) | yes | — | TODO |
| `k_minus_bb_pct` | double | yes | — | TODO |
| `gb_` | decimal128(18, 6) | yes | — | Ground Ball Percentage: ground balls divided by balls in play. (src: batted_ball) |
| `lob_` | decimal128(18, 6) | yes | — | Left On Base Percentage: the percentage of base runners a pitcher strands on base. (src: lob) |
| `fip` | decimal128(18, 5) | yes | — | Fielding Independent Pitching: what a pitcher's ERA would look like with typical results on balls in play. (src: fip) |
| `fpts_ip` | double | yes | — | TODO |
| `spts_ip` | double | yes | — | TODO |
| `ra9_war` | double | yes | — | TODO |
| `qs` | decimal128(18, 8) | yes | — | TODO |
| `ra_talent_sd` | decimal128(18, 6) | yes | — | TODO |
| `chance_ra_se` | decimal128(18, 6) | yes | — | TODO |
| `total_ra_se` | decimal128(18, 6) | yes | — | TODO |
| `intersd` | decimal128(18, 6) | yes | — | TODO |
| `intersk` | decimal128(18, 8) | yes | — | TODO |
| `intrasd` | decimal128(18, 6) | yes | — | TODO |
| `vol` | decimal128(18, 6) | yes | — | TODO |
| `skew` | decimal128(18, 8) | yes | — | TODO |
| `dim` | decimal128(18, 5) | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.projection -->

<!-- BEGIN GENERATED:fangraphs.prospects -->
### Dataset: prospects

FanGraphs prospect board (private research data): scouting grades per player and season.

- **View:** `fangraphs_prospects`
- **Processed path:** `processed/fangraphs/prospects/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `season`, `playerid`, `minormasterid`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `llevel` | string | yes | — | TODO |
| `mlevel` | string | yes | — | TODO |
| `minormasterid` | string | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `playernameroute` | string | yes | — | TODO |
| `upurl` | string | yes | — | TODO |
| `upid` | string | yes | — | TODO |
| `positiondb` | string | yes | — | TODO |
| `playerteamid` | int32 | yes | — | TODO |
| `rpm` | string | yes | — | TODO |
| `crisk` | string | yes | — | TODO |
| `ceta` | int32 | yes | — | TODO |
| `cfv` | string | yes | — | TODO |
| `cweight` | int32 | yes | — | TODO |
| `cheight` | string | yes | — | TODO |
| `covr` | int32 | yes | — | TODO |
| `corg` | int32 | yes | — | TODO |
| `ctrend` | string | yes | — | TODO |
| `cdraftschool` | string | yes | — | TODO |
| `hit` | string | yes | — | TODO |
| `game` | string | yes | — | TODO |
| `raw` | string | yes | — | TODO |
| `spd` | string | yes | — | Speed Score: a Bill James statistic that rates a player on speed and baserunning ability. (src: spd) |
| `fld` | string | yes | — | TODO |
| `fb` | string | yes | — | TODO |
| `sl` | string | yes | — | TODO |
| `cb` | string | yes | — | TODO |
| `ch` | string | yes | — | TODO |
| `spl` | string | yes | — | TODO |
| `ct` | string | yes | — | TODO |
| `cmd` | string | yes | — | TODO |
| `cseason` | int32 | yes | — | TODO |
| `playerpagesortorder` | int32 | yes | — | TODO |
| `ccollegecommit` | string | yes | — | TODO |
| `id` | int32 | yes | — | TODO |
| `firstname` | string | yes | — | TODO |
| `lastname` | string | yes | — | TODO |
| `position` | string | yes | — | TODO |
| `age` | decimal128(18, 8) | yes | — | TODO |
| `team` | string | yes | — | TODO |
| `season` | int32 | yes | — | TODO |
| `type` | string | yes | — | TODO |
| `playerid` | string | yes | — | TODO |
| `ovr_rank` | int32 | yes | — | TODO |
| `org_rank` | int32 | yes | — | TODO |
| `fv_current` | int32 | yes | — | TODO |
| `eta_current` | int32 | yes | — | TODO |
| `height` | int32 | yes | — | TODO |
| `weight` | int32 | yes | — | TODO |
| `bats` | string | yes | — | TODO |
| `throws` | string | yes | — | TODO |
| `school` | string | yes | — | TODO |
| `summary` | string | yes | — | TODO |
| `youtube` | string | yes | — | TODO |
| `phit` | int32 | yes | — | TODO |
| `fhit` | int32 | yes | — | TODO |
| `pgame` | int32 | yes | — | TODO |
| `fgame` | int32 | yes | — | TODO |
| `praw` | int32 | yes | — | TODO |
| `fraw` | int32 | yes | — | TODO |
| `pspd` | int32 | yes | — | TODO |
| `fspd` | int32 | yes | — | TODO |
| `pfld` | int32 | yes | — | TODO |
| `ffld` | int32 | yes | — | TODO |
| `parm` | int32 | yes | — | TODO |
| `variance` | string | yes | — | TODO |
| `birthdate` | int32 | yes | — | TODO |
| `tldr` | string | yes | — | TODO |
| `athleticism` | int32 | yes | — | TODO |
| `frame` | int32 | yes | — | TODO |
| `performer` | int32 | yes | — | TODO |
| `ovr_summary` | string | yes | — | TODO |
| `dist_raw` | string | yes | — | TODO |
| `player_type` | string | yes | — | TODO |
| `signed_yr` | int32 | yes | — | TODO |
| `signed_mkt` | string | yes | — | TODO |
| `signed_org` | string | yes | — | TODO |
| `draft_rnd` | int32 | yes | — | TODO |
| `sign_bonus` | int32 | yes | — | TODO |
| `school_type` | string | yes | — | TODO |
| `hs_state` | string | yes | — | TODO |
| `college_commit` | string | yes | — | TODO |
| `country` | string | yes | — | TODO |
| `pitch_sel` | int32 | yes | — | TODO |
| `bat_ctrl` | int32 | yes | — | TODO |
| `fantasy_redraft` | int32 | yes | — | TODO |
| `fantasy_dynasty` | int32 | yes | — | TODO |
| `fypd_eligible` | string | yes | — | TODO |
| `levers` | string | yes | — | TODO |
| `options` | string | yes | — | TODO |
| `servicetime` | decimal128(9, 3) | yes | — | TODO |
| `amateur_rk` | int32 | yes | — | TODO |
| `trend` | string | yes | — | TODO |
| `vel` | int32 | yes | — | TODO |
| `arm` | string | yes | — | TODO |
| `pfb` | int32 | yes | — | TODO |
| `ffb` | int32 | yes | — | TODO |
| `psl` | int32 | yes | — | TODO |
| `fsl` | int32 | yes | — | TODO |
| `pch` | int32 | yes | — | TODO |
| `fch` | int32 | yes | — | TODO |
| `pspl` | int32 | yes | — | TODO |
| `fspl` | int32 | yes | — | TODO |
| `pct` | int32 | yes | — | TODO |
| `fct` | int32 | yes | — | TODO |
| `pcmd` | int32 | yes | — | TODO |
| `fcmd` | int32 | yes | — | TODO |
| `range` | string | yes | — | TODO |
| `touch` | int32 | yes | — | TODO |
| `fbtype` | string | yes | — | TODO |
| `isvisible` | string | yes | — | TODO |
| `pcb` | int32 | yes | — | TODO |
| `fcb` | int32 | yes | — | TODO |
| `brpm` | int32 | yes | — | TODO |
| `frpm` | int32 | yes | — | TODO |
| `delivery` | int32 | yes | — | TODO |
| `agent` | string | yes | — | TODO |
| `tjdate` | string | yes | — | TODO |
| `bonus_class_rk` | int32 | yes | — | TODO |
| `pos_rk` | int32 | yes | — | TODO |
| `_season` | int32 | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `crank` | string | yes | — | TODO |
| `rowid` | int32 | yes | — | TODO |
| `draftrank` | int32 | yes | — | TODO |
| `projteam` | string | yes | — | TODO |
| `risk_current` | int32 | yes | — | TODO |
| `draft` | string | yes | — | TODO |
| `collegecommit` | string | yes | — | TODO |
| `farm` | int32 | yes | — | TODO |
| `avg_ev` | int32 | yes | — | TODO |
| `max_ev` | int32 | yes | — | TODO |
| `birth_yr_rk` | int32 | yes | — | TODO |
| `class_rk` | int32 | yes | — | TODO |
| `hardhit_` | decimal128(9, 3) | yes | — | TODO |
| `versatility` | string | yes | — | TODO |
| `contact_style` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.prospects -->

<!-- BEGIN GENERATED:fangraphs.split_batting -->
### Dataset: split_batting

FanGraphs batting split leaderboards (private research data): a curated set of splits per season.

- **View:** `fangraphs_split_batting`
- **Processed path:** `processed/fangraphs/split_batting/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerid`, `season`, `_split`, `_scope`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season` | int32 | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `playerid` | int32 | yes | — | TODO |
| `teamnameabb` | string | yes | — | TODO |
| `pa` | int32 | yes | — | TODO |
| `avg` | double | yes | — | TODO |
| `bb_` | double | yes | — | Walk rate: the share of plate appearances that end in a walk (BB / PA). (src: rate_stats) |
| `k_` | double | yes | — | Strikeout rate: the share of plate appearances that end in a strikeout (K / PA). (src: rate_stats) |
| `bb_k` | double | yes | — | TODO |
| `obp` | double | yes | — | TODO |
| `slg` | double | yes | — | TODO |
| `ops` | double | yes | — | TODO |
| `iso` | double | yes | — | Isolated Power: a measure of a hitter's raw power, how often a player hits for extra bases. (src: iso) |
| `babip` | double | yes | — | Batting Average on Balls In Play: how often a ball in play goes for a hit. (src: babip) |
| `wrc` | double | yes | — | Weighted Runs Created: an improved version of Bill James' Runs Created, in runs. (src: wrc) |
| `wraa` | double | yes | — | Weighted Runs Above Average: the non-park-adjusted version of Batting Runs. (src: woba) |
| `woba` | double | yes | — | Weighted On-Base Average: combines all the different aspects of hitting into one metric. (src: woba) |
| `wrc_` | double | yes | — | wRC+: how a player's wRC compares with league average after controlling for park effects. (src: wrc) |
| `_season` | int32 | yes | — | TODO |
| `_split` | string | yes | — | TODO |
| `_scope` | string | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.split_batting -->

<!-- BEGIN GENERATED:fangraphs.split_pitching -->
### Dataset: split_pitching

FanGraphs pitching split leaderboards (private research data): a curated set of splits per season.

- **View:** `fangraphs_split_pitching`
- **Processed path:** `processed/fangraphs/split_pitching/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerid`, `season`, `_split`, `_scope`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `season` | int32 | yes | — | TODO |
| `playername` | string | yes | — | TODO |
| `playerid` | int32 | yes | — | TODO |
| `teamnameabb` | string | yes | — | TODO |
| `ip` | decimal128(9, 1) | yes | — | TODO |
| `tbf` | int32 | yes | — | TODO |
| `avg` | double | yes | — | TODO |
| `k_9` | decimal128(18, 8) | yes | — | TODO |
| `bb_9` | decimal128(18, 8) | yes | — | TODO |
| `k_bb` | decimal128(18, 8) | yes | — | TODO |
| `hr_9` | decimal128(18, 8) | yes | — | TODO |
| `k_` | decimal128(18, 8) | yes | — | Strikeout rate: the share of plate appearances that end in a strikeout (K / PA). (src: rate_stats) |
| `bb_` | decimal128(18, 8) | yes | — | Walk rate: the share of plate appearances that end in a walk (BB / PA). (src: rate_stats) |
| `k_minus_bb_pct` | decimal128(18, 8) | yes | — | TODO |
| `whip` | decimal128(18, 8) | yes | — | TODO |
| `babip` | decimal128(18, 8) | yes | — | Batting Average on Balls In Play: how often a ball in play goes for a hit. (src: babip) |
| `lob_` | decimal128(18, 8) | yes | — | Left On Base Percentage: the percentage of base runners a pitcher strands on base. (src: lob) |
| `xfip` | double | yes | — | Expected FIP: a regressed version of FIP that uses the league-average HR/FB rate on fly balls. (src: xfip) |
| `fip` | double | yes | — | Fielding Independent Pitching: what a pitcher's ERA would look like with typical results on balls in play. (src: fip) |
| `_season` | int32 | yes | — | TODO |
| `_split` | string | yes | — | TODO |
| `_scope` | string | yes | — | TODO |
| `_loaded_at` | timestamp[us, tz=UTC] | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:fangraphs.split_pitching -->
