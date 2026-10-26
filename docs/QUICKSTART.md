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
uv add "baseballpy[all]"  # Includes retrosheet, streaming, and pandas support
```

---

## 2. Configuration via Environment Variables

All paths and rate limits are managed via Pydantic Settings (`BASEBALLPY_*`):

```bash
export BASEBALLPY_HOME="~/.baseballpy"
export BASEBALLPY_CACHE_DIR="/data/baseball_cache"
export BASEBALLPY_RATE_MAX_CONCURRENCY=8
export BASEBALLPY_RATE_SAVANT_RPS=2.5
export BASEBALLPY_AUDIT_ENABLED=true
```

Or configure dynamically in Python:
```python
from pathlib import Path
from baseballpy.core.config import CacheConfig, PipelineConfig

config = PipelineConfig(
    cache=CacheConfig(base_dir=Path("/custom/storage")),
)
```

---

## 3. Dataset-to-Function Catalog

| Provider | Dataset | Target Function | Returned Type | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Statcast** | Pitch-by-pitch search | `statcast_search(start_date, end_date)` | `pa.Table` | 94 columns, automatic 5-day chunking |
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
| **Chadwick** | Player ID Crosswalk | `chadwick.search(last="Ohtani")` | `pa.Table` | Cross-links MLBAM, Retro, B-Ref, FanGraphs |
| **MLB API** | Schedule & Outcomes | `mlb.schedule(season=2024)` | `pa.Table` | Game dates, teams, venues, scores |
| **MLB API** | Boxscore | `mlb.boxscore(game_pk=745789)` | `tuple[pa.Table, pa.Table]` | In-depth game boxscore batting & pitching |
| **MLB API** | Standings | `mlb.standings(season=2024)` | `pa.Table` | Division, wild-card standings, run differentials |
| **MLB API** | Active Rosters | `mlb.roster(team_id=147)` | `pa.Table` | Active 26/40-man rosters with positions |
| **MLB API** | Roster Transactions | `mlb.transactions(season=2024)` | `pa.Table` | IL placements, trades, options, call-ups |
| **MLB API** | Ballpark Venues | `mlb.venues()` | `pa.Table` | Venue metadata, turf type, locations |
| **MLB API** | Real-Time Live Game Stream | `mlb.stream_game(game_pk)` | `AsyncIterator[dict]` | Real-time pitch coordinates, state diffing |

---

## 4. End-to-End Examples

### Ingesting Statcast Pitches Directly into DuckDB
```python
from baseballpy.sources.statcast import statcast_search
from baseballpy.sinks.duckdb import DuckDBSink

# 1. Fetch pitches across date range (automatically chunked & cached)
pitches = statcast_search(start_date="2024-04-01", end_date="2024-04-15")

# 2. Write directly to DuckDB zero-copy
sink = DuckDBSink()
sink.write(pitches, destination="baseball.duckdb", table_name="statcast_pitches")
```

### High-Speed Polars Analytics
```python
from baseballpy.sources.statcast import get_leaderboard
from baseballpy.sinks.polars import PolarsSink

# Ingest bat tracking leaderboard
bat_tracking = get_leaderboard("bat_tracking", year=2024)

# Zero-copy Polars DataFrame
df = PolarsSink().to_dataframe(bat_tracking)

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

### Inspecting Audit Telemetry via CLI
```bash
# View summary of all operations
baseballpy audit summary

# Tail recent execution logs
baseballpy audit tail -n 20

# View throughput and cache-hit statistics
baseballpy audit stats
```
