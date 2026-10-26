# Design: Lahman Database Ingestion and Modern Chadwick Register Shards

## 1. Chadwick Names Register Architecture

### Shard Ingestion Workflow
```text
┌──────────────────────────────────────────────────────────────────┐
│                   GitHub (chadwickbureau/register)               │
│  - Commit Check: /repos/chadwickbureau/register/commits?path=data│
│  - 16 Hex Shards: data/people-0.csv ... data/people-f.csv        │
│  - Auxiliary: data/names.csv, data/links.csv                     │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ Bounded Concurrency (Semaphore 4)
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ChadwickShardExtractor                         │
│  - Checks local manifest for latest commit SHA                   │
│  - If unchanged: load local cache directly                       │
│  - If updated / missing: download all 16 shards to .part files   │
│  - Download names.csv and links.csv                              │
└─────────────────────────────────┬────────────────────────────────┘
                                  │ Coerce & Normalize
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ChadwickShardNormalizer                        │
│  - Concat 16 shards into unified PyArrow Table                   │
│  - Schema: key_person, key_uuid, key_mlbam, key_retro,          │
│    key_bbref, key_fangraphs, key_npb, key_wikidata,              │
│    name_last, name_first, name_given, birth_year, etc.           │
│  - Normalize names.csv for nickname aliases (e.g. Pete -> Peter) │
│  - Atomically save to ~/.baseballpy/cache/chadwick/people.parquet│
└─────────────────────────────────┬────────────────────────────────┘
                                  │ In-Memory Crosswalk Index
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                   ChadwickPlayerCrosswalk                        │
│  - Fast hash indices: MLBAM, Retrosheet, BBRef, FanGraphs, UUID  │
│  - Crosswalk resolution: resolve(id_val, from_type, to_type)     │
│  - Fuzzy name search with Levenshtein ratio                      │
│  - Nickname expansion via names.csv index                        │
│  - Enums: PlayerIdType                                           │
└──────────────────────────────────────────────────────────────────┘
```

### PlayerIdType Enum
```python
from enum import StrEnum


class PlayerIdType(StrEnum):
    PERSON = "key_person"
    UUID = "key_uuid"
    MLBAM = "key_mlbam"
    RETRO = "key_retro"
    BBREF = "key_bbref"
    FANGRAPHS = "key_fangraphs"
    NPB = "key_npb"
    WIKIDATA = "key_wikidata"
```

## 2. Lahman Database Architecture (1871–2025)

### Storage Layout
```text
~/.baseballpy/cache/lahman/
├── raw/
│   ├── Batting.csv
│   ├── Pitching.csv
│   ├── People.csv
│   ├── Teams.csv
│   └── ... (all 27 CSVs)
├── processed/
│   ├── Batting.parquet
│   ├── Pitching.parquet
│   ├── People.parquet
│   └── ... (all 27 Parquet files)
└── manifest.json
```

### Ingestion Flow
1. **Mode A (Automated Extraction):**
   - Source: `https://raw.githubusercontent.com/cbwinslow/lahman-database-csv/main/data/{table}.csv`
   - Downloads all 27 tables into `raw/` using two-phase atomic writes.
   - Normalizes raw CSVs into physical PyArrow types (integers, dates, categoricals) and saves into `processed/{table}.parquet`.
2. **Mode B (Manual Local Import):**
   - User downloads official zip archive from `sabr.org` / `sabr.app.box.com`.
   - User calls:
     ```python
     from baseballpy.sources.lahman import LahmanSource

     lahman = LahmanSource()
     lahman.import_archive("~/Downloads/lahman-2025-csv.zip")
     ```
   - Validates CSV headers, extracts/copies into `raw/`, and immediately compiles into `processed/` Parquet partitions.

### LahmanTable Enum
```python
class LahmanTable(StrEnum):
    ALLSTAR_FULL = "AllstarFull"
    APPEARANCES = "Appearances"
    AWARDS_MANAGERS = "AwardsManagers"
    AWARDS_PLAYERS = "AwardsPlayers"
    AWARDS_SHARE_MANAGERS = "AwardsShareManagers"
    AWARDS_SHARE_PLAYERS = "AwardsSharePlayers"
    BATTING = "Batting"
    BATTING_POST = "BattingPost"
    COLLEGE_PLAYING = "CollegePlaying"
    FIELDING = "Fielding"
    FIELDING_OF = "FieldingOF"
    FIELDING_OF_SPLIT = "FieldingOFsplit"
    FIELDING_POST = "FieldingPost"
    HALL_OF_FAME = "HallOfFame"
    HOME_GAMES = "HomeGames"
    MANAGERS = "Managers"
    MANAGERS_HALF = "ManagersHalf"
    PARKS = "Parks"
    PEOPLE = "People"
    PITCHING = "Pitching"
    PITCHING_POST = "PitchingPost"
    SALARIES = "Salaries"
    SCHOOLS = "Schools"
    SERIES_POST = "SeriesPost"
    TEAMS = "Teams"
    TEAMS_FRANCHISES = "TeamsFranchises"
    TEAMS_HALF = "TeamsHalf"
```
