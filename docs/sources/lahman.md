# SABR Lahman Baseball Database Endpoint & Schema Catalog (1871–2025)

## Upstream Overview
- **Provider:** Society for American Baseball Research (SABR) & Sean Lahman
- **Historical Scope:** 1871 through 2025 Major League Baseball seasons
- **Format:** 27 relational CSV tables
- **Official SABR Page:** `https://sabr.org/lahman-database/`
- **Licence:** Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0); copyright 1996-2025 SABR, donated by Sean Lahman; licensing questions to SABR (see `docs/DATA_LICENSES.md`). ShareAlike applies to adaptations: copies you export (Parquet, CSV, DuckDB, PostgreSQL) and share further carry the same licence and the attribution.
- **Automated Mirror:** `https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/<pinned sha>/data/` (the repository also ships `data/readme2025.txt`, the release's data dictionary, plus `LICENSE` and `README.md`; all three are kept in `raw/lahman/documents/` with their hashes)
- **Why Automated Scrapers Fail on SABR Box:** The official download link on SABR routes through `sabr.app.box.com`, which requires ephemeral session cookies and interactive verification. Direct HTTP scripts hitting Box break.
- **baseballpy Dual-Mode Solution:**
  1. **Mode A (Automated Extraction):** Direct zero-configuration download from the verified GitHub repository `cbwinslow/lahman-database-csv`, containing the complete 1871–2025 SABR release with 27 tables.
  2. **Mode B (Manual Local Import):** A built-in helper `lahman.import_archive(path)` allowing users to supply an official `.zip` or unzipped folder downloaded manually from SABR Box. The helper copies the raw CSVs into `~/.baseballpy/raw/lahman/<Table>/<Table>.csv` and compiles them immediately into strongly-typed Parquet tables at `~/.baseballpy/processed/lahman/<Table>/part-data.parquet`.

---

## How to Manually Import from the Official SABR Box Page

If you prefer to download the official distribution directly from SABR:
1. Visit the [SABR Lahman Database Download Page](https://sabr.org/lahman-database/).
2. Click the link for the **Comma-delimited version (`.zip`)** hosted on Box.
3. Download the file (e.g. `lahman-2025-csv.zip`) to your machine.
4. Run the one-line import in Python:
   ```python
   import baseballpy as bb
   from baseballpy.sources.lahman import import_archive

   # Point to your downloaded zip or unzipped folder:
   count = import_archive("~/Downloads/lahman-2025-csv.zip")
   print(f"Successfully compiled and cached {count} Lahman tables into Parquet!")
   ```
5. All subsequent calls to `bb.lahman.batting()`, `bb.lahman.pitching()`, etc., will now load directly from your local Parquet cache without network access!

What the import keeps (`LahmanSource().last_import` lists it): the 27 known tables are typed into Parquet; the release's README, licence and data dictionary are kept in `raw/lahman/documents/`; a CSV that is not one of the 27 tables is kept as raw bytes only (with a warning), never turned into an unregistered table; other file types are ignored. Supplied files carry a content fingerprint and stay authoritative until you refresh them. If you import only part of a release and the rest is later fetched from the mirror, a warning says the tables may come from two different releases.

---

## All 27 Supported Tables

| Table Name | Enum (`LahmanTable`) | Domain Coverage |
| :--- | :--- | :--- |
| `Batting` | `LahmanTable.BATTING` | Regular season batting statistics (AB, H, 2B, 3B, HR, RBI, SB, BB, SO) |
| `Pitching` | `LahmanTable.PITCHING` | Regular season pitching statistics (W, L, ERA, IPouts, SO, BB, CG, SHO) |
| `People` | `LahmanTable.PEOPLE` | Master biographical registry (birth/death dates, heights, weights, bats/throws) |
| `Teams` | `LahmanTable.TEAMS` | Team records, standings, home games, park names, attendance, and park factors |
| `Fielding` | `LahmanTable.FIELDING` | Fielding statistics by position (PO, A, E, DP, PB, InnOuts) |
| `Salaries` | `LahmanTable.SALARIES` | Player salaries by team and season |
| `HallOfFame` | `LahmanTable.HALL_OF_FAME` | Hall of Fame voting ballots, votes received, inductee status |
| `AllstarFull` | `LahmanTable.ALLSTAR_FULL` | All-Star Game roster appearances, game IDs, starting positions |
| `Appearances` | `LahmanTable.APPEARANCES` | Player appearances across all fielding positions in a season |
| `BattingPost` | `LahmanTable.BATTING_POST` | Postseason batting statistics |
| `PitchingPost` | `LahmanTable.PITCHING_POST` | Postseason pitching statistics |
| `FieldingPost` | `LahmanTable.FIELDING_POST` | Postseason fielding statistics |
| `FieldingOF` | `LahmanTable.FIELDING_OF` | Outfielder specific statistics (LF, CF, RF) |
| `FieldingOFsplit` | `LahmanTable.FIELDING_OF_SPLIT`| Outfield positional split breakdowns |
| `Managers` | `LahmanTable.MANAGERS` | Managerial season win-loss records and rank |
| `ManagersHalf` | `LahmanTable.MANAGERS_HALF` | Split-season managerial records (1892, 1981) |
| `Parks` | `LahmanTable.PARKS` | Ballpark codes, names, city, state, countries |
| `HomeGames` | `LahmanTable.HOME_GAMES` | Home games scheduled and played by team and park |
| `AwardsPlayers` | `LahmanTable.AWARDS_PLAYERS` | Major player awards (MVP, Cy Young, Gold Glove, Silver Slugger) |
| `AwardsManagers` | `LahmanTable.AWARDS_MANAGERS` | Manager of the Year awards |
| `AwardsSharePlayers` | `LahmanTable.AWARDS_SHARE_PLAYERS`| Player award vote shares and points |
| `AwardsShareManagers`| `LahmanTable.AWARDS_SHARE_MANAGERS`| Manager award vote shares and points |
| `CollegePlaying` | `LahmanTable.COLLEGE_PLAYING` | Collegiate baseball playing records and years |
| `Schools` | `LahmanTable.SCHOOLS` | Colleges and universities attended by players |
| `SeriesPost` | `LahmanTable.SERIES_POST` | Postseason series outcomes and rounds |
| `TeamsFranchises` | `LahmanTable.TEAMS_FRANCHISES`| Franchise history and lineage |
| `TeamsHalf` | `LahmanTable.TEAMS_HALF` | Split season division finishes |

---

## Sources, pinning and data quality
- **Allowed sources only:** the configured remote repository (default `cbwinslow/lahman-database-csv`, pinned commit in `src/baseballpy/core/sources_lock.json`; override the repo with `BASEBALLPY_LAHMAN_REPO` and the ref with `BASEBALLPY_LAHMAN_REF`) or user-supplied data via `import_archive`. `chadwickbureau/baseballdatabank` is refused outright (its data stops around 2023) and there is **no automatic fallback** to any other repository: if the remote fails after retries a `LahmanSourceError` names `import_archive` as the alternative.
- **Provenance:** every raw file has exactly one entry in `raw/lahman/<Table>/manifest.json` (key `<Table>.csv`): sha256, size, data-row count, `origin` (`<repo>@<sha>` or `local-import`), `source_ref` and the provider's fingerprint (the git blob SHA of `data/<Table>.csv`; supplied files get a content sha256).
- **Currency (ADR 43), at both cache tiers:** a raw file is current when its stored git blob SHA equals the one the pinned tree lists (the tree is saved in `cache/http/github-tree/`, so a pinned lake works offline; with no tree the pinned commit decides). The processed Parquet is current only when it was built from the raw file we hold (its manifest records that fingerprint). Move the pin (`BASEBALLPY_LAHMAN_REF` or the lock) and only the files whose blob changed are downloaded and rebuilt. User-supplied tables are never overwritten by remote cache invalidation. `baseballpy cache check --upstream --source lahman` compares the stored blob SHAs with the latest tree of the mirror.
- **Documents kept:** `README.md`, `LICENSE` and `data/readme*.txt` of the mirror are stored in `raw/lahman/documents/` (the data dictionary is renamed every release year, hence the pattern).
- **Stale-data warning:** if the newest `yearID` in `Batting`/`Teams` is more than one season behind the last completed MLB season, a warning is logged and kept in the processed manifest (`quality.stale`).
- **Data-quality checks (warnings, never errors):** primary-key uniqueness and the relationships between tables (`playerID` in `People`; `yearID`+`teamID` in `Teams`; `Teams.franchID` in `TeamsFranchises`; `HomeGames.parkkey` in `Parks`; `CollegePlaying.schoolID` in `Schools`; rows with an empty id are not orphans) are checked whenever a table is stored, and again for the tables that point into a parent when that parent is stored later, so the result does not depend on load order. Findings are logged, stored in the processed manifest (`quality`) and printed by `baseballpy catalog status` (also in `--json`). On the 2025 release exactly one finding exists: 5 `AllstarFull` rows whose (`yearID`, `teamID`) has no `Teams` row.
- **Safe imports:** `import_archive` rejects zip members with path traversal (`..`) and members/archives beyond 512 MB / 2 GB; raw files are written atomically and untouched (byte-for-byte, BOM included).

## Schemas
All 27 schemas are **generated from the real headers** (`scripts/gen_schemas.py lahman`) and committed in `sources/lahman/tables.py`; column types are inferred over the full release with conservative narrowing (integers are `int16` only when every value is within ±20,000, otherwise `int32`/`int64`; ISO dates are `date32`). Columns are matched by **header name**, so order never matters, and any column added upstream is preserved as JSON in the trailing `_extras` column with a one-time `schema_drift` warning.

Quirks verified on the 2025 release:
- `People.csv`, `Parks.csv`, `Batting.csv` start with a UTF-8 BOM; it is stripped from the first header.
- `People` and `Parks` carry a surrogate `ID` column; `HomeGames` uses `yearkey/leaguekey/teamkey/parkkey` instead of `yearID/lgID/teamID`; `HallOfFame` spells its year column `yearid`.
- `lgID` code `NA` (National Association, 1871–75) is real data, not NULL. The data dictionary says missing values are NULL, never zero.
- `FieldingOFsplit.WP` and `FieldingOFsplit.ZR` exist in the file but are empty in every row.
- **Keys with empty values:** `AllstarFull` (`gameNum`, `gameID`), `AwardsPlayers` (`notes`) and `CollegePlaying` (`yearID`) have key columns that can be empty, so `baseballpy export --mode merge` is refused for those three tables (the other 24 can merge); use replace or append there.
- **Names the data dictionary does not define:** 11 columns have no description because `readme2025.txt` documents other names for them (`Schools`: it documents `schoolName`, `schoolCity`, `schoolState`, the files carry `name_full`, `city`, `state`, `country`) or none (`Parks.ID`, `Teams.teamIDlahman45`, `FieldingOFsplit.PB/WP/SB/CS/ZR`). They are left undescribed rather than guessed; the dictionary is cited at the pinned commit.
- **Against the Chadwick register** (2025 release): 99.94% of `People.bbrefID` and 99.85% of `People.retroID` values match a Chadwick `key_bbref` / `key_retro`; 4 people (`smither02`, `smithge05`, `hughesa01`, `williwo03`) have a `bbrefID` and a `retroID` that point at two different Chadwick persons, and 14 `bbrefID` and 36 `retroID` values have no Chadwick row. `People` has no MLBAM id; go through Chadwick for it.
- Table names ignore letter case everywhere (`batting` finds `Batting`); the data dictionary spells a few differently from the files (`AllStarFull`, `HallofFame`, `TeamFranchises`).
- Documented primary keys (uniqueness verified on the full data): `AllstarFull` (`playerID, yearID, gameNum, gameID, teamID, lgID`), `AwardsPlayers` (`playerID, awardID, yearID, lgID, notes`), `Appearances` (`yearID, teamID, playerID`), `Batting`/`Pitching` (`playerID, yearID, stint`), `Fielding` (`playerID, yearID, stint, POS`), `Teams` (`yearID, lgID, teamID`) and so on — see the generated per-table blocks below.

The generated column dictionaries for all 27 tables follow (regenerate with `baseballpy docs generate`).

## Python API Usage

Any of the 27 tables is one call: `lahman.table("Batting")` (any letter case; `lahman.tables()` lists the names; the named functions below remain). A table is read once per process and reused until its Parquet changes, so repeated calls are free.

```python
from baseballpy.sources.lahman import (
    batting,
    pitching,
    people,
    teams,
    salaries,
    hall_of_fame,
    LahmanSource,
    LahmanTable,
)

# 1. Direct function calls (auto-fetches and caches as Parquet)
batting_df = batting()
print(f"Total historical batting lines: {len(batting_df)}")

# 2. Query specific tables via LahmanSource
source = LahmanSource()
teams_table = source.get_table(LahmanTable.TEAMS)

# 3. Fast Zero-Copy DuckDB Analysis
import duckdb

con = duckdb.connect()
con.register("batting", batting_df)
top_hr_seasons = con.execute("""
    SELECT playerID, yearID, teamID, HR, RBI, SB 
    FROM batting 
    WHERE HR >= 50 
    ORDER BY HR DESC 
    LIMIT 5
""").fetchdf()
print(top_hr_seasons)
```

## Dataset reference (generated)

<!-- BEGIN GENERATED:lahman.description_sources -->
### Description sources

- `lahman_readme`: https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/0377e0b8d3f1b8f6710cc4faee7d842d0e81f344/data/readme2025.txt

<!-- END GENERATED:lahman.description_sources -->

<!-- BEGIN GENERATED:lahman.AllstarFull -->
### Dataset: AllstarFull

Lahman AllstarFull table.

- **View:** `lahman_allstarfull`
- **Processed path:** `processed/lahman/AllstarFull/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `gameNum`, `gameID`, `teamID`, `lgID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `gameNum` | int16 | yes | — | Game number (zero if only one All-Star game played that season) (src: lahman_readme) |
| `gameID` | string | yes | — | Retrosheet ID for the game (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `GP` | int16 | yes | — | 1 if Played in the game (src: lahman_readme) |
| `startingPos` | string | yes | — | If player was game starter, the position played, can have multiple positions listed (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.AllstarFull -->

<!-- BEGIN GENERATED:lahman.Appearances -->
### Dataset: Appearances

Lahman Appearances table.

- **View:** `lahman_appearances`
- **Processed path:** `processed/lahman/Appearances/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `teamID`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `G_all` | int16 | yes | — | Total games played (src: lahman_readme) |
| `GS` | int16 | yes | — | Games started (src: lahman_readme) |
| `G_batting` | int16 | yes | — | Games in which player batted (src: lahman_readme) |
| `G_defense` | int16 | yes | — | Games in which player appeared on defense (src: lahman_readme) |
| `G_p` | int16 | yes | — | Games as pitcher (src: lahman_readme) |
| `G_c` | int16 | yes | — | Games as catcher (src: lahman_readme) |
| `G_1b` | int16 | yes | — | Games as first baseman (src: lahman_readme) |
| `G_2b` | int16 | yes | — | Games as second baseman (src: lahman_readme) |
| `G_3b` | int16 | yes | — | Games as third baseman (src: lahman_readme) |
| `G_ss` | int16 | yes | — | Games as shortstop (src: lahman_readme) |
| `G_lf` | int16 | yes | — | Games as left fielder (src: lahman_readme) |
| `G_cf` | int16 | yes | — | Games as center fielder (src: lahman_readme) |
| `G_rf` | int16 | yes | — | Games as right fielder (src: lahman_readme) |
| `G_of` | int16 | yes | — | Games as outfielder (if a player appeared in a single game at multiple OF positions, this will count as one g_OF game) (src: lahman_readme) |
| `G_dh` | int16 | yes | — | Games as designated hitter (src: lahman_readme) |
| `G_ph` | int16 | yes | — | Games as pinch hitter (src: lahman_readme) |
| `G_pr` | int16 | yes | — | Games as pinch runner (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Appearances -->

<!-- BEGIN GENERATED:lahman.AwardsManagers -->
### Dataset: AwardsManagers

Lahman AwardsManagers table.

- **View:** `lahman_awardsmanagers`
- **Processed path:** `processed/lahman/AwardsManagers/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `awardID`, `yearID`, `lgID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Manager ID code (src: lahman_readme) |
| `awardID` | string | yes | — | Name of award won (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `tie` | string | yes | — | Award was a tie (Y or N) (src: lahman_readme) |
| `notes` | string | yes | — | Notes about the award (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.AwardsManagers -->

<!-- BEGIN GENERATED:lahman.AwardsPlayers -->
### Dataset: AwardsPlayers

Lahman AwardsPlayers table.

- **View:** `lahman_awardsplayers`
- **Processed path:** `processed/lahman/AwardsPlayers/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `awardID`, `yearID`, `lgID`, `notes`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `awardID` | string | yes | — | Name of award won (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `tie` | string | yes | — | Award was a tie (Y or N) (src: lahman_readme) |
| `notes` | string | yes | — | Notes about the award (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.AwardsPlayers -->

<!-- BEGIN GENERATED:lahman.AwardsShareManagers -->
### Dataset: AwardsShareManagers

Lahman AwardsShareManagers table.

- **View:** `lahman_awardssharemanagers`
- **Processed path:** `processed/lahman/AwardsShareManagers/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `awardID`, `yearID`, `lgID`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `awardID` | string | yes | — | Name of award votes were received for (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `playerID` | string | yes | — | Manager ID code (src: lahman_readme) |
| `pointsWon` | int16 | yes | — | Number of points received (src: lahman_readme) |
| `pointsMax` | int16 | yes | — | Maximum number of points possible (src: lahman_readme) |
| `votesFirst` | int16 | yes | — | Number of first place votes (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.AwardsShareManagers -->

<!-- BEGIN GENERATED:lahman.AwardsSharePlayers -->
### Dataset: AwardsSharePlayers

Lahman AwardsSharePlayers table.

- **View:** `lahman_awardsshareplayers`
- **Processed path:** `processed/lahman/AwardsSharePlayers/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `awardID`, `yearID`, `lgID`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `awardID` | string | yes | — | Name of award votes were received for (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `pointsWon` | int16 | yes | — | Number of points received (src: lahman_readme) |
| `pointsMax` | int16 | yes | — | Maximum number of points possible (src: lahman_readme) |
| `votesFirst` | int16 | yes | — | Number of first place votes (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.AwardsSharePlayers -->

<!-- BEGIN GENERATED:lahman.Batting -->
### Dataset: Batting

Lahman Batting table.

- **View:** `lahman_batting`
- **Processed path:** `processed/lahman/Batting/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `stint`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `stint` | int16 | yes | — | player's stint (order of appearances within a season) (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `AB` | int16 | yes | — | At Bats (src: lahman_readme) |
| `R` | int16 | yes | — | Runs (src: lahman_readme) |
| `H` | int16 | yes | — | Hits (src: lahman_readme) |
| `2B` | int16 | yes | — | Doubles (src: lahman_readme) |
| `3B` | int16 | yes | — | Triples (src: lahman_readme) |
| `HR` | int16 | yes | — | Homeruns (src: lahman_readme) |
| `RBI` | int16 | yes | — | Runs Batted In (src: lahman_readme) |
| `SB` | int16 | yes | — | Stolen Bases (src: lahman_readme) |
| `CS` | int16 | yes | — | Caught Stealing (src: lahman_readme) |
| `BB` | int16 | yes | — | Base on Balls (src: lahman_readme) |
| `SO` | int16 | yes | — | Strikeouts (src: lahman_readme) |
| `IBB` | int16 | yes | — | Intentional walks (src: lahman_readme) |
| `HBP` | int16 | yes | — | Hit by pitch (src: lahman_readme) |
| `SH` | int16 | yes | — | Sacrifice hits (src: lahman_readme) |
| `SF` | int16 | yes | — | Sacrifice flies (src: lahman_readme) |
| `GIDP` | int16 | yes | — | Grounded into double plays (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Batting -->

<!-- BEGIN GENERATED:lahman.BattingPost -->
### Dataset: BattingPost

Lahman BattingPost table.

- **View:** `lahman_battingpost`
- **Processed path:** `processed/lahman/BattingPost/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `round`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `round` | string | yes | — | Level of playoffs (src: lahman_readme) |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `AB` | int16 | yes | — | At Bats (src: lahman_readme) |
| `R` | int16 | yes | — | Runs (src: lahman_readme) |
| `H` | int16 | yes | — | Hits (src: lahman_readme) |
| `2B` | int16 | yes | — | Doubles (src: lahman_readme) |
| `3B` | int16 | yes | — | Triples (src: lahman_readme) |
| `HR` | int16 | yes | — | Homeruns (src: lahman_readme) |
| `RBI` | int16 | yes | — | Runs Batted In (src: lahman_readme) |
| `SB` | int16 | yes | — | Stolen Bases (src: lahman_readme) |
| `CS` | int16 | yes | — | Caught stealing (src: lahman_readme) |
| `BB` | int16 | yes | — | Base on Balls (src: lahman_readme) |
| `SO` | int16 | yes | — | Strikeouts (src: lahman_readme) |
| `IBB` | int16 | yes | — | Intentional walks (src: lahman_readme) |
| `HBP` | int16 | yes | — | Hit by pitch (src: lahman_readme) |
| `SH` | int16 | yes | — | Sacrifices (src: lahman_readme) |
| `SF` | int16 | yes | — | Sacrifice flies (src: lahman_readme) |
| `GIDP` | int16 | yes | — | Grounded into double plays (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.BattingPost -->

<!-- BEGIN GENERATED:lahman.CollegePlaying -->
### Dataset: CollegePlaying

Lahman CollegePlaying table.

- **View:** `lahman_collegeplaying`
- **Processed path:** `processed/lahman/CollegePlaying/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `schoolID`, `yearID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `schoolID` | string | yes | — | School ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.CollegePlaying -->

<!-- BEGIN GENERATED:lahman.Fielding -->
### Dataset: Fielding

Lahman Fielding table.

- **View:** `lahman_fielding`
- **Processed path:** `processed/lahman/Fielding/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `stint`, `POS`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `stint` | int16 | yes | — | player's stint (order of appearances within a season) (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `POS` | string | yes | — | Position (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `GS` | int16 | yes | — | Games Started (src: lahman_readme) |
| `InnOuts` | int16 | yes | — | Time played in the field expressed as outs (src: lahman_readme) |
| `PO` | int16 | yes | — | Putouts (src: lahman_readme) |
| `A` | int16 | yes | — | Assists (src: lahman_readme) |
| `E` | int16 | yes | — | Errors (src: lahman_readme) |
| `DP` | int16 | yes | — | Double Plays (src: lahman_readme) |
| `PB` | int16 | yes | — | Passed Balls (by catchers) (src: lahman_readme) |
| `WP` | int16 | yes | — | Wild Pitches (by catchers) (src: lahman_readme) |
| `SB` | int16 | yes | — | Opponent Stolen Bases (by catchers) (src: lahman_readme) |
| `CS` | int16 | yes | — | Opponents Caught Stealing (by catchers) (src: lahman_readme) |
| `ZR` | int16 | yes | — | Zone Rating (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Fielding -->

<!-- BEGIN GENERATED:lahman.FieldingOF -->
### Dataset: FieldingOF

Lahman FieldingOF table.

- **View:** `lahman_fieldingof`
- **Processed path:** `processed/lahman/FieldingOF/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `stint`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `stint` | int16 | yes | — | Player's stint (order of appearances within a season) (src: lahman_readme) |
| `Glf` | int16 | yes | — | Games played in left field (src: lahman_readme) |
| `Gcf` | int16 | yes | — | Games played in center field (src: lahman_readme) |
| `Grf` | int16 | yes | — | Games played in right field (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.FieldingOF -->

<!-- BEGIN GENERATED:lahman.FieldingOFsplit -->
### Dataset: FieldingOFsplit

Lahman FieldingOFsplit table.

- **View:** `lahman_fieldingofsplit`
- **Processed path:** `processed/lahman/FieldingOFsplit/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `stint`, `POS`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `stint` | int16 | yes | — | Player's stint (order of appearances within a season) (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `POS` | string | yes | — | Position (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `GS` | int16 | yes | — | Games Started (src: lahman_readme) |
| `InnOuts` | int16 | yes | — | Time played in the field expressed as outs (src: lahman_readme) |
| `PO` | int16 | yes | — | Putouts (src: lahman_readme) |
| `A` | int16 | yes | — | Assists (src: lahman_readme) |
| `E` | int16 | yes | — | Errors (src: lahman_readme) |
| `DP` | int16 | yes | — | Double Plays (src: lahman_readme) |
| `PB` | int16 | yes | — | TODO |
| `WP` | string | yes | — | TODO |
| `SB` | int16 | yes | — | TODO |
| `CS` | int16 | yes | — | TODO |
| `ZR` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.FieldingOFsplit -->

<!-- BEGIN GENERATED:lahman.FieldingPost -->
### Dataset: FieldingPost

Lahman FieldingPost table.

- **View:** `lahman_fieldingpost`
- **Processed path:** `processed/lahman/FieldingPost/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `round`, `POS`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `round` | string | yes | — | Level of playoffs (src: lahman_readme) |
| `POS` | string | yes | — | Position (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `GS` | int16 | yes | — | Games Started (src: lahman_readme) |
| `InnOuts` | int16 | yes | — | Time played in the field expressed as outs (innings played x 3) (src: lahman_readme) |
| `PO` | int16 | yes | — | Putouts (src: lahman_readme) |
| `A` | int16 | yes | — | Assists (src: lahman_readme) |
| `E` | int16 | yes | — | Errors (src: lahman_readme) |
| `DP` | int16 | yes | — | Double Plays (src: lahman_readme) |
| `TP` | int16 | yes | — | Triple Plays (src: lahman_readme) |
| `PB` | int16 | yes | — | Passed Balls (src: lahman_readme) |
| `SB` | int16 | yes | — | Stolen Bases allowed (by catcher) (src: lahman_readme) |
| `CS` | int16 | yes | — | Caught Stealing (by catcher) (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.FieldingPost -->

<!-- BEGIN GENERATED:lahman.HallOfFame -->
### Dataset: HallOfFame

Lahman HallOfFame table.

- **View:** `lahman_halloffame`
- **Processed path:** `processed/lahman/HallOfFame/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearid`, `votedBy`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearid` | int16 | yes | — | Year of ballot (src: lahman_readme) |
| `votedBy` | string | yes | — | Method by which player was voted upon (src: lahman_readme) |
| `ballots` | int16 | yes | — | Total ballots cast in that year (src: lahman_readme) |
| `needed` | int16 | yes | — | Number of votes needed for selection in that year (src: lahman_readme) |
| `votes` | int16 | yes | — | Total votes received (src: lahman_readme) |
| `inducted` | string | yes | — | Whether player was inducted by that vote or not (Y or N) (src: lahman_readme) |
| `category` | string | yes | — | Category in which candidate was honored (src: lahman_readme) |
| `needed_note` | string | yes | — | Explanation of qualifiers for special elections, revised in 2023 to include important notes about the record. (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.HallOfFame -->

<!-- BEGIN GENERATED:lahman.HomeGames -->
### Dataset: HomeGames

Lahman HomeGames table.

- **View:** `lahman_homegames`
- **Processed path:** `processed/lahman/HomeGames/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearkey`, `leaguekey`, `teamkey`, `parkkey`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearkey` | int16 | yes | — | Year (src: lahman_readme) |
| `leaguekey` | string | yes | — | League (src: lahman_readme) |
| `teamkey` | string | yes | — | Team ID (src: lahman_readme) |
| `parkkey` | string | yes | — | Ballpark ID (src: lahman_readme) |
| `spanfirst` | date32[day] | yes | — | Date of first game played (src: lahman_readme) |
| `spanlast` | date32[day] | yes | — | Date of last game played (src: lahman_readme) |
| `games` | int16 | yes | — | Total number of games (src: lahman_readme) |
| `openings` | int16 | yes | — | Total number of paid dates played (games with attendance, note that doubleheaders may make the openings less than games) (src: lahman_readme) |
| `attendance` | int32 | yes | — | Total attendance (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.HomeGames -->

<!-- BEGIN GENERATED:lahman.Managers -->
### Dataset: Managers

Lahman Managers table.

- **View:** `lahman_managers`
- **Processed path:** `processed/lahman/Managers/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `teamID`, `inseason`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID Number (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `inseason` | int16 | yes | — | Managerial order, in order of appearance during the year.  One if the individual managed the team the entire year. (src: lahman_readme) |
| `G` | int16 | yes | — | Games managed (src: lahman_readme) |
| `W` | int16 | yes | — | Wins (src: lahman_readme) |
| `L` | int16 | yes | — | Losses (src: lahman_readme) |
| `rank` | int16 | yes | — | Team's final position in standings that year (src: lahman_readme) |
| `plyrMgr` | string | yes | — | Player Manager (denoted by 'Y') (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Managers -->

<!-- BEGIN GENERATED:lahman.ManagersHalf -->
### Dataset: ManagersHalf

Lahman ManagersHalf table.

- **View:** `lahman_managershalf`
- **Processed path:** `processed/lahman/ManagersHalf/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `teamID`, `half`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Manager ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `inseason` | int16 | yes | — | Managerial order, in order of appearance during the year, 1 if the individual managed the team the entire year (src: lahman_readme) |
| `half` | int16 | yes | — | First or second half of season (src: lahman_readme) |
| `G` | int16 | yes | — | Games managed (src: lahman_readme) |
| `W` | int16 | yes | — | Wins (src: lahman_readme) |
| `L` | int16 | yes | — | Losses (src: lahman_readme) |
| `rank` | int16 | yes | — | Team's position in standings for the half (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.ManagersHalf -->

<!-- BEGIN GENERATED:lahman.Parks -->
### Dataset: Parks

Lahman Parks table.

- **View:** `lahman_parks`
- **Processed path:** `processed/lahman/Parks/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `parkkey`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `ID` | int16 | yes | — | TODO |
| `parkalias` | string | yes | — | Alternate names of ballpark, separated by semicolon (src: lahman_readme) |
| `parkkey` | string | yes | — | Ballpark ID code (src: lahman_readme) |
| `parkname` | string | yes | — | Name of ballpark (src: lahman_readme) |
| `city` | string | yes | — | City (src: lahman_readme) |
| `state` | string | yes | — | State (src: lahman_readme) |
| `country` | string | yes | — | Country (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Parks -->

<!-- BEGIN GENERATED:lahman.People -->
### Dataset: People

Lahman People table.

- **View:** `lahman_people`
- **Processed path:** `processed/lahman/People/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `ID` | int32 | yes | — | Numeric ID, not used anywhere else. (src: lahman_readme) |
| `playerID` | string | yes | — | A unique code assigned to each player.  The playerID links the data in this file with records in the other files. (src: lahman_readme) |
| `birthYear` | int16 | yes | — | Year player was born (src: lahman_readme) |
| `birthMonth` | int16 | yes | — | Month player was born (src: lahman_readme) |
| `birthDay` | int16 | yes | — | Day player was born (src: lahman_readme) |
| `birthCity` | string | yes | — | City where player was born (src: lahman_readme) |
| `birthCountry` | string | yes | — | Country where player was born (src: lahman_readme) |
| `birthState` | string | yes | — | State where player was born (src: lahman_readme) |
| `deathYear` | int16 | yes | — | Year player died (src: lahman_readme) |
| `deathMonth` | int16 | yes | — | Month player died (src: lahman_readme) |
| `deathDay` | int16 | yes | — | Day player died (src: lahman_readme) |
| `deathCountry` | string | yes | — | Country where player died (src: lahman_readme) |
| `deathState` | string | yes | — | State where player died (src: lahman_readme) |
| `deathCity` | string | yes | — | City where player died (src: lahman_readme) |
| `nameFirst` | string | yes | — | Player's first name (src: lahman_readme) |
| `nameLast` | string | yes | — | Player's last name (src: lahman_readme) |
| `nameGiven` | string | yes | — | Player's given name (typically first and middle) (src: lahman_readme) |
| `weight` | int16 | yes | — | Player's weight in pounds (src: lahman_readme) |
| `height` | int16 | yes | — | Player's height in inches (src: lahman_readme) |
| `bats` | string | yes | — | Player's batting hand (left, right, or both) (src: lahman_readme) |
| `throws` | string | yes | — | Player's throwing hand (left or right) (src: lahman_readme) |
| `debut` | date32[day] | yes | — | Date that player made first major league appearance (src: lahman_readme) |
| `bbrefID` | string | yes | — | ID used by Baseball Reference website (src: lahman_readme) |
| `finalGame` | date32[day] | yes | — | Date that player made last major league appearance (src: lahman_readme) |
| `retroID` | string | yes | — | ID used by Retrosheet (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.People -->

<!-- BEGIN GENERATED:lahman.Pitching -->
### Dataset: Pitching

Lahman Pitching table.

- **View:** `lahman_pitching`
- **Processed path:** `processed/lahman/Pitching/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `stint`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `stint` | int16 | yes | — | player's stint (order of appearances within a season) (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `W` | int16 | yes | — | Wins (src: lahman_readme) |
| `L` | int16 | yes | — | Losses (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `GS` | int16 | yes | — | Games Started (src: lahman_readme) |
| `CG` | int16 | yes | — | Complete Games (src: lahman_readme) |
| `SHO` | int16 | yes | — | Shutouts (src: lahman_readme) |
| `SV` | int16 | yes | — | Saves (src: lahman_readme) |
| `IPouts` | int16 | yes | — | Outs Pitched (innings pitched x 3) (src: lahman_readme) |
| `H` | int16 | yes | — | Hits (src: lahman_readme) |
| `ER` | int16 | yes | — | Earned Runs (src: lahman_readme) |
| `HR` | int16 | yes | — | Homeruns (src: lahman_readme) |
| `BB` | int16 | yes | — | Walks (src: lahman_readme) |
| `SO` | int16 | yes | — | Strikeouts (src: lahman_readme) |
| `BAOpp` | double | yes | — | Opponent's Batting Average (src: lahman_readme) |
| `ERA` | double | yes | — | Earned Run Average (src: lahman_readme) |
| `IBB` | int16 | yes | — | Intentional Walks (src: lahman_readme) |
| `WP` | int16 | yes | — | Wild Pitches (src: lahman_readme) |
| `HBP` | int16 | yes | — | Batters Hit By Pitch (src: lahman_readme) |
| `BK` | int16 | yes | — | Balks (src: lahman_readme) |
| `BFP` | int16 | yes | — | Batters faced by Pitcher (src: lahman_readme) |
| `GF` | int16 | yes | — | Games Finished (src: lahman_readme) |
| `R` | int16 | yes | — | Runs Allowed (src: lahman_readme) |
| `SH` | int16 | yes | — | Sacrifices by opposing batters (src: lahman_readme) |
| `SF` | int16 | yes | — | Sacrifice flies by opposing batters (src: lahman_readme) |
| `GIDP` | int16 | yes | — | Grounded into double plays by opposing batter (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Pitching -->

<!-- BEGIN GENERATED:lahman.PitchingPost -->
### Dataset: PitchingPost

Lahman PitchingPost table.

- **View:** `lahman_pitchingpost`
- **Processed path:** `processed/lahman/PitchingPost/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `round`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `round` | string | yes | — | Level of playoffs (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `W` | int16 | yes | — | Wins (src: lahman_readme) |
| `L` | int16 | yes | — | Losses (src: lahman_readme) |
| `G` | int16 | yes | — | Games (src: lahman_readme) |
| `GS` | int16 | yes | — | Games Started (src: lahman_readme) |
| `CG` | int16 | yes | — | Complete Games (src: lahman_readme) |
| `SHO` | int16 | yes | — | Shutouts (src: lahman_readme) |
| `SV` | int16 | yes | — | Saves (src: lahman_readme) |
| `IPouts` | int16 | yes | — | Outs Pitched (innings pitched x 3) (src: lahman_readme) |
| `H` | int16 | yes | — | Hits (src: lahman_readme) |
| `ER` | int16 | yes | — | Earned Runs (src: lahman_readme) |
| `HR` | int16 | yes | — | Homeruns (src: lahman_readme) |
| `BB` | int16 | yes | — | Walks (src: lahman_readme) |
| `SO` | int16 | yes | — | Strikeouts (src: lahman_readme) |
| `BAOpp` | double | yes | — | Opponents' batting average (src: lahman_readme) |
| `ERA` | double | yes | — | Earned Run Average (src: lahman_readme) |
| `IBB` | int16 | yes | — | Intentional Walks (src: lahman_readme) |
| `WP` | int16 | yes | — | Wild Pitches (src: lahman_readme) |
| `HBP` | int16 | yes | — | Batters Hit By Pitch (src: lahman_readme) |
| `BK` | int16 | yes | — | Balks (src: lahman_readme) |
| `BFP` | int16 | yes | — | Batters faced by Pitcher (src: lahman_readme) |
| `GF` | int16 | yes | — | Games Finished (src: lahman_readme) |
| `R` | int16 | yes | — | Runs Allowed (src: lahman_readme) |
| `SH` | int16 | yes | — | Sacrifice Hits allowed (src: lahman_readme) |
| `SF` | int16 | yes | — | Sacrifice Flies allowed (src: lahman_readme) |
| `GIDP` | int16 | yes | — | Grounded into Double Plays (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.PitchingPost -->

<!-- BEGIN GENERATED:lahman.Salaries -->
### Dataset: Salaries

Lahman Salaries table.

- **View:** `lahman_salaries`
- **Processed path:** `processed/lahman/Salaries/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `teamID`, `lgID`, `playerID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `playerID` | string | yes | — | Player ID code (src: lahman_readme) |
| `salary` | int32 | yes | — | Salary (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Salaries -->

<!-- BEGIN GENERATED:lahman.Schools -->
### Dataset: Schools

Lahman Schools table.

- **View:** `lahman_schools`
- **Processed path:** `processed/lahman/Schools/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `schoolID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `schoolID` | string | yes | — | School ID code (src: lahman_readme) |
| `name_full` | string | yes | — | TODO |
| `city` | string | yes | — | TODO |
| `state` | string | yes | — | TODO |
| `country` | string | yes | — | TODO |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Schools -->

<!-- BEGIN GENERATED:lahman.SeriesPost -->
### Dataset: SeriesPost

Lahman SeriesPost table.

- **View:** `lahman_seriespost`
- **Processed path:** `processed/lahman/SeriesPost/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `round`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `round` | string | yes | — | Level of playoffs (src: lahman_readme) |
| `teamIDwinner` | string | yes | — | Team ID of the team that won the series (src: lahman_readme) |
| `lgIDwinner` | string | yes | — | League ID of the team that won the series (src: lahman_readme) |
| `teamIDloser` | string | yes | — | Team ID of the team that lost the series (src: lahman_readme) |
| `lgIDloser` | string | yes | — | League ID of the team that lost the series (src: lahman_readme) |
| `wins` | int16 | yes | — | Wins by team that won the series (src: lahman_readme) |
| `losses` | int16 | yes | — | Losses by team that won the series (src: lahman_readme) |
| `ties` | int16 | yes | — | Tie games (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.SeriesPost -->

<!-- BEGIN GENERATED:lahman.Teams -->
### Dataset: Teams

Lahman Teams table.

- **View:** `lahman_teams`
- **Processed path:** `processed/lahman/Teams/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `lgID`, `teamID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `franchID` | string | yes | — | Franchise (links to TeamsFranchise table) (src: lahman_readme) |
| `divID` | string | yes | — | Team's division (src: lahman_readme) |
| `Rank` | int16 | yes | — | Position in final standings (src: lahman_readme) |
| `G` | int16 | yes | — | Games played (src: lahman_readme) |
| `Ghome` | int16 | yes | — | Games played at home (src: lahman_readme) |
| `W` | int16 | yes | — | Wins (src: lahman_readme) |
| `L` | int16 | yes | — | Losses (src: lahman_readme) |
| `DivWin` | string | yes | — | Division Winner (Y or N) (src: lahman_readme) |
| `WCWin` | string | yes | — | Wild Card Winner (Y or N) (src: lahman_readme) |
| `LgWin` | string | yes | — | League Champion (Y or N) (src: lahman_readme) |
| `WSWin` | string | yes | — | World Series Winner (Y or N) (src: lahman_readme) |
| `R` | int16 | yes | — | Runs scored (src: lahman_readme) |
| `AB` | int16 | yes | — | At bats (src: lahman_readme) |
| `H` | int16 | yes | — | Hits by batters (src: lahman_readme) |
| `2B` | int16 | yes | — | Doubles (src: lahman_readme) |
| `3B` | int16 | yes | — | Triples (src: lahman_readme) |
| `HR` | int16 | yes | — | Homeruns by batters (src: lahman_readme) |
| `BB` | int16 | yes | — | Walks by batters (src: lahman_readme) |
| `SO` | int16 | yes | — | Strikeouts by batters (src: lahman_readme) |
| `SB` | int16 | yes | — | Stolen bases (src: lahman_readme) |
| `CS` | int16 | yes | — | Caught stealing (src: lahman_readme) |
| `HBP` | int16 | yes | — | Batters hit by pitch (src: lahman_readme) |
| `SF` | int16 | yes | — | Sacrifice flies (src: lahman_readme) |
| `RA` | int16 | yes | — | Opponents runs scored (src: lahman_readme) |
| `ER` | int16 | yes | — | Earned runs allowed (src: lahman_readme) |
| `ERA` | double | yes | — | Earned run average (src: lahman_readme) |
| `CG` | int16 | yes | — | Complete games (src: lahman_readme) |
| `SHO` | int16 | yes | — | Shutouts (team level) (src: lahman_readme) |
| `SV` | int16 | yes | — | Saves (src: lahman_readme) |
| `IPouts` | int16 | yes | — | Outs Pitched (innings pitched x 3) (src: lahman_readme) |
| `HA` | int16 | yes | — | Hits allowed (src: lahman_readme) |
| `HRA` | int16 | yes | — | Homeruns allowed (src: lahman_readme) |
| `BBA` | int16 | yes | — | Walks allowed (src: lahman_readme) |
| `SOA` | int16 | yes | — | Strikeouts by pitchers (src: lahman_readme) |
| `E` | int16 | yes | — | Errors (src: lahman_readme) |
| `DP` | int16 | yes | — | Double Plays (team level) (src: lahman_readme) |
| `FP` | double | yes | — | Fielding  percentage (src: lahman_readme) |
| `name` | string | yes | — | Team's full name (src: lahman_readme) |
| `park` | string | yes | — | Name of team's home ballpark (src: lahman_readme) |
| `attendance` | int32 | yes | — | Home attendance total (src: lahman_readme) |
| `BPF` | int16 | yes | — | Three-year park factor for batters (src: lahman_readme) |
| `PPF` | int16 | yes | — | Three-year park factor for pitchers (src: lahman_readme) |
| `teamIDBR` | string | yes | — | Team ID used by Baseball Reference website (src: lahman_readme) |
| `teamIDlahman45` | string | yes | — | TODO |
| `teamIDretro` | string | yes | — | Team ID used by Retrosheet (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.Teams -->

<!-- BEGIN GENERATED:lahman.TeamsFranchises -->
### Dataset: TeamsFranchises

Lahman TeamsFranchises table.

- **View:** `lahman_teamsfranchises`
- **Processed path:** `processed/lahman/TeamsFranchises/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `franchID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `franchID` | string | yes | — | Franchise ID (src: lahman_readme) |
| `franchName` | string | yes | — | Franchise name (src: lahman_readme) |
| `active` | string | yes | — | Whether team is currently active or not (Y or N) (src: lahman_readme) |
| `NAassoc` | string | yes | — | ID of National Association team franchise played as (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.TeamsFranchises -->

<!-- BEGIN GENERATED:lahman.TeamsHalf -->
### Dataset: TeamsHalf

Lahman TeamsHalf table.

- **View:** `lahman_teamshalf`
- **Processed path:** `processed/lahman/TeamsHalf/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `yearID`, `lgID`, `teamID`, `Half`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `yearID` | int16 | yes | — | Year (src: lahman_readme) |
| `lgID` | string | yes | — | League (src: lahman_readme) |
| `teamID` | string | yes | — | Team (src: lahman_readme) |
| `Half` | int16 | yes | — | First or second half of season (src: lahman_readme) |
| `divID` | string | yes | — | Division (src: lahman_readme) |
| `DivWin` | string | yes | — | Won Division (Y or N) (src: lahman_readme) |
| `Rank` | int16 | yes | — | Team's position in standings for the half (src: lahman_readme) |
| `G` | int16 | yes | — | Games played (src: lahman_readme) |
| `W` | int16 | yes | — | Wins (src: lahman_readme) |
| `L` | int16 | yes | — | Losses (src: lahman_readme) |
| `_extras` | string | yes | — | Upstream fields without a typed column, as JSON (schema-drift safety net). (authored) |

<!-- END GENERATED:lahman.TeamsHalf -->
