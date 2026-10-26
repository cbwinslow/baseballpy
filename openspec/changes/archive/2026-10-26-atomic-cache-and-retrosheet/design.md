# Design: Two-Phase Atomic Ingestion Gates & Retrosheet Engine

## 1. Two-Phase Atomic Write Pattern

```text
Stream incoming bytes from HTTP / Parser
                    │
                    ▼
          {target_path}.part
                    │
       Integrity Check: Valid Parquet / Non-empty CSV
                    │
                    ▼
         os.replace(part, target)
                    │
                    ▼
         Manifest Checkpoint Update
         manifest.set_chunk(chunk_id, status="COMPLETED")
```

If any failure occurs before `os.replace()`, the `.part` file is deleted or ignored, and the manifest leaves the chunk in `UNFINISHED` status. Upon restart, the downloader checks `manifest.is_completed(chunk_id)`:
- If `True`: Skip network download entirely.
- If `False`: Safely download afresh.

## 2. Retrosheet Folder & Ingestion Topology

```text
~/.baseballpy/cache/retrosheet/
├── raw/
│   ├── manifest.json
│   └── 2024/
│       ├── TEAM2024
│       ├── 2024BOS.EVA / .EVN
│       └── BOS2024.ROS
└── processed/
    └── events/
        ├── manifest.json
        └── season=2024/
            └── part-0.parquet
```

## 3. Retrosheet Parsing Engine
`baseballpy.sources.retrosheet` downloads the raw event and roster files from GitHub's Fastly CDN mirror (`https://raw.githubusercontent.com/chadwickbureau/retrosheet/master/`).
Then `chadwickpy` parses the `.EVA` / `.EVN` files in memory:
- Events table (`cwevent` equivalent): Pitch sequence, batter, pitcher, runners, base out state, event code.
- Game logs table: 161 columns strictly coerced from CSV text into dates, integers, and categoricals.
- Rosters: Player ID, last name, first name, bats, throws, team, position.
All output tables are stored in `processed/` as PyArrow Parquet files.
