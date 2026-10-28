# baseballpy Quickstart & Dataset Function Catalog

A complete reference guide mapping every dataset to its designated Python function, schema types, and storage sink.

---

## 1. Installation

```bash
# With uv (recommended)
uv add baseballpy

# Or with pip
pip install baseballpy
```

Optional feature bundles:
```bash
uv add "baseballpy[all]"  # Includes pandas and the Postgres/Snowflake dlt destinations
```

---

## 2. Configuration via Environment Variables

All paths and rate limits are managed via Pydantic Settings (`BASEBALLPY_*`):

```bash
export BASEBALLPY_HOME="~/.baseballpy"
export BASEBALLPY_PROCESSED_ROOT_OVERRIDE="/fast-disk/baseball/processed"  # optional: move one tier
export BASEBALLPY_RATE_MAX_CONCURRENCY=8
export BASEBALLPY_RATE_SAVANT_RPS=2.5
export BASEBALLPY_AUDIT_ENABLED=true
```

A dotenv file is loaded only when `BASEBALLPY_ENV_FILE` names it (real environment variables win over
the file); a stray `.env` in the working directory is ignored. Or configure dynamically in Python:
```python
from pathlib import Path
from baseballpy.core.config import LakeConfig, PipelineConfig

config = PipelineConfig(
    lake=LakeConfig(home=Path("/custom/storage")),
)
```

---

## 3. Dataset-to-Function Catalog

| Provider | Dataset | Target Function | Returned Type | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Statcast** | Pitch-by-pitch search | `statcast_search(start_date, end_date)` | `pa.Table` | 119 columns (+`_extras`), automatic 5-day chunking and row-cap bisection |
| **Statcast** | Bat Tracking Leaderboard | `get_leaderboard("bat_tracking", 2024)` | `pa.Table` | Bat speed, fast swing %, blast rate |
| **Statcast** | Exit Velocity & Barrels | `get_leaderboard("exit_velocity", 2024)` | `pa.Table` | Hard-hit %, avg EV, max EV, launch angle |
| **Statcast** | Expected Statistics | `get_leaderboard("expected_statistics", 2024)` | `pa.Table` | xBA, xSLG, xwOBA, xOBP |
| **Statcast** | Sprint Speed | `get_leaderboard("sprint_speed", 2024)` | `pa.Table` | Ft/sec sprint speed, bolts |
| **Statcast** | Running Splits | `get_leaderboard("running_splits", 2024)` | `pa.Table` | Home-to-first, 90-ft split times |
| **Statcast** | Outs Above Average (OAA) | `get_leaderboard("outs_above_average", 2024)` | `pa.Table` | Range OAA, catch probability breakdowns |
| **Statcast** | Catcher Framing | `get_leaderboard("catcher_framing", 2024)` | `pa.Table` | Strike rate by zone, framing runs |
| **Statcast** | Catcher Poptime | `get_leaderboard("poptime", 2024)` | `pa.Table` | Poptime to 2B/3B, exchange time, arm speed |
| **Statcast** | Arm Strength | `get_leaderboard("arm_strength", 2024)` | `pa.Table` | Outfielder/infielder max throw velocity |
| **Statcast** | Pitch Arsenals | `get_leaderboard("pitch_arsenals", 2024)` | `pa.Table` | Pitch type frequencies, spin, movement |
| **Statcast** | ABS Challenges | `get_leaderboard("abs_challenges", 2024)` | `pa.Table` | Automated Ball-Strike challenge outcomes |
| **Retrosheet** | Play-by-play events | `retro.events(year)` | `pa.Table` | 97 fields via `chadwickpy` cwevent engine |
| **Retrosheet** | Boxscores (batting & pitching) | `retro.boxscores(year)` | `tuple[pa.Table, pa.Table]` | Game-by-game player batting & pitching |
| **Retrosheet** | Daily appearance splits | `retro.daily(year)` | `pa.Table` | 154 fields from Retrosheet daily lines |
| **Retrosheet** | In-game substitutions | `retro.substitutions(year)` | `pa.Table` | Exact lineup substitutions with inning/scores |
| **Retrosheet** | Game Logs (Regular + Postseason)| `retro.gamelogs(year, "regular")` | `pa.Table` | 161 fields: line scores, umpires, weather |
| **Retrosheet** | Ballparks Database | `retro.reference("ballparks")` | `pa.Table` | Park dimensions, coordinates, dates in use |
| **Retrosheet** | Teams Database | `retro.reference("teams")` | `pa.Table` | Historical franchise lineage from 1871 |
| **Retrosheet** | Ejections Database | `retro.reference("ejections")` | `pa.Table` | Umpire ejection logs and reasons |
| **Retrosheet** | Personnel (Coaches/Bio) | `retro.reference("coaches")` | `pa.Table` | Coaching staff and biological registry |
| **Chadwick** | Player ID Crosswalk | `crosswalk(id, from_type, to_type)` | `Any` | Fast system-to-system translation |
| **Chadwick** | Player Register Search | `get_register().search_name("Pete Alonso")`| `list[PlayerRecord]` | 16-shard index with nickname & fuzzy resolution |
| **Lahman** | Regular Season Batting (1871-2025) | `lahman.batting()` | `pa.Table` | 22 fields: G, AB, R, H, 2B, 3B, HR, RBI, SB |
| **Lahman** | Regular Season Pitching (1871-2025)| `lahman.pitching()` | `pa.Table` | 30 fields: W, L, G, GS, CG, SHO, SV, IPouts, ERA |
| **Lahman** | Master Biographical Directory | `lahman.people()` | `pa.Table` | 24 fields: names, birth/death, bats/throws |
| **Lahman** | Teams & Standings | `lahman.teams()` | `pa.Table` | 48 fields: team standings, runs, park factors |
| **Lahman** | Fielding Statistics | `lahman.fielding()` | `pa.Table` | 18 fields: PO, A, E, DP, PB, InnOuts |
| **Lahman** | Player Salaries | `lahman.salaries()` | `pa.Table` | Historical player salaries |
| **Lahman** | Hall of Fame Ballots | `lahman.hall_of_fame()` | `pa.Table` | Ballots, votes, and inductee status |
| **Lahman** | All-Star Game Rosters | `lahman.allstar()` | `pa.Table` | All-Star game rosters and starts |
| **Lahman** | Manual SABR Box Archive Import | `lahman.import_archive(path)` | `int` | Imports local SABR Box zip or folder |
| **MLB API** | Schedule & Outcomes | `mlb.schedule(season=2024)` | `pa.Table` | Game dates, teams, venues, scores |
| **MLB API** | Boxscore | `mlb.boxscore(game_pk=745789)` | `tuple[pa.Table, pa.Table]` | In-depth game boxscore batting & pitching |
| **MLB API** | Standings | `mlb.standings(season=2024)` | `pa.Table` | Division, wild-card standings, run differentials |
| **MLB API** | Active Rosters | `mlb.roster(team_id=147)` | `pa.Table` | Active 26/40-man rosters with positions |
| **MLB API** | Roster Transactions | `mlb.transactions(season=2024)` | `pa.Table` | IL placements, trades, options, call-ups |
| **MLB API** | Ballpark Venues | `mlb.venues()` | `pa.Table` | Venue metadata, turf type, locations |
| **MLB API** | Real-Time Live Game Stream | `mlb.stream_game(game_pk)` | `AsyncIterator[dict]` | Real-time pitch coordinates, state diffing |

---

## 4. End-to-End Examples

### Chadwick Register Crosswalk & Nickname Search
```python
import baseballpy as bp

# 1. Direct ID crosswalk using type-safe PlayerIdType Enum
retro_id = bp.crosswalk(660271, from_type=bp.PlayerIdType.MLBAM, to_type=bp.PlayerIdType.RETRO)
print(retro_id)  # "ohtas001"

# 2. Nickname-aware search (resolves Pete -> Peter)
reg = bp.get_register()
players = reg.search_name("Pete Alonso")
print(players[0].full_name)  # "Peter Alonso"
```

### Querying Lahman Historical Statistics (1871-2025)
```python
import baseballpy as bp
import duckdb

# 1. Fetch batting stats (cached locally as Parquet)
bat_df = bp.batting()

# 2. Or retrieve by table enum
teams_df = bp.LahmanSource().get_table(bp.LahmanTable.TEAMS)

# 3. Ingest into DuckDB for high-speed SQL
con = duckdb.connect()
con.register("batting", bat_df)
leaders = con.execute("""
    SELECT playerID, yearID, teamID, HR, SB 
    FROM batting 
    WHERE HR >= 50 AND SB >= 50
""").fetchdf()
print(leaders)
```

### Consolidated DuckDB Multi-Season Database & Cross-Source Joins
```python
import baseballpy as bp

# 1. Connect to consolidated DuckDB database
# Automatically discovers all Parquet cache partitions and registers unified views!
con = bp.connect_db()

# 2. Query across ALL downloaded seasons as a single unified PostgreSQL-style table
pitches_summary = con.sql("""
    SELECT 
        season,
        pitch_type,
        COUNT(*) as total_pitches,
        AVG(release_speed) as avg_velocity
    FROM statcast_pitches
    GROUP BY season, pitch_type
    ORDER BY season DESC, total_pitches DESC
""").pl()
print(pitches_summary)

# 3. Cross-source SQL Join (Statcast + Chadwick Crosswalk + Lahman Master Directory)
cross_join = con.sql("""
    SELECT 
        p.season,
        p.pitch_type,
        reg.name_last,
        reg.name_first,
        lahman.weight,
        lahman.height,
        AVG(p.release_speed) as avg_velo
    FROM statcast_pitches p
    JOIN chadwick_register reg ON p.pitcher = reg.key_mlbam
    LEFT JOIN lahman_people lahman ON reg.key_bbref = lahman.bbrefID
    WHERE p.season = 2024
    GROUP BY p.season, p.pitch_type, reg.name_last, reg.name_first, lahman.weight, lahman.height
    ORDER BY avg_velo DESC
    LIMIT 10
""").df()
print(cross_join)
```

### Ingesting Statcast Pitches Directly into DuckDB
```python
import baseballpy as bp

# 1. Fetch pitches across date range (automatically chunked & cached)
pitches = bp.statcast("2024-04-01", "2024-04-15")

# 2. Write directly to DuckDB zero-copy with type-safe WriteMode
bp.to_duckdb(
    pitches,
    destination="baseball.duckdb",
    table_name="statcast_pitches",
    mode=bp.WriteMode.APPEND,
)
```

### High-Speed Polars Analytics with Leaderboards
```python
import polars as pl
import baseballpy as bp

# Ingest bat tracking leaderboard using StatcastLeaderboard Enum
bat_tracking = bp.get_leaderboard(bp.StatcastLeaderboard.BAT_TRACKING, year=2024)

# Zero-copy Polars DataFrame
df = bp.to_polars(bat_tracking)

# Fast aggregation
fastest_swings = (
    df.filter(pl.col("swings") >= 100)
    .sort("avg_bat_speed", descending=True)
    .select(["player_name", "avg_bat_speed", "fast_swing_rate"])
    .head(10)
)
print(fastest_swings)
```

### Historical Retrosheet Boxscore Extraction
```python
from baseballpy.sources.retrosheet.api import RetrosheetSource

retro = RetrosheetSource()

# Download and parse full season boxscores
batting, pitching = retro.boxscores(season=2023)

print(f"Ingested {len(batting)} batting lines and {len(pitching)} pitching lines.")
```

### Real-Time Live Game Streaming
```python
import asyncio
from baseballpy.sources.mlb_api.api import MlbApiSource

mlb = MlbApiSource()


async def track_live_contest(game_pk: int):
    print(f"Subscribing to live game {game_pk}...")
    async for event in mlb.stream_game(game_pk, poll_interval=2.0):
        if event["is_pitch"]:
            print(
                f"Pitch {event['pitch_number']}: {event['pitch_type']} at "
                f"{event['start_speed']} mph ({event['description']})"
            )
        elif event["event"]:
            print(f"Play: {event['event']} - {event['description']}")


# Run streamer
# asyncio.run(track_live_contest(745789))
```

### Ingest, Inspect and Query from the CLI
```bash
baseballpy catalog status                       # which datasets are INGESTED or MISSING, and why
baseballpy catalog status --gaps                # only MISSING datasets the default ingest should fill
baseballpy ingest all --seasons 2023 --dry-run  # plan only: no requests are made
baseballpy ingest lahman chadwick               # season-less sources
baseballpy db sync && baseballpy db views       # DuckDB views over processed/ Parquet
baseballpy db query "SELECT count(*) FROM lahman_batting" --json
baseballpy doctor                               # layout, disk, versions, orphan .part files
```
The full command reference is [`CLI.md`](CLI.md) (generated from the click help).

### Inspecting Audit Telemetry via CLI
```bash
# View summary of all operations (filters: --source, --status, --since)
baseballpy audit summary

# Tail recent execution logs
baseballpy audit tail -n 20

# View throughput and cache-hit statistics
baseballpy audit stats
```
