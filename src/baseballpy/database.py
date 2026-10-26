"""Consolidated DuckDB database catalog for multi-season baseball data queries.

Automatically registers Hive-partitioned views over Statcast, Retrosheet,
Lahman, and Chadwick Parquet stores, enabling cross-source SQL joins.
"""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig


class BaseballDatabase:
    """Manages an embedded DuckDB database with consolidated multi-season Parquet views."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        cache_config: CacheConfig | None = None,
        read_only: bool = False,
    ) -> None:
        self.cache_config = cache_config or CacheConfig()
        if db_path is None:
            db_dir = self.cache_config.base_dir / "databases"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = db_dir / "baseball.duckdb"
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.read_only = read_only

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Open a DuckDB connection and sync all available Parquet views."""
        target = str(self.db_path)
        con = duckdb.connect(database=target, read_only=self.read_only)
        self.sync_views(con)
        return con

    @contextmanager
    def session(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """Context manager providing an active DuckDB connection."""
        con = self.connect()
        try:
            yield con
        finally:
            con.close()

    def sync_views(self, con: duckdb.DuckDBPyConnection | None = None) -> int:
        """Scan local Parquet cache partitions and create or replace consolidated views."""
        views_registered = 0
        close_con = False

        if con is None:
            con = duckdb.connect(database=str(self.db_path), read_only=self.read_only)
            close_con = True

        try:
            with default_audit_logger.track(
                operation="database_sync_views",
                source="database",
                destination=str(self.db_path),
            ) as tracker:
                # 1. Statcast pitches (Hive-partitioned by season=YYYY)
                statcast_dir = self.cache_config.statcast_dir
                if statcast_dir.exists():
                    parquet_files = list(statcast_dir.glob("**/*.parquet"))
                    if parquet_files:
                        pattern = (statcast_dir / "**" / "*.parquet").as_posix()
                        con.execute(
                            f"CREATE OR REPLACE VIEW statcast_pitches AS "
                            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true, union_by_name = true);"
                        )
                        views_registered += 1

                # 2. Retrosheet Events (Hive-partitioned by season=YYYY)
                events_dir = self.cache_config.retrosheet_dir / "processed" / "events"
                if events_dir.exists():
                    event_files = list(events_dir.glob("**/*.parquet"))
                    if event_files:
                        pattern = (events_dir / "**" / "*.parquet").as_posix()
                        con.execute(
                            f"CREATE OR REPLACE VIEW retrosheet_events AS "
                            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true, union_by_name = true);"
                        )
                        views_registered += 1

                # 3. Retrosheet Boxscores Batting
                box_bat_dir = self.cache_config.retrosheet_dir / "processed" / "boxscores_batting"
                if box_bat_dir.exists():
                    box_bat_files = list(box_bat_dir.glob("**/*.parquet"))
                    if box_bat_files:
                        pattern = (box_bat_dir / "**" / "*.parquet").as_posix()
                        con.execute(
                            f"CREATE OR REPLACE VIEW retrosheet_boxscores_batting AS "
                            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true, union_by_name = true);"
                        )
                        views_registered += 1

                # 4. Retrosheet Boxscores Pitching
                box_pit_dir = self.cache_config.retrosheet_dir / "processed" / "boxscores_pitching"
                if box_pit_dir.exists():
                    box_pit_files = list(box_pit_dir.glob("**/*.parquet"))
                    if box_pit_files:
                        pattern = (box_pit_dir / "**" / "*.parquet").as_posix()
                        con.execute(
                            f"CREATE OR REPLACE VIEW retrosheet_boxscores_pitching AS "
                            f"SELECT * FROM read_parquet('{pattern}', hive_partitioning = true, union_by_name = true);"
                        )
                        views_registered += 1

                # 5. Retrosheet Game Logs
                gamelog_dir = self.cache_config.retrosheet_dir / "processed" / "gamelogs"
                if gamelog_dir.exists():
                    gamelog_files = list(gamelog_dir.glob("*.parquet"))
                    if gamelog_files:
                        pattern = (gamelog_dir / "*.parquet").as_posix()
                        con.execute(
                            f"CREATE OR REPLACE VIEW retrosheet_gamelogs AS "
                            f"SELECT * FROM read_parquet('{pattern}', union_by_name = true);"
                        )
                        views_registered += 1

                # 6. Lahman Historical Tables (27 canonical tables)
                lahman_dir = self.cache_config.lahman_dir / "processed"
                if lahman_dir.exists():
                    for lahman_file in lahman_dir.glob("*.parquet"):
                        table_name = f"lahman_{lahman_file.stem.lower()}"
                        posix_path = lahman_file.as_posix()
                        con.execute(
                            f"CREATE OR REPLACE VIEW {table_name} AS "
                            f"SELECT * FROM read_parquet('{posix_path}');"
                        )
                        views_registered += 1

                # 7. Chadwick Player Register
                chadwick_file = self.cache_config.chadwick_dir / "processed" / "register.parquet"
                if chadwick_file.exists():
                    posix_path = chadwick_file.as_posix()
                    con.execute(
                        f"CREATE OR REPLACE VIEW chadwick_register AS "
                        f"SELECT * FROM read_parquet('{posix_path}');"
                    )
                    views_registered += 1

                tracker.set_records(views_registered)
                return views_registered
        finally:
            if close_con:
                con.close()


def connect_db(
    db_path: Path | str | None = None,
    cache_config: CacheConfig | None = None,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Connect to the consolidated DuckDB baseball database and return an active connection."""
    db = BaseballDatabase(db_path=db_path, cache_config=cache_config, read_only=read_only)
    return db.connect()


def sync_database(
    db_path: Path | str | None = None,
    cache_config: CacheConfig | None = None,
) -> int:
    """Synchronize all Parquet cache tables into the DuckDB database."""
    db = BaseballDatabase(db_path=db_path, cache_config=cache_config)
    return db.sync_views()
