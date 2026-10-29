"""Export cached, typed datasets to Parquet, CSV, DuckDB or PostgreSQL (ADR 46).

One generic path for every source, driven only by the dataset registry: the schema, the key, the
season partitioning and the table name (the registry ``view`` name) all come from the
:class:`~baseballpy.core.datasets.DatasetSpec`. Input is always the cached typed Parquet in
``processed/``; nothing is downloaded or re-typed. Every export is read back and compared with the
source (rows and types) and written to the audit log.

Files (Parquet, CSV) are written by pyarrow through our sinks; DuckDB through the native
``DuckDBSink``; server databases (PostgreSQL) through ``dlt`` with the registry key as primary key.
"""

import os
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write_parquet
from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.sql import quote_ident
from baseballpy.core.stores import PARQUET_COMPRESSION, ProcessedStore
from baseballpy.sinks.csv import CsvSink, read_csv_typed
from baseballpy.sinks.dlt import DltSink, type_mismatches
from baseballpy.sinks.duckdb import DuckDBSink

#: environment variable holding the PostgreSQL connection URL
POSTGRES_URL_ENV = "BASEBALLPY_POSTGRES_URL"
#: default schema (PostgreSQL) for exported tables
DEFAULT_SCHEMA = "baseballpy"
#: default DuckDB file name inside the exports folder
DUCKDB_FILE = "baseballpy.duckdb"

Kind = Literal["file", "database"]
MODES = ("replace", "append", "merge")


@dataclass(frozen=True)
class ExportTarget:
    """A place data can be exported to."""

    name: str
    kind: Kind
    suffix: str
    description: str


#: the registry of targets; the CLI and the docs iterate it
TARGETS: dict[str, ExportTarget] = {
    t.name: t
    for t in (
        ExportTarget("parquet", "file", "parquet", "typed zstd Parquet file(s)"),
        ExportTarget("csv", "file", "csv", "UTF-8 CSV with a .schema.json type sidecar"),
        ExportTarget("duckdb", "database", "duckdb", "tables in a DuckDB file"),
        ExportTarget("postgres", "database", "", "tables in a PostgreSQL schema (via dlt)"),
    )
}


class ExportError(RuntimeError):
    """An export could not be done or its read-back check failed."""


class NoCachedDataError(ExportError):
    """The dataset has nothing in ``processed/`` yet."""


@dataclass
class ExportResult:
    """What one export did."""

    source: str
    dataset: str
    target: str
    destination: str
    rows: int
    seasons: tuple[int, ...] = ()
    seconds: float = 0.0
    verified: bool = False
    problems: list[str] = field(default_factory=list)


def available_seasons(config: LakeConfig, spec: DatasetSpec) -> list[int]:
    """Seasons of ``spec`` that have Parquet in ``processed/`` (empty for unpartitioned datasets)."""
    root = config.processed_dir(spec.source, spec.name)
    if spec.partition != "season" or not root.exists():
        return []
    found = []
    for child in root.iterdir():
        if child.is_dir() and child.name.startswith("season=") and any(child.glob("*.parquet")):
            found.append(int(child.name.removeprefix("season=")))
    return sorted(found)


def _slices(
    store: ProcessedStore, config: LakeConfig, spec: DatasetSpec, seasons: Sequence[int] | None
) -> list[tuple[int | None, pa.Table]]:
    """``(season, table)`` pairs to export, one per season (a single ``None`` season otherwise)."""
    hint = f"run `baseballpy ingest {spec.source} -d {spec.name}` first"
    if spec.partition == "season":
        have = available_seasons(config, spec)
        if not have:
            raise NoCachedDataError(f"{spec.key} has no cached data: {hint}")
        wanted = sorted(seasons) if seasons else have
        if missing := [s for s in wanted if s not in have]:
            raise NoCachedDataError(f"{spec.key} has no cached season(s) {missing}: {hint}")
        return [(season, store.read(spec, season)) for season in wanted]
    if not store.is_cached(spec) and not store.files(spec):
        raise NoCachedDataError(f"{spec.key} has no cached data: {hint}")
    return [(None, store.read(spec))]


def _out_root(config: LakeConfig, out: Path | str | None) -> Path:
    return Path(out) if out else config.exports_root


def _file_path(root: Path, spec: DatasetSpec, target: ExportTarget, season: int | None) -> Path:
    folder = root / spec.source / spec.name
    if season is not None:
        folder = folder / f"season={season}"
    return folder / f"{spec.name}.{target.suffix}"


def _export_files(
    spec: DatasetSpec,
    target: ExportTarget,
    slices: list[tuple[int | None, pa.Table]],
    root: Path,
    verify: bool,
) -> tuple[str, list[str]]:
    problems: list[str] = []
    for season, table in slices:
        path = _file_path(root, spec, target, season)
        if target.name == "parquet":
            atomic_write_parquet(table, path, compression=PARQUET_COMPRESSION)
        else:
            CsvSink().write(table, str(path))
        if verify:
            back = pq.read_table(path) if target.name == "parquet" else read_csv_typed(path)
            if not back.schema.equals(table.schema):
                problems.append(f"{path.name}: schema read back differs from the source")
            elif not back.equals(table):
                problems.append(f"{path.name}: data read back differs from the source")
    return str(root / spec.source / spec.name), problems


def _season_mode(mode: str, index: int) -> str:
    """The first slice uses the requested mode; later ones must not wipe what it wrote."""
    return mode if index == 0 or mode == "merge" else "append"


def _duckdb_path(config: LakeConfig, out: Path | str | None) -> Path:
    if out and Path(out).suffix == ".duckdb":
        return Path(out)
    return _out_root(config, out) / DUCKDB_FILE


def _export_duckdb(
    spec: DatasetSpec,
    slices: list[tuple[int | None, pa.Table]],
    config: LakeConfig,
    out: Path | str | None,
    mode: str,
    verify: bool,
) -> tuple[str, list[str]]:
    path = _duckdb_path(config, out)
    path.parent.mkdir(parents=True, exist_ok=True)
    sink_modes = {"replace": "replace", "append": "append", "merge": "upsert"}
    for index, (_, table) in enumerate(slices):
        DuckDBSink().write(
            table,
            str(path),
            table_name=spec.view,
            mode=sink_modes[_season_mode(mode, index)],
            key_columns=spec.keys,
        )
    problems: list[str] = []
    if verify:
        con = duckdb.connect(str(path), read_only=True)
        try:
            rows = con.execute(f"SELECT COUNT(*) FROM {quote_ident(spec.view)}").fetchone()  # noqa: S608
            columns = con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'main' AND table_name = ? ORDER BY ordinal_position",
                [spec.view],
            ).fetchall()
        finally:
            con.close()
        problems = _database_problems(
            spec, sum(len(t) for _, t in slices), int(rows[0]) if rows else -1, columns, mode
        )
    return f"{path}:{spec.view}", problems


def _database_problems(
    spec: DatasetSpec,
    exported_rows: int,
    stored_rows: int,
    columns: Sequence[Sequence[str]],
    mode: str,
) -> list[str]:
    problems = type_mismatches(spec.schema, {name: ty for name, ty in columns})
    if mode == "replace" and stored_rows != exported_rows:
        problems.append(f"table holds {stored_rows} rows, {exported_rows} were exported")
    elif stored_rows < exported_rows and mode != "merge":
        problems.append(f"table holds {stored_rows} rows, fewer than the {exported_rows} exported")
    elif mode == "merge" and stored_rows == 0 and exported_rows:
        problems.append("table is empty after the merge")
    return problems


def _export_postgres(
    spec: DatasetSpec,
    slices: list[tuple[int | None, pa.Table]],
    config: LakeConfig,
    url: str | None,
    schema: str,
    mode: str,
    verify: bool,
) -> tuple[str, list[str]]:
    credentials = url or os.environ.get(POSTGRES_URL_ENV)
    if not credentials:
        raise ExportError(
            f"no PostgreSQL URL: pass --url or set {POSTGRES_URL_ENV} "
            "(for example postgresql://user:password@host:5432/database)"
        )
    sink = DltSink(
        destination="postgres",
        dataset_name=schema,
        credentials=credentials,
        pipelines_dir=str(config.home / "cache" / "dlt"),
        pipeline_name="baseballpy_export",
    )
    for index, (_, table) in enumerate(slices):
        sink.write(
            table,
            spec.view,
            write_disposition=_season_mode(mode, index),
            primary_key=spec.keys if mode == "merge" else None,
        )
    problems: list[str] = []
    if verify:
        info = sink.table_info(spec.view)
        problems = _database_problems(
            spec, sum(len(t) for _, t in slices), info.rows, list(info.columns.items()), mode
        )
    return f"postgres:{schema}.{spec.view}", problems


def export_dataset(
    spec: DatasetSpec,
    target: str,
    *,
    config: LakeConfig | None = None,
    out: Path | str | None = None,
    url: str | None = None,
    schema: str = DEFAULT_SCHEMA,
    mode: str = "replace",
    seasons: Sequence[int] | None = None,
    verify: bool = True,
) -> ExportResult:
    """Export one cached dataset to ``target`` and check what was written.

    ``mode`` is ``replace`` (default), ``append`` or ``merge`` (on the registry key; databases only,
    files are always replaced). Season-partitioned datasets are exported one season at a time.
    Raises :class:`NoCachedDataError` when nothing is cached and :class:`ExportError` when the
    read-back check finds a difference.
    """
    if target not in TARGETS:
        raise ValueError(f"unknown export target {target!r}; known: {sorted(TARGETS)}")
    if mode not in MODES:
        raise ValueError(f"unknown export mode {mode!r}; known: {list(MODES)}")
    kind = TARGETS[target]
    if kind.kind == "file" and mode != "replace":
        raise ValueError(f"{target} files are always replaced; {mode!r} is for databases")
    cfg = config or LakeConfig()
    slices = _slices(ProcessedStore(cfg), cfg, spec, seasons)
    rows = sum(len(table) for _, table in slices)
    started = time.perf_counter()
    with default_audit_logger.track(
        operation="export", source=spec.source, endpoint=spec.name, destination=target
    ) as tracker:
        if kind.kind == "file":
            destination, problems = _export_files(spec, kind, slices, _out_root(cfg, out), verify)
        elif target == "duckdb":
            destination, problems = _export_duckdb(spec, slices, cfg, out, mode, verify)
        else:
            destination, problems = _export_postgres(spec, slices, cfg, url, schema, mode, verify)
        tracker.set_records(rows)
        if problems:
            raise ExportError(f"{spec.key} -> {target} failed its read-back check: {problems}")
    return ExportResult(
        source=spec.source,
        dataset=spec.name,
        target=target,
        destination=destination,
        rows=rows,
        seasons=tuple(s for s, _ in slices if s is not None),
        seconds=round(time.perf_counter() - started, 3),
        verified=verify,
    )


__all__ = [
    "DEFAULT_SCHEMA",
    "MODES",
    "POSTGRES_URL_ENV",
    "TARGETS",
    "ExportError",
    "ExportResult",
    "ExportTarget",
    "NoCachedDataError",
    "available_seasons",
    "export_dataset",
]
