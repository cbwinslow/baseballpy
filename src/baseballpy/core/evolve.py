"""Bring Parquet files written under an older schema up to the registered one (ADR 87).

A schema can gain typed columns after files were written (B-303 added ``name_slug`` columns to 142
datasets). Until then the upstream values sat in the ``_extras`` JSON column of every old file. This
module does the two things that make old and new files one dataset again, offline and without a
download:

* :func:`promote_extras` moves the values out of ``_extras`` into the new typed columns (cast with
  the same rules and quarantine as an ingest, :func:`map_to_schema`) and removes the moved keys from
  ``_extras``, so nothing is stored twice and nothing is lost;
* :func:`migrate_dataset` rewrites every file of a dataset whose columns differ from the registered
  schema (verify, then atomic swap) and, for chunks that were fingerprinted, records that they now
  match the schema, so the next ingest does not download them again.
"""

import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import duckdb
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write_parquet
from baseballpy.core.compacted import (
    CHUNK_MAP_KEY,
    INTO,
    RETIRED_COLUMNS,
    align_to_schema,
    chunk_map,
    write_compacted,
)
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.listing import visible_parquet
from baseballpy.core.quarantine import Quarantine
from baseballpy.core.schema_tools import EXTRAS, UPSTREAM_KEY, map_to_schema
from baseballpy.core.stores import part_filename, spec_fingerprint

logger = logging.getLogger(__name__)

_COMPRESSION = "zstd"


@dataclass
class MigrateReport:
    """What one dataset's schema migration did (or would do)."""

    dataset: str
    files_checked: int = 0
    files_rewritten: int = 0
    rows: int = 0
    promoted: dict[str, int] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)


def _keys_of(column: pa.Field) -> list[str]:
    """Upstream names a schema column can be found under in ``_extras``, best first."""
    upstream = (column.metadata or {}).get(UPSTREAM_KEY, b"").decode("utf-8")
    keys = [k for k in upstream.split("|") if k] + [column.name]
    return [k for k in dict.fromkeys(keys) if '"' not in k and "\\" not in k]


def promote_extras(
    table: pa.Table,
    schema: pa.Schema,
    *,
    source: str,
    dataset: str,
    quarantine: Quarantine | None = None,
    counts: dict[str, int] | None = None,
) -> pa.Table:
    """``table`` with exactly the columns of ``schema``; values found in ``_extras`` are moved.

    A schema column the table lacks is read from ``_extras`` under its upstream name (or its own),
    cast with quarantine, and the key is removed from ``_extras``. A column with no value in
    ``_extras`` stays empty. ``counts`` receives how many cells each column gained.
    """
    missing = [f for f in schema if f.name not in table.column_names and f.name != EXTRAS]
    if not missing or EXTRAS not in table.column_names:
        return align_to_schema(table, schema)
    extras = pl.from_arrow(table[EXTRAS])
    if not isinstance(extras, pl.Series):
        raise TypeError("_extras must be one column")
    found: dict[str, pl.Series] = {}
    claimed: list[str] = []
    for column in missing:
        keys = _keys_of(column)
        values = [
            extras.str.json_path_match(f'$["{k}"]').alias(f"v{i}") for i, k in enumerate(keys)
        ]
        merged = pl.DataFrame(values).select(pl.coalesce(pl.all()).alias(column.name))[column.name]
        if merged.null_count() < len(merged):
            found[column.name] = merged
            claimed.extend(keys)
    if not found:
        return align_to_schema(table, schema)
    strings = pa.table({name: series.to_arrow() for name, series in found.items()})
    typed = map_to_schema(
        strings,
        pa.schema([f for f in missing if f.name in found]),
        source=source,
        dataset=dataset,
        quarantine=quarantine,
    )
    out = table
    for name in typed.column_names:
        out = out.append_column(schema.field(name), typed[name])
        if counts is not None:
            counts[name] = counts.get(name, 0) + (len(typed[name]) - typed[name].null_count)
    out = out.set_column(
        out.schema.get_field_index(EXTRAS),
        pa.field(EXTRAS, pa.string()),
        _without_keys(table[EXTRAS], claimed),
    )
    return align_to_schema(out, schema)


def _without_keys(extras: pa.ChunkedArray, keys: list[str]) -> pa.Array:
    """``_extras`` JSON strings with ``keys`` removed; an emptied object becomes NULL."""
    patch = "{" + ",".join(f'"{k}":null' for k in dict.fromkeys(keys)) + "}"
    con = duckdb.connect()
    try:
        con.register("t", pa.table({"e": extras}))
        result = con.sql(
            "SELECT CASE WHEN json_merge_patch(e, ?)::VARCHAR = '{}' THEN NULL "
            "ELSE json_merge_patch(e, ?)::VARCHAR END FROM t",
            params=[patch, patch],
        ).to_arrow_table()
    finally:
        con.close()
    return result.column(0).combine_chunks().cast(pa.string())


def _differs(path: Path, schema: pa.Schema) -> bool:
    return not pq.read_schema(path).equals(schema, check_metadata=False)


def _rewrite(path: Path, spec: DatasetSpec, quarantine: Quarantine, counts: dict[str, int]) -> int:
    """Rewrite one part or compacted file under the registered schema; returns its rows."""
    table = pq.read_table(path)
    old_cols = [n for n in table.column_names if n != EXTRAS]
    spans = chunk_map(path) if CHUNK_MAP_KEY in (pq.read_schema(path).metadata or {}) else None
    done = promote_extras(
        table.replace_schema_metadata(None),
        spec.schema,
        source=spec.source,
        dataset=spec.name,
        quarantine=quarantine,
        counts=counts,
    )
    if done.num_rows != table.num_rows:
        raise ValueError(f"{path.name}: {done.num_rows} rows after migration, had {table.num_rows}")
    for (
        name
    ) in old_cols:  # nothing already typed may change (a retired column is dropped on purpose)
        if name in RETIRED_COLUMNS:
            continue
        if not _same(table[name], done[name]):
            raise ValueError(f"{path.name}: column {name} changed during migration")
    if spans is None:
        atomic_write_parquet(done, path, compression=_COMPRESSION)
    else:
        write_compacted(
            path,
            spec.schema,
            [(key, done.slice(first, count)) for key, (first, count) in spans.items()],
        )
    return int(done.num_rows)


def _same(before: pa.ChunkedArray, after: pa.ChunkedArray) -> bool:
    if pa.types.is_dictionary(before.type):
        before = before.cast(before.type.value_type)
    if pa.types.is_dictionary(after.type):
        after = after.cast(after.type.value_type)
    return bool(before.cast(after.type).equals(after))


def migrate_dataset(
    spec: DatasetSpec,
    config: LakeConfig | None = None,
    *,
    dry_run: bool = False,
    quarantine: Quarantine | None = None,
) -> MigrateReport:
    """Rewrite every file of ``spec`` whose columns differ from the registered schema.

    A file that cannot be migrated cleanly is left untouched and listed in ``failed``. A chunk gets
    the current schema fingerprint after a successful rewrite only when its stored fingerprint is
    exactly the one the file's old columns (and the spec's parser ``revision``) would have produced:
    then the schema is the only difference and the rewrite closed it. Anything else stays marked
    stale, so the next ingest re-downloads it.
    """
    cfg = config or LakeConfig()
    report = MigrateReport(spec.key)
    root = cfg.processed_dir(spec.source, spec.name)
    if not root.exists():
        return report
    quarantine = quarantine or Quarantine()
    manifest = cfg.dataset_manifest(spec.source, spec.name, "processed")
    entries = manifest.chunks()
    done: dict[str, str] = {}  # file -> fingerprint its chunks carried if it was only a column gap
    for path in sorted(visible_parquet(root)):
        if path.name.startswith("seg-"):
            continue  # a segment file is rebuilt from raw, never rewritten: its commit line names its sha256
        report.files_checked += 1
        if not _differs(path, spec.schema):
            continue
        old_print = spec_fingerprint(replace(spec, schema=pq.read_schema(path)))
        report.files_rewritten += 1
        if dry_run:
            continue
        try:
            report.rows += _rewrite(path, spec, quarantine, report.promoted)
        except (ValueError, pa.ArrowException) as exc:
            report.files_rewritten -= 1
            report.failed.append(f"{path.relative_to(root).as_posix()}: {exc}")
            logger.error("schema migration failed for %s: %s", path, exc)
            continue
        done[path.relative_to(root).as_posix()] = old_print
    if done:
        fresh = spec_fingerprint(spec)
        updates: dict[str, dict[str, Any]] = {}
        for key, entry in entries.items():
            rel = _entry_file(key, entry, spec, cfg)
            if rel in done and entry.get("schema_sha256") == done[rel]:
                updates[key] = {**entry, "schema_sha256": fresh}
        if updates:
            manifest.put_entries(updates)
    return report


def _entry_file(key: str, entry: dict[str, Any], spec: DatasetSpec, cfg: LakeConfig) -> str:
    """Path (relative to the dataset folder) of the file that holds a manifest chunk."""
    if entry.get(INTO):
        return str(entry[INTO])
    season = (
        int(key.split("/", 1)[0].removeprefix("season=")) if key.startswith("season=") else None
    )
    name = key.split("/", 1)[1] if season is not None else key
    folder = cfg.processed_dir(spec.source, spec.name, season)
    root = cfg.processed_dir(spec.source, spec.name)
    return (folder / part_filename(spec.name, name, season)).relative_to(root).as_posix()
