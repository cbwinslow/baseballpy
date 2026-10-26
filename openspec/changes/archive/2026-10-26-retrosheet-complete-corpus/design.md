# Design: Retrosheet Complete Corpus & Chadwick Suite Ingestion

## 1. Directory Structure & Partitioning

All Retrosheet data is stored under the partitioned cache directory `~/.baseballpy/cache/retrosheet/`:
```text
~/.baseballpy/cache/retrosheet/
├── manifest.json                  # Checkpoint manifest of downloaded & processed partitions
├── raw/
│   ├── seasons/{year}/            # Unmodified .EVA, .EVN, .EVE, .ROS files
│   ├── gamelog/                   # GL1871.TXT ... GL2024.TXT, GLWC.TXT, GLDV.TXT, etc.
│   └── reference/                 # ballparks.csv, teams.csv, ejections.csv, etc.
└── processed/
    ├── events/season={year}/      # Parquet files for 97-field play-by-play
    ├── boxscores_batting/season={year}/
    ├── boxscores_pitching/season={year}/
    ├── daily_splits/season={year}/
    ├── substitutions/season={year}/
    ├── comments/season={year}/
    ├── gamelogs/type={type}/season={year}/
    └── reference/table={name}/
```

## 2. In-Memory Chadwick Parsing Engine

`chadwickpy.tools` provides modular generators that take season raw files in memory and yield structured rows:
- `cwbox.process_game(game)`: Yields batting and pitching lines with official scorebook apparatus.
- `daily.daily_lines(game)`: Yields daily player lines.
- `sub.sub_lines(game)`: Yields substitution events.
- `comment.comment_lines(game)`: Yields comments.
- `events.event_rows(game)`: Yields 97-field play-by-play events.

The normalizer consumes these generators and converts them directly into `pyarrow.Table` using strictly defined Arrow schemas:
- `BOX_BATTING_SCHEMA`: `game_id`, `team_id`, `player_id`, `slot`, `pos`, `ab`, `r`, `h`, `d`, `t`, `hr`, `rbi`, `bb`, `ibb`, `so`, `hbp`, `sh`, `sf`, `sb`, `cs`, `gidp`.
- `BOX_PITCHING_SCHEMA`: `game_id`, `team_id`, `pitcher_id`, `starter_fl`, `outs_recorded`, `bf`, `h`, `r`, `er`, `bb`, `ibb`, `so`, `hr`, `hbp`, `wp`, `bk`, `pitches`, `strikes`.
- `DAILY_SPLITS_SCHEMA`: `game_id`, `player_id`, `team_id`, `date`, `slot`, `pos`, `ab`, `r`, `h`, `d`, `t`, `hr`, `rbi`, `bb`, `so`, `po`, `a`, `e`, `ip_outs`.
- `SUBSTITUTIONS_SCHEMA`: `game_id`, `inning`, `event_num`, `team_id`, `player_id`, `slot`, `pos`, `removed_player_id`, `removed_pos`.
- `REFERENCE_SCHEMAS`: Explicit physical schemas for `ballparks`, `teams`, `ejections`, `coaches`, `relatives`, `biofile`.

## 3. Atomic Downloads & Manifest Checkpointing

Every network operation routes through `ManifestTracker` and `atomic_write`:
- Checks manifest before network calls.
- If partition is complete and valid, loads cached raw file without hitting GitHub CDN.
- Atomic commit prevents corrupted partial files on network drops.
