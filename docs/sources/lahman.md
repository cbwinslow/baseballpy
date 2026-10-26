# SABR Lahman Baseball Database Endpoint & Schema Catalog (1871–2025)

## Upstream Overview
- **Provider:** Society for American Baseball Research (SABR) & Sean Lahman
- **Historical Scope:** 1871 through 2025 Major League Baseball seasons
- **Format:** 27 relational CSV tables
- **Official SABR Page:** `https://sabr.org/lahman-database/`
- **Automated Mirror:** `https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/main/data/`
- **Why Automated Scrapers Fail on SABR Box:** The official download link on SABR routes through `sabr.app.box.com`, which requires ephemeral session cookies and interactive verification. Direct HTTP scripts hitting Box break.
- **baseballpy Dual-Mode Solution:**
  1. **Mode A (Automated Extraction):** Direct zero-configuration download from the verified GitHub repository `cbwinslow/lahman-database-csv`, containing the complete 1871–2025 SABR release with 27 tables.
  2. **Mode B (Manual Local Import):** A built-in helper `lahman.import_archive(path)` allowing users to supply an official `.zip` or unzipped folder downloaded manually from SABR Box. The helper moves/copies the raw CSVs into `~/.baseballpy/cache/lahman/raw/` and compiles them immediately into strongly-typed Parquet tables in `~/.baseballpy/cache/lahman/processed/`.

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

## Canonical Table Schema Dictionaries

### 1. `Batting` Table Schema
| Column Name | PyArrow Physical Type | Nullable | Example Raw Value | Description |
| :--- | :--- | :---: | :--- | :--- |
| `playerID` | `string()` | No | `ohtansh01` | Player unique Lahman ID |
| `yearID` | `int16()` | No | `2024` | Championship season |
| `stint` | `int8()` | No | `1` | Order of stints within season for traded players |
| `teamID` | `string()` | No | `LAD` | Team 3-character code |
| `lgID` | `string()` | No | `NL` | League code (`AL`, `NL`, `AA`, `PL`, `FL`, `NA`) |
| `G` | `int16()` | No | `159` | Games played |
| `AB` | `int16()` | Yes | `636` | At bats |
| `R` | `int16()` | Yes | `134` | Runs scored |
| `H` | `int16()` | Yes | `197` | Hits |
| `2B` | `int16()` | Yes | `38` | Doubles |
| `3B` | `int16()` | Yes | `7` | Triples |
| `HR` | `int16()` | Yes | `54` | Home runs |
| `RBI` | `int16()` | Yes | `130` | Runs batted in |
| `SB` | `int16()` | Yes | `59` | Stolen bases |
| `CS` | `int16()` | Yes | `4` | Caught stealing |
| `BB` | `int16()` | Yes | `81` | Base on balls (walks) |
| `SO` | `int16()` | Yes | `162` | Strikeouts |
| `IBB` | `int16()` | Yes | `20` | Intentional walks |
| `HBP` | `int16()` | Yes | `6` | Hit by pitch |
| `SH` | `int16()` | Yes | `0` | Sacrifice hits (bunts) |
| `SF` | `int16()` | Yes | `5` | Sacrifice flies |
| `GIDP` | `int16()` | Yes | `5` | Grounded into double plays |

### 2. `Pitching` Table Schema
| Column Name | PyArrow Physical Type | Nullable | Example Raw Value | Description |
| :--- | :--- | :---: | :--- | :--- |
| `playerID` | `string()` | No | `coleg01` | Player Lahman ID |
| `yearID` | `int16()` | No | `2023` | Championship season |
| `stint` | `int8()` | No | `1` | Stint index |
| `teamID` | `string()` | No | `NYA` | Team code |
| `lgID` | `string()` | No | `AL` | League code |
| `W` | `int16()` | Yes | `15` | Wins |
| `L` | `int16()` | Yes | `4` | Losses |
| `G` | `int16()` | No | `33` | Games appeared |
| `GS` | `int16()` | Yes | `33` | Games started |
| `CG` | `int16()` | Yes | `2` | Complete games |
| `SHO` | `int16()` | Yes | `2` | Shutouts |
| `SV` | `int16()` | Yes | `0` | Saves |
| `IPouts` | `int32()` | Yes | `627` | Outs pitched (IP = IPouts / 3) |
| `H` | `int16()` | Yes | `157` | Hits allowed |
| `ER` | `int16()` | Yes | `61` | Earned runs allowed |
| `HR` | `int16()` | Yes | `20` | Home runs allowed |
| `BB` | `int16()` | Yes | `48` | Walks allowed |
| `SO` | `int16()` | Yes | `222` | Strikeouts |
| `BAOpp` | `float32()` | Yes | `0.206` | Opponents' batting average |
| `ERA` | `float32()` | Yes | `2.63` | Earned run average |

---

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
