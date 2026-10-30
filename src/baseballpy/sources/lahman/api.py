"""High-level public interface for the SABR Lahman Baseball Database."""

import hashlib
import logging
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS, DatasetSpec
from baseballpy.core.stores import ProcessedStore, RawStore, schema_matches
from baseballpy.core.upstream import CONTENT_SHA256, Fingerprint, is_current, stored_fingerprint
from baseballpy.sources import catalog
from baseballpy.sources.lahman.extractor import (
    DOCUMENT_DATASET,
    LOCAL_IMPORT,
    LahmanExtractor,
    data_rows,
)
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.lahman.quality import (
    FOREIGN_KEYS,
    PARENT_TABLES,
    foreign_key_findings,
    quality_report,
)
from baseballpy.sources.lahman.schema import LAHMAN_SCHEMAS, LahmanTable, canonical_table_name

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


@dataclass(frozen=True)
class LoadedTable:
    """A table and whether it was served from a cache (memory or processed Parquet)."""

    table: pa.Table
    from_cache: bool


@dataclass
class ImportReport:
    """What the last :meth:`LahmanSource.import_archive` did."""

    tables: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    raw_only: list[str] = field(default_factory=list)


def _is_document(filename: str) -> bool:
    lower = Path(filename).name.lower()
    return not lower.endswith(".csv") and lower.startswith(("readme", "license", "licence"))


def _content_fingerprint(data: bytes) -> Fingerprint:
    return Fingerprint(CONTENT_SHA256, hashlib.sha256(data).hexdigest(), origin=LOCAL_IMPORT)


class LahmanSource:
    """Orchestrator for Lahman Baseball Database extraction, local import, and caching."""

    def __init__(self, cache_config: LakeConfig | None = None) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        self.extractor = LahmanExtractor(cache_config=self.cache_config)
        self.normalizer = LahmanNormalizer()
        self.raw = RawStore(self.cache_config)
        self.store = ProcessedStore(self.cache_config)
        self.last_import = ImportReport()
        #: tables already read in this process: name -> (parquet stamp, loaded at, table)
        self._memory: dict[str, tuple[tuple[int, int], float, pa.Table]] = {}

    # -- user-supplied archives -----------------------------------------------------------------

    def _import_csv(self, filename: str, data: bytes) -> str:
        """Store one supplied CSV: a known table is typed into Parquet, anything else stays raw.

        Returns ``"table"`` or ``"raw_only"``. Unknown CSV files are never turned into unregistered
        tables; their bytes are kept in ``raw/`` and a warning names them.
        """
        stem = Path(filename).stem
        fingerprint = _content_fingerprint(data)
        try:
            table_name = canonical_table_name(stem)
        except ValueError:
            logger.warning(
                "supplied file %s is not one of the 27 Lahman tables; its bytes are kept in raw/ "
                "and no table is built from it",
                filename,
            )
            self.raw.put(
                "lahman",
                stem,
                f"{stem}.csv",
                data,
                source_ref=LOCAL_IMPORT,
                upstream=fingerprint,
                records=data_rows(data),
                extra={"origin": LOCAL_IMPORT, "source": LOCAL_IMPORT},
            )
            return "raw_only"
        self.raw.put(
            "lahman",
            table_name,
            f"{table_name}.csv",
            data,
            source_ref=LOCAL_IMPORT,
            upstream=fingerprint,
            records=data_rows(data),
            extra={"origin": LOCAL_IMPORT, "source": LOCAL_IMPORT},
        )
        table = self.normalizer.normalize(data, table_name=table_name)
        self.store.put(
            lahman_spec(table_name, table.schema),
            table,
            source_ref=LOCAL_IMPORT,
            metadata={**self._quality(table_name, table), "upstream": fingerprint.to_dict()},
        )
        self._recheck_children(table_name)
        return "table"

    def _import_document(self, filename: str, data: bytes) -> None:
        """Keep a supplied README, licence or data dictionary in ``raw/lahman/documents/``."""
        self.raw.put(
            "lahman",
            DOCUMENT_DATASET,
            Path(filename).name,
            data,
            source_ref=LOCAL_IMPORT,
            upstream=_content_fingerprint(data),
            extra={"origin": LOCAL_IMPORT, "source": LOCAL_IMPORT},
        )

    def _import_member(self, filename: str, data: bytes) -> None:
        lower = filename.lower()
        if lower.endswith(".csv"):
            kind = self._import_csv(filename, data)
            (self.last_import.tables if kind == "table" else self.last_import.raw_only).append(
                Path(filename).stem
            )
        elif _is_document(filename):
            self._import_document(filename, data)
            self.last_import.documents.append(Path(filename).name)

    def _parents(self) -> Callable[[str], pa.Table | None]:
        """Loader of stored parent tables for the relationship checks (read once per pass)."""
        loaded: dict[str, pa.Table | None] = {}

        def parent(name: str) -> pa.Table | None:
            if name not in loaded:
                path = self.store.part_path(lahman_spec(name), "data")
                loaded[name] = pq.read_table(path) if path.exists() else None
            return loaded[name]

        return parent

    def _quality(self, name: str, table: pa.Table) -> dict[str, object]:
        """Run data-quality checks; findings are logged as warnings and kept in the manifest."""
        findings = quality_report(
            name, table, parents=self._parents(), today=self.cache_config.today_or_now()
        )
        for key, value in findings.items():
            logger.warning("lahman data quality: %s %s=%s", name, key, value)
        return {"quality": findings} if findings else {}

    def _recheck_children(self, parent_name: str) -> None:
        """A parent table was stored: recheck the tables that point into it.

        Without this, a table stored before ``People`` (or ``Teams``, ...) would never be checked
        against it, because the result would depend on the order the tables were loaded in.
        """
        if parent_name not in PARENT_TABLES:
            return
        parents = self._parents()
        for child in sorted(LAHMAN_SCHEMAS):
            relations = [
                fk
                for fk in FOREIGN_KEYS
                if fk.parent == parent_name and fk.applies_to(child, LAHMAN_SCHEMAS[child].names)
            ]
            path = self.store.part_path(lahman_spec(child), "data")
            if not relations or not path.exists():
                continue
            columns = sorted({c for fk in relations for c in fk.columns})
            table = pq.read_table(path, columns=columns)
            fresh = {
                key: count
                for key, count in foreign_key_findings(child, table, parents).items()
                if any(key == fk.label for fk in relations)
            }
            self._write_orphan_findings(child, {fk.label for fk in relations}, fresh)

    def _write_orphan_findings(self, child: str, labels: set[str], fresh: dict[str, int]) -> None:
        """Replace the stored findings of the given relationships in the child's manifest."""
        manifest = self.cache_config.dataset_manifest("lahman", child)
        entry = manifest.get_chunk("data")
        if entry is None:
            return
        stored = dict(entry.get("quality") or {})
        if {k: v for k, v in stored.items() if k in labels} == fresh:
            return
        stored = {k: v for k, v in stored.items() if k not in labels}
        stored.update(fresh)
        updated = {k: v for k, v in entry.items() if k != "quality"}
        if stored:
            updated["quality"] = stored
        manifest.put_entry("data", updated)
        for key, count in fresh.items():
            logger.warning("lahman data quality: %s %s=%s", child, key, count)

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

        Copies the raw CSVs into ``raw/`` and compiles the 27 known tables into strongly-typed
        Parquet in ``processed/``; the release's README, licence and data dictionary are kept in
        ``raw/lahman/documents/``; a CSV that is not one of the 27 tables is kept raw only, with a
        warning. Returns the number of tables imported; :attr:`last_import` lists everything.
        """
        path = Path(archive_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Lahman archive path does not exist: {path}")
        self.last_import = ImportReport()

        with default_audit_logger.track(
            operation="lahman_import_archive",
            source="lahman",
            endpoint=str(path),
            destination=str(self.cache_config.processed_root / "lahman"),
        ) as tracker:
            if path.is_file() and path.suffix.lower() == ".zip":
                with zipfile.ZipFile(path, "r") as zf:
                    members = [
                        info
                        for info in zf.infolist()
                        if not info.is_dir() and not info.filename.startswith("__MACOSX")
                    ]
                    self._check_zip_safety(members)
                    for info in members:
                        with zf.open(info) as src:
                            self._import_member(Path(info.filename).name, src.read())
            elif path.is_dir():
                for file in sorted(path.glob("**/*")):
                    if file.is_file() and not file.name.startswith("."):
                        self._import_member(file.name, file.read_bytes())
            else:
                raise ValueError(f"Unsupported archive format: {path}. Expected .zip or directory.")
            self._memory.clear()
            tracker.set_records(len(self.last_import.tables))
            return len(self.last_import.tables)

    # -- reading tables ---------------------------------------------------------------------------

    def _memory_hit(self, name: str, parquet: Path, refresh: bool) -> pa.Table | None:
        """The table from this process's memory while its Parquet is unchanged and not expired."""
        kept = self._memory.get(name)
        if refresh or kept is None or not parquet.exists():
            return None
        stamp, loaded_at, table = kept
        status = parquet.stat()
        ttl = self.cache_config.ttl_for("lahman")
        if stamp != (status.st_mtime_ns, status.st_size):
            return None
        if ttl is not None and time.monotonic() - loaded_at >= ttl:
            return None
        return table

    def _raw_fingerprint(self, name: str) -> Fingerprint | None:
        """Fingerprint of the raw file held; entries stored without one are identified by content."""
        entry = self.extractor.file_entry(name)
        if (found := stored_fingerprint(entry)) is not None or entry is None:
            return found
        digest = entry.get("sha256")
        if isinstance(digest, str) and digest:
            return Fingerprint(CONTENT_SHA256, digest, origin=str(entry.get("source_ref", "")))
        return None

    def _processed_is_current(self, name: str, parquet: Path) -> bool:
        """The Parquet is current when it was built from the raw file we hold (same fingerprint)."""
        raw_fingerprint = self._raw_fingerprint(name)
        if raw_fingerprint is None or not parquet.exists():
            return False
        processed = self.cache_config.dataset_manifest("lahman", name).get_chunk("data")
        return schema_matches(lahman_spec(name), processed) and is_current(
            processed, expected=raw_fingerprint
        )

    def load_table(self, table_name: str | LahmanTable, refresh: bool = False) -> LoadedTable:
        """Extract, normalize, and cache any Lahman table; says whether a cache served it.

        Both cache tiers are checked with the shared ``is_current``: the raw CSV against the
        fingerprint the pinned git tree lists (or the pinned commit offline), the processed Parquet
        against the fingerprint of the raw file it was built from. Table names ignore letter case.
        """
        name = canonical_table_name(table_name)
        spec = lahman_spec(name)
        parquet = self.store.part_path(spec, "data")

        with default_audit_logger.track(
            operation="lahman_get_table",
            source="lahman",
            endpoint=name,
            destination=str(parquet),
        ) as tracker:
            if (kept := self._memory_hit(name, parquet, refresh)) is not None:
                tracker.set_cache_hit(True)
                tracker.set_records(len(kept))
                return LoadedTable(kept, True)

            raw_current = not refresh and self.extractor.is_current(name)
            if raw_current and self._processed_is_current(name, parquet):
                table = pq.read_table(parquet)
                self._remember(name, parquet, table)
                tracker.set_cache_hit(True)
                tracker.set_records(len(table))
                return LoadedTable(table, True)

            raw_bytes = self.extractor.extract_table(name, refresh=refresh)
            table = self.normalizer.normalize(raw_bytes, table_name=name)
            if self.cache_config.enabled and len(table) > 0:
                fingerprint = self._raw_fingerprint(name)
                local = self.extractor.is_local(name)
                self.store.put(
                    lahman_spec(name, table.schema),
                    table,
                    source_ref=LOCAL_IMPORT if local else self.extractor.source_ref.ref,
                    metadata={
                        **self._quality(name, table),
                        **({"upstream": fingerprint.to_dict()} if fingerprint else {}),
                    },
                )
                self._recheck_children(name)
                self._remember(name, parquet, table)
            tracker.set_cache_hit(False)
            tracker.set_records(len(table))
            return LoadedTable(table, raw_current)

    def _remember(self, name: str, parquet: Path, table: pa.Table) -> None:
        if parquet.exists():
            status = parquet.stat()
            self._memory[name] = ((status.st_mtime_ns, status.st_size), time.monotonic(), table)

    def get_table(
        self,
        table_name: str | LahmanTable,
        refresh: bool = False,
    ) -> pa.Table:
        """Extract, normalize, and cache any Lahman table (names ignore letter case)."""
        return self.load_table(table_name, refresh=refresh).table

    def clear_cache(self) -> None:
        """Forget the tables kept in memory by this source."""
        self._memory.clear()

    def people(self, refresh: bool = False) -> pa.Table:
        """Biographical player registry (People)."""
        return self.get_table(LahmanTable.PEOPLE, refresh=refresh)

    def batting(self, refresh: bool = False) -> pa.Table:
        """Regular season batting (Batting)."""
        return self.get_table(LahmanTable.BATTING, refresh=refresh)

    def pitching(self, refresh: bool = False) -> pa.Table:
        """Regular season pitching (Pitching)."""
        return self.get_table(LahmanTable.PITCHING, refresh=refresh)

    def teams(self, refresh: bool = False) -> pa.Table:
        """Yearly team stats and standings (Teams)."""
        return self.get_table(LahmanTable.TEAMS, refresh=refresh)

    def fielding(self, refresh: bool = False) -> pa.Table:
        """Regular season fielding (Fielding)."""
        return self.get_table(LahmanTable.FIELDING, refresh=refresh)

    def salaries(self, refresh: bool = False) -> pa.Table:
        """Player salaries (Salaries)."""
        return self.get_table(LahmanTable.SALARIES, refresh=refresh)

    def hall_of_fame(self, refresh: bool = False) -> pa.Table:
        """Hall of Fame voting (HallOfFame)."""
        return self.get_table(LahmanTable.HALL_OF_FAME, refresh=refresh)

    def allstar(self, refresh: bool = False) -> pa.Table:
        """All-Star appearances (AllstarFull)."""
        return self.get_table(LahmanTable.ALLSTAR_FULL, refresh=refresh)

    def appearances(self, refresh: bool = False) -> pa.Table:
        """Positions played per season (Appearances)."""
        return self.get_table(LahmanTable.APPEARANCES, refresh=refresh)

    def parks(self, refresh: bool = False) -> pa.Table:
        """Ballparks (Parks)."""
        return self.get_table(LahmanTable.PARKS, refresh=refresh)

    def managers(self, refresh: bool = False) -> pa.Table:
        """Managerial records (Managers)."""
        return self.get_table(LahmanTable.MANAGERS, refresh=refresh)

    def awards_players(self, refresh: bool = False) -> pa.Table:
        """Player awards (AwardsPlayers)."""
        return self.get_table(LahmanTable.AWARDS_PLAYERS, refresh=refresh)

    def series_post(self, refresh: bool = False) -> pa.Table:
        """Post-season series (SeriesPost)."""
        return self.get_table(LahmanTable.SERIES_POST, refresh=refresh)

    def list_tables(self) -> list[str]:
        """Return list of all 27 standard Lahman table names."""
        return [t.value for t in LahmanTable]
