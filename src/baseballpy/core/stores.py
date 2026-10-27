"""Raw and processed tiers of the data lake (atomic writes, sha256, footer validation)."""

import hashlib
import logging
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write, atomic_write_parquet
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec
from baseballpy.core.layout import ensure_version_file, hint_if_legacy

logger = logging.getLogger(__name__)

PARQUET_COMPRESSION = "zstd"


def _safe_chunk_id(chunk_id: str) -> str:
    """Reject chunk ids that could escape the dataset directory."""
    if not chunk_id or any(sep in chunk_id for sep in ("/", "\\", "..")):
        raise ValueError(f"invalid chunk id {chunk_id!r}")
    return chunk_id


class _EmptyStreamError(Exception):  # noqa: N818 - internal control flow
    """Raised inside ``put_stream`` when no rows arrived (the part file is discarded)."""


def manifest_key(name: str, season: int | None) -> str:
    """Manifest key for a chunk: ``season=YYYY/<name>`` when season-partitioned."""
    return f"season={season}/{name}" if season is not None else name


class RawStore:
    """Immutable upstream bytes under ``raw/<source>/<dataset>/[season=YYYY/]``."""

    def __init__(self, config: LakeConfig | None = None) -> None:
        self.config = config or LakeConfig()
        hint_if_legacy(self.config)

    def path_for(self, source: str, dataset: str, name: str, season: int | None = None) -> Path:
        """Location of a raw file (does not create anything)."""
        return self.config.raw_dir(source, dataset, season) / _safe_chunk_id(name)

    def put(
        self,
        source: str,
        dataset: str,
        name: str,
        data: bytes,
        *,
        season: int | None = None,
        source_ref: str | None = None,
        etag: str = "",
    ) -> Path:
        """Atomically write ``data`` and record size + sha256 in the dataset's raw manifest."""
        ensure_version_file(self.config)
        directory = self.config.raw_dir(source, dataset, season, create=True)
        path = directory / _safe_chunk_id(name)
        with atomic_write(path) as part:
            part.write_bytes(data)
        self.config.dataset_manifest(source, dataset, "raw", season).set_completed(
            name,
            etag=etag,
            metadata={
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "season": season,
                "source_ref": source_ref,
            },
        )
        return path

    def get(self, source: str, dataset: str, name: str, season: int | None = None) -> bytes:
        """Read a raw file back (``FileNotFoundError`` if absent)."""
        return self.path_for(source, dataset, name, season).read_bytes()

    def verify(self, source: str, dataset: str, name: str, season: int | None = None) -> bool:
        """True when the file exists and matches the sha256 recorded in the manifest."""
        path = self.path_for(source, dataset, name, season)
        if not path.exists():
            return False
        manifest = self.config.dataset_manifest(source, dataset, "raw", season)
        entry = manifest.get_chunk(name)
        if not entry or "sha256" not in entry:
            return False
        return bool(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"])


class ProcessedStore:
    """Typed Parquet under ``processed/<source>/<dataset>/[season=YYYY/]part-<chunk>.parquet``."""

    def __init__(self, config: LakeConfig | None = None) -> None:
        self.config = config or LakeConfig()
        hint_if_legacy(self.config)

    def dataset_dir(self, spec: DatasetSpec, season: int | None = None) -> Path:
        """Directory holding ``spec``'s parquet parts for ``season`` (no creation)."""
        return self.config.processed_dir(spec.source, spec.name, season)

    @staticmethod
    def _check_season(spec: DatasetSpec, season: int | None) -> None:
        if spec.partition == "season" and season is None:
            raise ValueError(f"{spec.key} is season-partitioned; season is required")
        if spec.partition == "none" and season is not None:
            raise ValueError(f"{spec.key} is not season-partitioned; got season={season}")

    def part_path(self, spec: DatasetSpec, chunk_id: str, season: int | None = None) -> Path:
        """Deterministic part file path so reruns overwrite rather than duplicate."""
        self._check_season(spec, season)
        return self.dataset_dir(spec, season) / f"part-{_safe_chunk_id(chunk_id)}.parquet"

    def put(
        self,
        spec: DatasetSpec,
        table: pa.Table,
        *,
        chunk_id: str = "data",
        season: int | None = None,
        source_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Atomically write ``table`` (footer validated) and record the chunk in the manifest."""
        path = self.part_path(spec, chunk_id, season)
        ensure_version_file(self.config)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_parquet(table, path, compression=PARQUET_COMPRESSION)
        self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(
            manifest_key(chunk_id, season),
            records_count=table.num_rows,
            metadata={"season": season, "source_ref": source_ref, **(metadata or {})},
        )
        return path

    def put_stream(
        self,
        spec: DatasetSpec,
        batches: Iterable[pa.Table],
        *,
        chunk_id: str = "data",
        season: int | None = None,
        source_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Stream tables into one atomic Parquet part (one row group per batch); returns rows.

        Nothing is written when the stream is empty. The footer row count is validated before
        the atomic rename, exactly like :meth:`put`.
        """
        path = self.part_path(spec, chunk_id, season)
        ensure_version_file(self.config)
        path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        try:
            with atomic_write(path) as part:
                writer: pq.ParquetWriter | None = None
                try:
                    for batch in batches:
                        if batch.num_rows == 0:
                            continue
                        if writer is None:
                            writer = pq.ParquetWriter(
                                part, spec.schema, compression=PARQUET_COMPRESSION
                            )
                        writer.write_table(
                            batch if batch.schema.equals(spec.schema) else batch.cast(spec.schema)
                        )
                        total += batch.num_rows
                finally:
                    if writer is not None:
                        writer.close()
                if writer is None:
                    raise _EmptyStreamError
                footer_rows = pq.ParquetFile(part).metadata.num_rows
                if footer_rows != total:
                    raise ValueError(f"parquet footer row count {footer_rows} != {total} written")
        except _EmptyStreamError:
            # remember that this chunk legitimately has no rows so it is not re-parsed every run
            self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(
                manifest_key(chunk_id, season),
                records_count=0,
                metadata={"season": season, "source_ref": source_ref, **(metadata or {})},
            )
            return 0
        self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(
            manifest_key(chunk_id, season),
            records_count=total,
            metadata={"season": season, "source_ref": source_ref, **(metadata or {})},
        )
        return total

    def is_cached(
        self, spec: DatasetSpec, chunk_id: str = "data", season: int | None = None
    ) -> bool:
        """True when the manifest recorded the chunk COMPLETED and its part (if any rows) exists."""
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        entry = manifest.get_chunk(manifest_key(chunk_id, season))
        if entry is None or entry.get("status") != "COMPLETED":
            return False
        if self.part_path(spec, chunk_id, season).exists():
            return True
        return entry.get("records_count") == 0

    def read_part(
        self, spec: DatasetSpec, chunk_id: str = "data", season: int | None = None
    ) -> pa.Table:
        """Read one stored part back (an empty table for a chunk recorded with zero rows)."""
        path = self.part_path(spec, chunk_id, season)
        if not path.exists():
            return spec.schema.empty_table()
        return pq.read_table(path)

    def files(self, spec: DatasetSpec) -> list[Path]:
        """Every parquet part currently stored for ``spec``."""
        root = self.dataset_dir(spec)
        return sorted(root.rglob("*.parquet")) if root.exists() else []

    def read(self, spec: DatasetSpec, season: int | None = None) -> pa.Table:
        """Concatenate the stored parts (optionally one season) into one table."""
        root = self.dataset_dir(spec, season)
        parts = sorted(root.rglob("*.parquet")) if root.exists() else []
        if not parts:
            return spec.schema.empty_table()
        return pa.concat_tables([pq.read_table(p) for p in parts], promote_options="permissive")

    def row_count(self, spec: DatasetSpec) -> int:
        """Total rows across all parts, read from parquet footers."""
        return sum(pq.ParquetFile(p).metadata.num_rows for p in self.files(spec))


def reprocess(
    spec: DatasetSpec,
    season: int | None,
    parse: Callable[[Path], pa.Table],
    *,
    config: LakeConfig | None = None,
    chunk_id: str = "data",
) -> Path:
    """Re-parse ``raw/`` for ``spec`` (one season) offline and rewrite the processed part.

    ``parse`` receives the raw directory and returns the typed table; no network is used.
    """
    cfg = config or LakeConfig()
    raw = cfg.raw_dir(spec.source, spec.name, season)
    if not raw.exists():
        raise FileNotFoundError(f"no raw data for {spec.key} season={season} at {raw}")
    table = parse(raw)
    return ProcessedStore(cfg).put(spec, table, chunk_id=chunk_id, season=season)
