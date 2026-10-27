"""High-level public interface for the SABR Lahman Baseball Database."""

import logging
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.sources import catalog
from baseballpy.sources.lahman.extractor import LOCAL_IMPORT, LahmanExtractor
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.lahman.quality import quality_report
from baseballpy.sources.lahman.schema import LahmanTable

logger = logging.getLogger(__name__)

#: zip-bomb guards for user-supplied archives
MAX_MEMBER_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def lahman_spec(table_name: str, schema: pa.Schema | None = None) -> DatasetSpec:
    """Registered spec for a Lahman table, or an unregistered placeholder for untyped tables."""
    if (spec := DATASETS.get(f"lahman.{table_name}")) is not None:
        return spec
    return DatasetSpec(
        source="lahman",
        name=table_name,
        view=f"lahman_{table_name.lower()}",
        schema=schema or pa.schema([]),
        partition="none",
        keys=(),
        description=f"Lahman {table_name} table (schema inferred; typed in complete-source-coverage).",
        endpoint_doc="sources/lahman.md#all-27-supported-tables",
    )


class LahmanSource:
    """Orchestrator for Lahman Baseball Database extraction, local import, and caching."""

    def __init__(self, cache_config: LakeConfig | None = None) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.extractor = LahmanExtractor(cache_config=self.cache_config)
        self.normalizer = LahmanNormalizer()
        self.raw = RawStore(self.cache_config)
        self.store = ProcessedStore(self.cache_config)

    def _import_csv(self, filename: str, data: bytes) -> None:
        """Store one user-supplied CSV in raw/ and compile it to typed Parquet in processed/."""
        table_name = Path(filename).stem
        self.raw.put("lahman", table_name, f"{table_name}.csv", data, source_ref=LOCAL_IMPORT)
        table = self.normalizer.normalize(data, table_name=table_name)
        self.store.put(
            lahman_spec(table_name, table.schema),
            table,
            source_ref=LOCAL_IMPORT,
            metadata=self._quality(table_name, table),
        )
        self.extractor.manifest_for(table_name).set_completed(
            table_name,
            records_count=len(table),
            metadata={"origin": LOCAL_IMPORT, "source": LOCAL_IMPORT},
        )

    def _people_ids(self) -> pa.ChunkedArray | None:
        """``People.playerID`` from the processed store if already present (never fetches)."""
        people = self.store.part_path(lahman_spec("People"), "data")
        if not people.exists():
            return None
        return pq.read_table(people, columns=["playerID"])["playerID"]

    def _quality(self, name: str, table: pa.Table) -> dict[str, object]:
        """Run data-quality checks; findings are logged as warnings and kept in the manifest."""
        findings = quality_report(
            name, table, people_ids=self._people_ids(), today=self.cache_config.today_or_now()
        )
        for key, value in findings.items():
            logger.warning("lahman data quality: %s %s=%s", name, key, value)
        return {"quality": findings} if findings else {}

    @staticmethod
    def _check_zip_safety(members: list[zipfile.ZipInfo]) -> None:
        """Reject path traversal and oversized members before anything is extracted."""
        total = 0
        for info in members:
            parts = Path(info.filename.replace("\\", "/")).parts
            if ".." in parts or Path(info.filename).is_absolute():
                raise ValueError(f"unsafe path in Lahman archive: {info.filename!r}")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError(f"Lahman archive member too large: {info.filename!r}")
            total += info.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Lahman archive expands beyond the allowed size")

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
            destination=str(self.cache_config.processed_root / "lahman"),
        ) as tracker:
            imported_count = 0

            # Handle ZIP file
            if path.is_file() and path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path, "r") as zf:
                    members = [
                        info
                        for info in zf.infolist()
                        if info.filename.lower().endswith(".csv")
                        and not info.filename.startswith("__MACOSX")
                    ]
                    self._check_zip_safety(members)
                    for info in members:
                        with zf.open(info) as src:
                            self._import_csv(Path(info.filename).name, src.read())
                        imported_count += 1
                tracker.set_records(imported_count)
                return imported_count

            # Handle directory
            if path.is_dir():
                for csv_file in path.glob("**/*.csv"):
                    if csv_file.name.startswith("."):
                        continue
                    self._import_csv(csv_file.name, csv_file.read_bytes())
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
        spec = lahman_spec(name_str)
        target_parquet = self.store.part_path(spec, "data")

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

            # 4. Save to processed Parquet
            if self.cache_config.enabled and len(table) > 0:
                self.store.put(
                    lahman_spec(name_str, table.schema),
                    table,
                    source_ref=self.extractor.source_ref.ref,
                    metadata=self._quality(name_str, table),
                )

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
