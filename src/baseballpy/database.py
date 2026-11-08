"""Consolidated DuckDB catalog: views over the ``processed/`` tier of the data lake.

Views are registry-driven (:data:`baseballpy.core.datasets.DATASETS`), read only
``processed/`` Parquet (never ``raw/`` or ``cache/``), and hold no data copies.
"""

import logging
import re
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DATASETS
from baseballpy.core.layout import hint_if_legacy
from baseballpy.core.sql import quote_ident, quote_literal
from baseballpy.sources import catalog

logger = logging.getLogger(__name__)

_SEASON_DIR = re.compile(r"season=(\d{4})")
_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CROSSWALK_VIEW = "v_player_crosswalk"
SEASON_CATALOG_VIEW = "v_season_catalog"
CROSSWALK_COLUMNS = (
    "key_person",
    "key_uuid",
    "key_mlbam",
    "key_retro",
    "key_bbref",
    "key_bbref_minors",
    "key_fangraphs",
    "name_first",
    "name_last",
    "mlb_played_first",
    "mlb_played_last",
)


class DatabaseReadOnlyError(RuntimeError):
    """Raised when a read-only connection needs views that have not been created yet."""


class DatabaseTooNewError(RuntimeError):
    """The database file was written by a newer DuckDB than the one installed."""


def is_newer_format(exc: BaseException) -> bool:
    """Whether a DuckDB error says the file comes from a newer DuckDB version."""
    return isinstance(exc, duckdb.IOException) and "newer version of DuckDB" in str(exc)


def _mixed_schema_file(root: Path, schema: pa.Schema) -> str | None:
    """Name of a file at the edges of ``root`` (first and last folder, first and last file) whose
    columns differ from ``schema``, or None.

    A strict view takes its columns from one file, so a dataset that mixes schemas silently loses
    columns in SQL (ADR 87). Looking at the edges is cheap and catches the usual case: the oldest
    seasons were written before the schema gained columns. ``baseballpy catalog layout`` checks all.
    """
    folders = sorted(p for p in root.iterdir() if p.is_dir())
    for folder in dict.fromkeys([folders[0], folders[-1]] if folders else [root]):
        files = sorted(folder.glob("*.parquet"))
        for file in dict.fromkeys(files[:1] + files[-1:]):
            if not pq.read_schema(file).equals(schema, check_metadata=False):
                return file.name
    return None


def _view_sql(files_glob: Path, partitioned: bool, strict: bool) -> str:
    """``SELECT`` over a dataset's parquet parts (one consistent ``season`` column if hive).

    Registered datasets have one strict schema, so every part has the same columns and the view
    skips ``union_by_name`` (which makes DuckDB open every file to merge schemas). Datasets that
    are not registered yet (untyped) keep the merge.
    """
    parts: list[str] = []
    if partitioned:
        parts += ["hive_partitioning = true", "hive_types = {'season': 'SMALLINT'}"]
    if not strict:
        parts.append("union_by_name = true")
    options = "".join(f", {p}" for p in parts)
    return f"SELECT * FROM read_parquet({quote_literal(files_glob.as_posix())}{options})"  # noqa: S608 - glob/options are quoted with quote_literal


class BaseballDatabase:
    """Manages an embedded DuckDB database whose views cover every ingested dataset."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        cache_config: LakeConfig | None = None,
        read_only: bool = False,
    ) -> None:
        catalog.register_all()
        self.cache_config = cache_config or LakeConfig()
        hint_if_legacy(self.cache_config)
        if db_path is None:
            self.db_path = self.cache_config.database_path
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(db_path)
        self.read_only = read_only

    def _open(self, read_only: bool) -> duckdb.DuckDBPyConnection:
        if not read_only and str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            return duckdb.connect(database=str(self.db_path), read_only=read_only)
        except duckdb.IOException as exc:
            if not is_newer_format(exc):
                raise
            # The catalog holds only views (no data), so a file from a newer DuckDB is rebuilt;
            # a file the user pointed us at by hand is never touched.
            if read_only or self.db_path != self.cache_config.database_path:
                raise DatabaseTooNewError(
                    f"{self.db_path} was written by a newer DuckDB than the installed {duckdb.__version__}. "
                    "Run `baseballpy db sync` (it rebuilds the view catalog) or upgrade duckdb."
                ) from exc
            aside = self.db_path.with_name(self.db_path.name + ".newer-duckdb")
            self.db_path.replace(aside)
            logger.warning(
                "%s was written by a newer DuckDB than %s; moved it to %s and rebuilt the views",
                self.db_path,
                duckdb.__version__,
                aside,
            )
            return duckdb.connect(database=str(self.db_path), read_only=read_only)

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Open a connection; read-write syncs views, read-only requires them to exist."""
        con = self._open(self.read_only)
        if self.read_only:
            try:
                self._require_views(con)
            except DatabaseReadOnlyError:
                con.close()
                raise
        else:
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

    def _dataset_files(self, source: str, dataset: str) -> list[Path]:
        root = self.cache_config.processed_dir(source, dataset)
        return sorted(root.rglob("*.parquet")) if root.exists() else []

    def expected_views(self) -> dict[str, tuple[Path, bool, bool]]:
        """``view -> (parquet glob, hive-partitioned, strict schema)`` for datasets with data.

        Registered datasets come first; directories under ``processed/`` that are not in the
        registry yet (untyped Lahman tables, Savant leaderboards) are discovered with a warning
        so their data stays queryable.
        """
        views: dict[str, tuple[Path, bool, bool]] = {}
        known: set[tuple[str, str]] = set()
        for spec in DATASETS.values():
            known.add((spec.source, spec.name))
            if self._dataset_files(spec.source, spec.name):
                root = self.cache_config.processed_dir(spec.source, spec.name)
                views[spec.view] = (root / "**" / "*.parquet", spec.partition == "season", True)
        processed = self.cache_config.processed_root
        if processed.exists():
            for source_dir in sorted(p for p in processed.iterdir() if p.is_dir()):
                for dataset_dir in sorted(p for p in source_dir.iterdir() if p.is_dir()):
                    if (source_dir.name, dataset_dir.name) in known:
                        continue
                    if not self._dataset_files(source_dir.name, dataset_dir.name):
                        continue
                    view = f"{source_dir.name}_{dataset_dir.name}".lower()
                    if not _SAFE_NAME.match(view) or view in views:
                        logger.warning("skipping unregistered dataset dir %s", dataset_dir)
                        continue
                    partitioned = any(
                        _SEASON_DIR.fullmatch(p.name) for p in dataset_dir.iterdir() if p.is_dir()
                    )
                    views[view] = (dataset_dir / "**" / "*.parquet", partitioned, False)
        return views

    def _require_views(self, con: duckdb.DuckDBPyConnection) -> int:
        existing = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
            ).fetchall()
        }
        missing = sorted(set(self.expected_views()) - existing)
        if missing:
            raise DatabaseReadOnlyError(
                f"read-only database is missing views {missing}; "
                "run `baseballpy db sync` (read-write) first"
            )
        return len(existing)

    def _season_catalog_rows(self) -> list[tuple[str, str, int | None, int, int]]:
        """``(source, dataset, season, rows, files)`` computed from parquet footers."""
        grouped: dict[tuple[str, str, int | None], list[int]] = {}
        processed = self.cache_config.processed_root
        if not processed.exists():
            return []
        for path in processed.rglob("*.parquet"):
            rel = path.relative_to(processed).parts
            if len(rel) < 3:
                continue
            match = next((m for part in rel if (m := _SEASON_DIR.fullmatch(part))), None)
            season = int(match.group(1)) if match else None
            entry = grouped.setdefault((rel[0], rel[1], season), [0, 0])
            entry[0] += pq.ParquetFile(path).metadata.num_rows
            entry[1] += 1
        return [
            (src, ds, season, rows, files)
            for (src, ds, season), (rows, files) in sorted(
                grouped.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or 0)
            )
        ]

    def _create_season_catalog(self, con: duckdb.DuckDBPyConnection) -> None:
        rows = self._season_catalog_rows()
        if not rows:
            con.execute(
                f"CREATE OR REPLACE VIEW {SEASON_CATALOG_VIEW} AS "
                "SELECT NULL::VARCHAR AS source, NULL::VARCHAR AS dataset, "
                "NULL::SMALLINT AS season, NULL::BIGINT AS row_count, "
                "NULL::BIGINT AS files WHERE false"
            )
            return
        values = ", ".join(
            f"({quote_literal(src)}, {quote_literal(ds)}, "
            f"{'NULL' if season is None else season}, {n}, {files})"
            for src, ds, season, n, files in rows
        )
        con.execute(
            f"CREATE OR REPLACE VIEW {SEASON_CATALOG_VIEW} AS "  # noqa: S608 - constant view name
            f"SELECT source::VARCHAR AS source, dataset::VARCHAR AS dataset, "
            f"season::SMALLINT AS season, row_count::BIGINT AS row_count, files::BIGINT AS files "
            f"FROM (VALUES {values}) AS t(source, dataset, season, row_count, files)"
        )

    def _drop_stale_views(self, con: duckdb.DuckDBPyConnection) -> None:
        """Drop views whose data folder is gone (after a rename or a deleted dataset).

        The database holds views only, so dropping loses nothing; without it a renamed table would
        leave its old view behind and every query of it would fail.
        """
        keep = {*self.expected_views(), CROSSWALK_VIEW, SEASON_CATALOG_VIEW}
        for (name,) in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
        ).fetchall():
            if name not in keep:
                logger.info("dropping stale view %s (its data folder is gone)", name)
                con.execute(f"DROP VIEW IF EXISTS {quote_ident(name)}")

    def sync_views(self, con: duckdb.DuckDBPyConnection | None = None) -> int:
        """Create or replace a view per dataset that has Parquet on disk; returns the count."""
        if self.read_only and con is None:
            raise DatabaseReadOnlyError("cannot sync views on a read-only database")
        close_con = con is None
        if con is None:
            con = self._open(False)
        try:
            with default_audit_logger.track(
                operation="database_sync_views",
                source="database",
                destination=str(self.db_path),
            ) as tracker:
                views_registered = 0
                specs = {s.view: s for s in DATASETS.values()}
                for view, (pattern, partitioned, strict) in self.expected_views().items():
                    if strict and (spec := specs.get(view)) is not None:
                        odd = _mixed_schema_file(pattern.parent.parent, spec.schema)
                        if odd is not None:
                            logger.warning(
                                "view %s: %s differs from the registered schema, so SQL may miss "
                                "columns; run `baseballpy compact` to rewrite old files",
                                view,
                                odd,
                            )
                    con.execute(
                        f"CREATE OR REPLACE VIEW {quote_ident(view)} AS "
                        f"{_view_sql(pattern, partitioned, strict)}"
                    )
                    views_registered += 1

                existing = {
                    row[0]
                    for row in con.execute(
                        "SELECT table_name FROM information_schema.tables WHERE table_type = 'VIEW'"
                    ).fetchall()
                }
                if "chadwick_register" in existing:
                    columns = {
                        row[0] for row in con.execute("DESCRIBE chadwick_register").fetchall()
                    }
                    wanted = [c for c in CROSSWALK_COLUMNS if c in columns]
                    if wanted:
                        con.execute(
                            f"CREATE OR REPLACE VIEW {CROSSWALK_VIEW} AS "  # noqa: S608 - identifiers are quoted with quote_ident
                            f"SELECT {', '.join(quote_ident(c) for c in wanted)} "
                            "FROM chadwick_register"
                        )
                        views_registered += 1
                self._create_season_catalog(con)
                views_registered += 1
                self._drop_stale_views(con)

                tracker.set_records(views_registered)
                return views_registered
        finally:
            if close_con:
                con.close()


def connect_db(
    db_path: Path | str | None = None,
    cache_config: LakeConfig | None = None,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Connect to the consolidated DuckDB baseball database and return an active connection."""
    db = BaseballDatabase(db_path=db_path, cache_config=cache_config, read_only=read_only)
    return db.connect()


def sync_database(
    db_path: Path | str | None = None,
    cache_config: LakeConfig | None = None,
) -> int:
    """Synchronize every processed dataset into DuckDB views (read-write)."""
    db = BaseballDatabase(db_path=db_path, cache_config=cache_config)
    return db.sync_views()
