# SABR Lahman Baseball Database Endpoint & Schema Catalog (1871–2025)

## Upstream Overview
- **Provider:** Society for American Baseball Research (SABR) & Sean Lahman
- **Historical Scope:** 1871 through 2025 Major League Baseball seasons
- **Format:** 27 relational CSV tables
- **Official SABR Page:** `https://sabr.org/lahman-database/`
- **Automated Mirror:** `https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/<pinned sha>/data/` (the repository also ships `readme2025.txt`, the release's own documentation)
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
- **Provenance:** each table's raw manifest records `origin` (`<repo>@<sha>` or `local-import`) and `source_ref`. A table fetched at a different ref is refetched; user-imported tables are never overwritten by remote cache invalidation.
- **Stale-data warning:** if the newest `yearID` in `Batting`/`Teams` is more than one season behind the last completed MLB season, a warning is logged and kept in the processed manifest (`quality.stale`).
- **Data-quality checks (warnings, never errors):** primary-key uniqueness and `playerID` ∈ `People` are checked on every ingest; findings are logged and stored in the processed manifest (`quality`).
- **Safe imports:** `import_archive` rejects zip members with path traversal (`..`) and members/archives beyond 512 MB / 2 GB; raw files are written atomically and untouched (byte-for-byte, BOM included).

## Schemas
All 27 schemas are **generated from the real headers** (`scripts/gen_schemas.py lahman`) and committed in `sources/lahman/tables.py`; column types are inferred over the full release with conservative narrowing (integers are `int16` only when every value is within ±20,000, otherwise `int32`/`int64`; ISO dates are `date32`). Columns are matched by **header name**, so order never matters, and any column added upstream is preserved as JSON in the trailing `_extras` column with a one-time `schema_drift` warning.

Quirks verified on the 2025 release:
- `People.csv`, `Parks.csv`, `Batting.csv` start with a UTF-8 BOM; it is stripped from the first header.
- `People` and `Parks` carry a surrogate `ID` column; `HomeGames` uses `yearkey/leaguekey/teamkey/parkkey` instead of `yearID/lgID/teamID`; `HallOfFame` spells its year column `yearid`.
- `lgID` code `NA` (National Association, 1871–75) is real data, not NULL.
- Documented primary keys (uniqueness verified on the full data): `AllstarFull` (`playerID, yearID, gameNum, gameID, teamID, lgID`), `AwardsPlayers` (`playerID, awardID, yearID, lgID, notes`), `Appearances` (`yearID, teamID, playerID`), `Batting`/`Pitching` (`playerID, yearID, stint`), `Fielding` (`playerID, yearID, stint, POS`), `Teams` (`yearID, lgID, teamID`) and so on — see the generated per-table blocks below.

The generated column dictionaries for all 27 tables follow (regenerate with `baseballpy docs generate`).

## Python API Usage

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

<!-- BEGIN GENERATED:lahman.AllstarFull -->
### Dataset: AllstarFull

Lahman AllstarFull table.

- **View:** `lahman_allstarfull`
- **Processed path:** `processed/lahman/AllstarFull/part-<chunk>.parquet`
- **Partitioning:** none (flat)
- **Key:** `playerID`, `yearID`, `gameNum`, `gameID`, `teamID`, `lgID`

| Column | Type | Nullable | Upstream name | Description |
| --- | --- | --- | --- | --- |
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `gameNum` | int16 | yes | — |  |
| `gameID` | string | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `GP` | int16 | yes | — |  |
| `startingPos` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearID` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `playerID` | string | yes | — |  |
| `G_all` | int16 | yes | — |  |
| `GS` | int16 | yes | — |  |
| `G_batting` | int16 | yes | — |  |
| `G_defense` | int16 | yes | — |  |
| `G_p` | int16 | yes | — |  |
| `G_c` | int16 | yes | — |  |
| `G_1b` | int16 | yes | — |  |
| `G_2b` | int16 | yes | — |  |
| `G_3b` | int16 | yes | — |  |
| `G_ss` | int16 | yes | — |  |
| `G_lf` | int16 | yes | — |  |
| `G_cf` | int16 | yes | — |  |
| `G_rf` | int16 | yes | — |  |
| `G_of` | int16 | yes | — |  |
| `G_dh` | int16 | yes | — |  |
| `G_ph` | int16 | yes | — |  |
| `G_pr` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `awardID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `lgID` | string | yes | — |  |
| `tie` | string | yes | — |  |
| `notes` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `awardID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `lgID` | string | yes | — |  |
| `tie` | string | yes | — |  |
| `notes` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `awardID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `lgID` | string | yes | — |  |
| `playerID` | string | yes | — |  |
| `pointsWon` | int16 | yes | — |  |
| `pointsMax` | int16 | yes | — |  |
| `votesFirst` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `awardID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `lgID` | string | yes | — |  |
| `playerID` | string | yes | — |  |
| `pointsWon` | int16 | yes | — |  |
| `pointsMax` | int16 | yes | — |  |
| `votesFirst` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `stint` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `G` | int16 | yes | — |  |
| `AB` | int16 | yes | — |  |
| `R` | int16 | yes | — |  |
| `H` | int16 | yes | — |  |
| `2B` | int16 | yes | — |  |
| `3B` | int16 | yes | — |  |
| `HR` | int16 | yes | — |  |
| `RBI` | int16 | yes | — |  |
| `SB` | int16 | yes | — |  |
| `CS` | int16 | yes | — |  |
| `BB` | int16 | yes | — |  |
| `SO` | int16 | yes | — |  |
| `IBB` | int16 | yes | — |  |
| `HBP` | int16 | yes | — |  |
| `SH` | int16 | yes | — |  |
| `SF` | int16 | yes | — |  |
| `GIDP` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearID` | int16 | yes | — |  |
| `round` | string | yes | — |  |
| `playerID` | string | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `G` | int16 | yes | — |  |
| `AB` | int16 | yes | — |  |
| `R` | int16 | yes | — |  |
| `H` | int16 | yes | — |  |
| `2B` | int16 | yes | — |  |
| `3B` | int16 | yes | — |  |
| `HR` | int16 | yes | — |  |
| `RBI` | int16 | yes | — |  |
| `SB` | int16 | yes | — |  |
| `CS` | int16 | yes | — |  |
| `BB` | int16 | yes | — |  |
| `SO` | int16 | yes | — |  |
| `IBB` | int16 | yes | — |  |
| `HBP` | int16 | yes | — |  |
| `SH` | int16 | yes | — |  |
| `SF` | int16 | yes | — |  |
| `GIDP` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `schoolID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `stint` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `POS` | string | yes | — |  |
| `G` | int16 | yes | — |  |
| `GS` | int16 | yes | — |  |
| `InnOuts` | int16 | yes | — |  |
| `PO` | int16 | yes | — |  |
| `A` | int16 | yes | — |  |
| `E` | int16 | yes | — |  |
| `DP` | int16 | yes | — |  |
| `PB` | int16 | yes | — |  |
| `WP` | int16 | yes | — |  |
| `SB` | int16 | yes | — |  |
| `CS` | int16 | yes | — |  |
| `ZR` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `stint` | int16 | yes | — |  |
| `Glf` | int16 | yes | — |  |
| `Gcf` | int16 | yes | — |  |
| `Grf` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `stint` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `POS` | string | yes | — |  |
| `G` | int16 | yes | — |  |
| `GS` | int16 | yes | — |  |
| `InnOuts` | int16 | yes | — |  |
| `PO` | int16 | yes | — |  |
| `A` | int16 | yes | — |  |
| `E` | int16 | yes | — |  |
| `DP` | int16 | yes | — |  |
| `PB` | int16 | yes | — |  |
| `WP` | string | yes | — |  |
| `SB` | int16 | yes | — |  |
| `CS` | int16 | yes | — |  |
| `ZR` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `round` | string | yes | — |  |
| `POS` | string | yes | — |  |
| `G` | int16 | yes | — |  |
| `GS` | int16 | yes | — |  |
| `InnOuts` | int16 | yes | — |  |
| `PO` | int16 | yes | — |  |
| `A` | int16 | yes | — |  |
| `E` | int16 | yes | — |  |
| `DP` | int16 | yes | — |  |
| `TP` | int16 | yes | — |  |
| `PB` | int16 | yes | — |  |
| `SB` | int16 | yes | — |  |
| `CS` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearid` | int16 | yes | — |  |
| `votedBy` | string | yes | — |  |
| `ballots` | int16 | yes | — |  |
| `needed` | int16 | yes | — |  |
| `votes` | int16 | yes | — |  |
| `inducted` | string | yes | — |  |
| `category` | string | yes | — |  |
| `needed_note` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearkey` | int16 | yes | — |  |
| `leaguekey` | string | yes | — |  |
| `teamkey` | string | yes | — |  |
| `parkkey` | string | yes | — |  |
| `spanfirst` | date32[day] | yes | — |  |
| `spanlast` | date32[day] | yes | — |  |
| `games` | int16 | yes | — |  |
| `openings` | int16 | yes | — |  |
| `attendance` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `inseason` | int16 | yes | — |  |
| `G` | int16 | yes | — |  |
| `W` | int16 | yes | — |  |
| `L` | int16 | yes | — |  |
| `rank` | int16 | yes | — |  |
| `plyrMgr` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `inseason` | int16 | yes | — |  |
| `half` | int16 | yes | — |  |
| `G` | int16 | yes | — |  |
| `W` | int16 | yes | — |  |
| `L` | int16 | yes | — |  |
| `rank` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `ID` | int16 | yes | — |  |
| `parkalias` | string | yes | — |  |
| `parkkey` | string | yes | — |  |
| `parkname` | string | yes | — |  |
| `city` | string | yes | — |  |
| `state` | string | yes | — |  |
| `country` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `ID` | int32 | yes | — |  |
| `playerID` | string | yes | — |  |
| `birthYear` | int16 | yes | — |  |
| `birthMonth` | int16 | yes | — |  |
| `birthDay` | int16 | yes | — |  |
| `birthCity` | string | yes | — |  |
| `birthCountry` | string | yes | — |  |
| `birthState` | string | yes | — |  |
| `deathYear` | int16 | yes | — |  |
| `deathMonth` | int16 | yes | — |  |
| `deathDay` | int16 | yes | — |  |
| `deathCountry` | string | yes | — |  |
| `deathState` | string | yes | — |  |
| `deathCity` | string | yes | — |  |
| `nameFirst` | string | yes | — |  |
| `nameLast` | string | yes | — |  |
| `nameGiven` | string | yes | — |  |
| `weight` | int16 | yes | — |  |
| `height` | int16 | yes | — |  |
| `bats` | string | yes | — |  |
| `throws` | string | yes | — |  |
| `debut` | date32[day] | yes | — |  |
| `bbrefID` | string | yes | — |  |
| `finalGame` | date32[day] | yes | — |  |
| `retroID` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `stint` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `W` | int16 | yes | — |  |
| `L` | int16 | yes | — |  |
| `G` | int16 | yes | — |  |
| `GS` | int16 | yes | — |  |
| `CG` | int16 | yes | — |  |
| `SHO` | int16 | yes | — |  |
| `SV` | int16 | yes | — |  |
| `IPouts` | int16 | yes | — |  |
| `H` | int16 | yes | — |  |
| `ER` | int16 | yes | — |  |
| `HR` | int16 | yes | — |  |
| `BB` | int16 | yes | — |  |
| `SO` | int16 | yes | — |  |
| `BAOpp` | double | yes | — |  |
| `ERA` | double | yes | — |  |
| `IBB` | int16 | yes | — |  |
| `WP` | int16 | yes | — |  |
| `HBP` | int16 | yes | — |  |
| `BK` | int16 | yes | — |  |
| `BFP` | int16 | yes | — |  |
| `GF` | int16 | yes | — |  |
| `R` | int16 | yes | — |  |
| `SH` | int16 | yes | — |  |
| `SF` | int16 | yes | — |  |
| `GIDP` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `playerID` | string | yes | — |  |
| `yearID` | int16 | yes | — |  |
| `round` | string | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `W` | int16 | yes | — |  |
| `L` | int16 | yes | — |  |
| `G` | int16 | yes | — |  |
| `GS` | int16 | yes | — |  |
| `CG` | int16 | yes | — |  |
| `SHO` | int16 | yes | — |  |
| `SV` | int16 | yes | — |  |
| `IPouts` | int16 | yes | — |  |
| `H` | int16 | yes | — |  |
| `ER` | int16 | yes | — |  |
| `HR` | int16 | yes | — |  |
| `BB` | int16 | yes | — |  |
| `SO` | int16 | yes | — |  |
| `BAOpp` | double | yes | — |  |
| `ERA` | double | yes | — |  |
| `IBB` | int16 | yes | — |  |
| `WP` | int16 | yes | — |  |
| `HBP` | int16 | yes | — |  |
| `BK` | int16 | yes | — |  |
| `BFP` | int16 | yes | — |  |
| `GF` | int16 | yes | — |  |
| `R` | int16 | yes | — |  |
| `SH` | int16 | yes | — |  |
| `SF` | int16 | yes | — |  |
| `GIDP` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearID` | int16 | yes | — |  |
| `teamID` | string | yes | — |  |
| `lgID` | string | yes | — |  |
| `playerID` | string | yes | — |  |
| `salary` | int32 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `schoolID` | string | yes | — |  |
| `name_full` | string | yes | — |  |
| `city` | string | yes | — |  |
| `state` | string | yes | — |  |
| `country` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearID` | int16 | yes | — |  |
| `round` | string | yes | — |  |
| `teamIDwinner` | string | yes | — |  |
| `lgIDwinner` | string | yes | — |  |
| `teamIDloser` | string | yes | — |  |
| `lgIDloser` | string | yes | — |  |
| `wins` | int16 | yes | — |  |
| `losses` | int16 | yes | — |  |
| `ties` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearID` | int16 | yes | — |  |
| `lgID` | string | yes | — |  |
| `teamID` | string | yes | — |  |
| `franchID` | string | yes | — |  |
| `divID` | string | yes | — |  |
| `Rank` | int16 | yes | — |  |
| `G` | int16 | yes | — |  |
| `Ghome` | int16 | yes | — |  |
| `W` | int16 | yes | — |  |
| `L` | int16 | yes | — |  |
| `DivWin` | string | yes | — |  |
| `WCWin` | string | yes | — |  |
| `LgWin` | string | yes | — |  |
| `WSWin` | string | yes | — |  |
| `R` | int16 | yes | — |  |
| `AB` | int16 | yes | — |  |
| `H` | int16 | yes | — |  |
| `2B` | int16 | yes | — |  |
| `3B` | int16 | yes | — |  |
| `HR` | int16 | yes | — |  |
| `BB` | int16 | yes | — |  |
| `SO` | int16 | yes | — |  |
| `SB` | int16 | yes | — |  |
| `CS` | int16 | yes | — |  |
| `HBP` | int16 | yes | — |  |
| `SF` | int16 | yes | — |  |
| `RA` | int16 | yes | — |  |
| `ER` | int16 | yes | — |  |
| `ERA` | double | yes | — |  |
| `CG` | int16 | yes | — |  |
| `SHO` | int16 | yes | — |  |
| `SV` | int16 | yes | — |  |
| `IPouts` | int16 | yes | — |  |
| `HA` | int16 | yes | — |  |
| `HRA` | int16 | yes | — |  |
| `BBA` | int16 | yes | — |  |
| `SOA` | int16 | yes | — |  |
| `E` | int16 | yes | — |  |
| `DP` | int16 | yes | — |  |
| `FP` | double | yes | — |  |
| `name` | string | yes | — |  |
| `park` | string | yes | — |  |
| `attendance` | int32 | yes | — |  |
| `BPF` | int16 | yes | — |  |
| `PPF` | int16 | yes | — |  |
| `teamIDBR` | string | yes | — |  |
| `teamIDlahman45` | string | yes | — |  |
| `teamIDretro` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `franchID` | string | yes | — |  |
| `franchName` | string | yes | — |  |
| `active` | string | yes | — |  |
| `NAassoc` | string | yes | — |  |
| `_extras` | string | yes | — |  |

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
| `yearID` | int16 | yes | — |  |
| `lgID` | string | yes | — |  |
| `teamID` | string | yes | — |  |
| `Half` | int16 | yes | — |  |
| `divID` | string | yes | — |  |
| `DivWin` | string | yes | — |  |
| `Rank` | int16 | yes | — |  |
| `G` | int16 | yes | — |  |
| `W` | int16 | yes | — |  |
| `L` | int16 | yes | — |  |
| `_extras` | string | yes | — |  |

<!-- END GENERATED:lahman.TeamsHalf -->
