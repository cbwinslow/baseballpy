"""High-level public interface for the SABR Lahman Baseball Database."""

import shutil
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write_parquet
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import CacheConfig
from baseballpy.sources.lahman.extractor import LahmanExtractor
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.lahman.schema import LahmanTable


class LahmanSource:
    """Orchestrator for Lahman Baseball Database extraction, local import, and caching."""

    def __init__(self, cache_config: CacheConfig | None = None) -> None:
        self.cache_config = cache_config or CacheConfig()
        self.extractor = LahmanExtractor(cache_config=self.cache_config)
        self.normalizer = LahmanNormalizer()
        self.raw_dir = self.cache_config.lahman_dir / "raw"
        self.processed_dir = self.cache_config.lahman_dir / "processed"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def import_archive(self, archive_path: Path | str) -> int:
        """Import a local Lahman ZIP archive or unzipped directory downloaded from SABR Box.

        Copies raw CSVs into cache raw/ directory and compiles them directly into
        strongly-typed Parquet tables in processed/.
        """
        path = Path(archive_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Lahman archive path does not exist: {path}")

        with default_audit_logger.track(
            operation="lahman_import_archive",
            source="lahman",
            endpoint=str(path),
            destination=str(self.processed_dir),
        ) as tracker:
            imported_count = 0

            # Handle ZIP file
            if path.is_file() and path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path, "r") as zf:
                    for member in zf.namelist():
                        if member.lower().endswith(".csv") and not member.startswith("__MACOSX"):
                            filename = Path(member).name
                            target_raw = self.raw_dir / filename
                            with zf.open(member) as src, open(target_raw, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            # Process immediately to Parquet
                            table_name = target_raw.stem
                            content = target_raw.read_bytes()
                            table = self.normalizer.normalize(content, table_name=table_name)
                            target_parquet = self.processed_dir / f"{table_name}.parquet"
                            atomic_write_parquet(table, target_parquet)
                            self.extractor.manifest.set_completed(
                                table_name, records_count=len(table)
                            )
                            imported_count += 1
                tracker.set_records(imported_count)
                return imported_count

            # Handle directory
            if path.is_dir():
                for csv_file in path.glob("**/*.csv"):
                    if csv_file.name.startswith("."):
                        continue
                    target_raw = self.raw_dir / csv_file.name
                    shutil.copy2(csv_file, target_raw)

                    table_name = target_raw.stem
                    content = target_raw.read_bytes()
                    table = self.normalizer.normalize(content, table_name=table_name)
                    target_parquet = self.processed_dir / f"{table_name}.parquet"
                    atomic_write_parquet(table, target_parquet)
                    self.extractor.manifest.set_completed(table_name, records_count=len(table))
                    imported_count += 1
                tracker.set_records(imported_count)
                return imported_count

            raise ValueError(f"Unsupported archive format: {path}. Expected .zip or directory.")

    def get_table(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> pa.Table:
        """Extract, normalize, and cache any Lahman table."""
        name_str = str(table_name)
        target_parquet = self.processed_dir / f"{name_str}.parquet"

        with default_audit_logger.track(
            operation="lahman_get_table",
            source="lahman",
            endpoint=name_str,
            destination=str(target_parquet),
        ) as tracker:
            # 1. Load from Parquet cache if available
            if not refresh and target_parquet.exists():
                tracker.set_cache_hit(True)
                table = pq.read_table(target_parquet)
                tracker.set_records(len(table))
                return table

            # 2. Extract raw CSV (from cache or remote GitHub mirror)
            raw_bytes = self.extractor.extract_table(name_str, refresh=refresh)

            # 3. Normalize into strongly typed PyArrow Table
            table = self.normalizer.normalize(raw_bytes, table_name=name_str)

            # 4. Save to processed Parquet cache
            if self.cache_config.enabled and len(table) > 0:
                atomic_write_parquet(table, target_parquet)

            tracker.set_cache_hit(False)
            tracker.set_records(len(table))
            return table

    def people(self, refresh: bool = False) -> pa.Table:
        """Extract People table (biographical player registry)."""
        return self.get_table(LahmanTable.PEOPLE, refresh=refresh)

    def batting(self, refresh: bool = False) -> pa.Table:
        """Extract regular season Batting statistics (1871-2025)."""
        return self.get_table(LahmanTable.BATTING, refresh=refresh)

    def pitching(self, refresh: bool = False) -> pa.Table:
        """Extract regular season Pitching statistics (1871-2025)."""
        return self.get_table(LahmanTable.PITCHING, refresh=refresh)

    def teams(self, refresh: bool = False) -> pa.Table:
        """Extract Teams standings and seasonal team totals."""
        return self.get_table(LahmanTable.TEAMS, refresh=refresh)

    def fielding(self, refresh: bool = False) -> pa.Table:
        """Extract Fielding statistics by position and year."""
        return self.get_table(LahmanTable.FIELDING, refresh=refresh)

    def salaries(self, refresh: bool = False) -> pa.Table:
        """Extract historical player Salaries."""
        return self.get_table(LahmanTable.SALARIES, refresh=refresh)

    def hall_of_fame(self, refresh: bool = False) -> pa.Table:
        """Extract Hall of Fame voting outcomes and ballots."""
        return self.get_table(LahmanTable.HALL_OF_FAME, refresh=refresh)

    def allstar(self, refresh: bool = False) -> pa.Table:
        """Extract All-Star Game roster appearances."""
        return self.get_table(LahmanTable.ALLSTAR_FULL, refresh=refresh)

    def appearances(self, refresh: bool = False) -> pa.Table:
        """Extract player season Appearances across positions."""
        return self.get_table(LahmanTable.APPEARANCES, refresh=refresh)

    def parks(self, refresh: bool = False) -> pa.Table:
        """Extract ballpark metadata and historical park identifiers."""
        return self.get_table(LahmanTable.PARKS, refresh=refresh)

    def managers(self, refresh: bool = False) -> pa.Table:
        """Extract managerial records and win-loss records."""
        return self.get_table(LahmanTable.MANAGERS, refresh=refresh)

    def awards_players(self, refresh: bool = False) -> pa.Table:
        """Extract major awards won by players (MVP, Cy Young, Rookie of the Year)."""
        return self.get_table(LahmanTable.AWARDS_PLAYERS, refresh=refresh)

    def series_post(self, refresh: bool = False) -> pa.Table:
        """Extract postseason series outcomes (World Series, LCS, LDS, Wild Card)."""
        return self.get_table(LahmanTable.SERIES_POST, refresh=refresh)

    def list_tables(self) -> list[str]:
        """Return list of all 27 standard Lahman table names."""
        return [t.value for t in LahmanTable]
