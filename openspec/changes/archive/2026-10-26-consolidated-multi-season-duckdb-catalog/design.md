# Design: Consolidated Multi-Season DuckDB Catalog and Partition Organization

## 1. Storage & Partitioning Strategy

### Statcast Hive Partitioning
```text
~/.baseballpy/cache/statcast/processed/
├── season=2023/
│   ├── 2023-04-01_2023-04-05.parquet
│   └── 2023-04-06_2023-04-10.parquet
└── season=2024/
    ├── 2024-03-28_2024-04-01.parquet
    └── ...
```

In `StatcastExtractor._get_cache_path(start_dt, end_dt, **filters)`:
- Target path: `statcast_dir / f"season={start_dt.year}" / f"{filename}.parquet"`.
- Backward compatibility: If the new path does not exist but `statcast_dir / f"{filename}.parquet"` exists, use the legacy path so existing caches continue to resolve without re-downloading.

### Cross-Source Storage Layout
- **Retrosheet:**
  - Events: `retrosheet/processed/events/season=YYYY/events.parquet`
  - Boxscores Batting: `retrosheet/processed/boxscores_batting/season=YYYY/batting.parquet`
  - Boxscores Pitching: `retrosheet/processed/boxscores_pitching/season=YYYY/pitching.parquet`
  - Game Logs: `retrosheet/processed/gamelogs/gamelogs_regular.parquet`
- **Lahman:**
  - `lahman/processed/{table_name}.parquet` (27 tables, cumulative 1871–2025)
- **Chadwick:**
  - `chadwick/processed/register.parquet` (cumulative player register)

---

## 2. DuckDB Catalog Architecture (`baseballpy.database`)

### Class: `BaseballDatabase`
Located at `src/baseballpy/database.py`.

```python
class BaseballDatabase:
    """Manages an embedded DuckDB database with consolidated multi-season views."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        cache_config: CacheConfig | None = None,
        read_only: bool = False,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.db_path = db_path or self.cache_config.base_dir / "databases" / "baseball.duckdb"
        self.read_only = read_only
        self._connection: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Return an active DuckDB connection with all available views registered."""
        ...

    def sync_views(self) -> int:
        """Scan Parquet cache directories and create or replace consolidated views."""
        ...
```

### Registered Views:
1. `statcast_pitches`:
   `CREATE OR REPLACE VIEW statcast_pitches AS SELECT * FROM read_parquet(['.../statcast/processed/**/*.parquet'], hive_partitioning=true, union_by_name=true);`
2. `retrosheet_events`:
   `CREATE OR REPLACE VIEW retrosheet_events AS SELECT * FROM read_parquet(['.../retrosheet/processed/events/**/*.parquet'], hive_partitioning=true, union_by_name=true);`
3. `retrosheet_boxscores_batting`:
   `CREATE OR REPLACE VIEW retrosheet_boxscores_batting AS SELECT * FROM read_parquet(['.../retrosheet/processed/boxscores_batting/**/*.parquet'], hive_partitioning=true, union_by_name=true);`
4. `retrosheet_boxscores_pitching`:
   `CREATE OR REPLACE VIEW retrosheet_boxscores_pitching AS SELECT * FROM read_parquet(['.../retrosheet/processed/boxscores_pitching/**/*.parquet'], hive_partitioning=true, union_by_name=true);`
5. `retrosheet_gamelogs`:
   `CREATE OR REPLACE VIEW retrosheet_gamelogs AS SELECT * FROM read_parquet(['.../retrosheet/processed/gamelogs/*.parquet'], union_by_name=true);`
6. `lahman_<table_name>` (e.g. `lahman_batting`, `lahman_pitching`, `lahman_people`, `lahman_teams`):
   Points to individual table Parquet files.
7. `chadwick_register`:
   Points to `chadwick/processed/register.parquet`.

### Cross-System SQL Joins:
DuckDB can execute queries joining these datasets directly:
```sql
SELECT
    p.game_year,
    p.pitcher,
    reg.name_last,
    reg.name_first,
    lahman.weight,
    lahman.height,
    AVG(p.release_speed) as avg_fastball_velo
FROM statcast_pitches p
JOIN chadwick_register reg ON p.pitcher = reg.key_mlbam
LEFT JOIN lahman_people lahman ON reg.key_bbref = lahman.bbrefID
WHERE p.pitch_type = 'FF'
GROUP BY p.game_year, p.pitcher, reg.name_last, reg.name_first, lahman.weight, lahman.height;
```

---

## 3. Public Top-Level API
Exposed in `src/baseballpy/__init__.py`:
- `bp.connect_db(db_path=None, read_only=False) -> duckdb.DuckDBPyConnection`
- `bp.sync_database(db_path=None) -> int`
- `bp.BaseballDatabase`
