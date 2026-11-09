"""Raw and processed tiers of the data lake (atomic writes, sha256, footer validation)."""

import hashlib
import logging
import threading
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.atomic import atomic_write, atomic_write_parquet
from baseballpy.core.compacted import (
    INTO,
    holds_chunk,
    read_chunk,
    release_chunk,
)
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, with_lineage
from baseballpy.core.layout import ensure_version_file, hint_if_legacy
from baseballpy.core.listing import dataset_files
from baseballpy.core.rawfiles import (
    GZIP,
    GZIP_SUFFIX,
    gzip_bytes,
    is_compressible,
    logical_sha256,
    read_logical,
    stored_path,
)
from baseballpy.core.upstream import ETAG, Fingerprint

logger = logging.getLogger(__name__)

PARQUET_COMPRESSION = "zstd"


#: characters Windows forbids in a file name (a lake built on Linux must open on Windows)
_ILLEGAL_NAME_CHARS = frozenset('<>:"|?*')
#: device names Windows reserves, with or without an extension
_RESERVED_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)
#: longest chunk id; keeps raw and processed paths far below the 260-character Windows limit
MAX_CHUNK_ID_LENGTH = 120


def portable_name_problem(name: str) -> str | None:
    """Why ``name`` would not be a safe file name on every OS (``None`` when it is portable)."""
    if not name:
        return "it is empty"
    if any(sep in name for sep in ("/", "\\")) or ".." in name:
        return "it could leave its directory"
    if len(name) > MAX_CHUNK_ID_LENGTH:
        return f"it is longer than {MAX_CHUNK_ID_LENGTH} characters"
    if any(ch in _ILLEGAL_NAME_CHARS or ord(ch) < 32 for ch in name):
        return "it has a character Windows forbids in file names"
    if name.endswith((".", " ")):
        return "it ends with a dot or a space"
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        return "it is a reserved Windows device name"
    return None


def _safe_chunk_id(chunk_id: str) -> str:
    """Reject chunk ids that would not be a safe file name on every OS (or could escape the folder)."""
    problem = portable_name_problem(chunk_id)
    if problem is not None:
        raise ValueError(f"invalid chunk id {chunk_id!r}: {problem}")
    return chunk_id


class _EmptyStreamError(Exception):  # noqa: N818 - internal control flow
    """Raised inside ``put_stream`` when no rows arrived (the part file is discarded)."""


def schema_fingerprint(schema: pa.Schema) -> str:
    """Digest of a schema's column names and types (order matters); stored with every chunk."""
    text = ";".join(f"{field.name}:{field.type}" for field in schema)
    return hashlib.sha256(text.encode()).hexdigest()


def spec_fingerprint(spec: DatasetSpec) -> str:
    """The digest stored with a chunk: the schema's, plus the spec's parser ``revision`` when it has one."""
    digest = schema_fingerprint(spec.schema)
    if not spec.revision:
        return digest
    return hashlib.sha256(f"{digest};revision={spec.revision}".encode()).hexdigest()


def segment_fingerprint(spec: DatasetSpec) -> str:
    """The digest of a segment file of ``spec``: its schema plus the lineage column.

    It is the digest of the file's own columns, which is what a commit line records. The parser
    ``revision`` is not in it (the writer does not know the spec), so a revision bump is applied by
    rebuilding the season from raw, which the rebuild does for every segment it is asked to. The
    ``spec_fingerprint`` of the same spec is unchanged by the lineage column, so no chunk written
    before it looks stale.
    """
    return schema_fingerprint(with_lineage(spec.schema))


def segment_matches(spec: DatasetSpec, stored_digest: str | None) -> bool:
    """False when a segment file was written under a different schema than ``spec`` has now."""
    return bool(stored_digest) and stored_digest == segment_fingerprint(spec)


def schema_matches(spec: DatasetSpec, entry: Mapping[str, Any] | None) -> bool:
    """False when the chunk was written under a different schema than ``spec`` has now.

    A chunk written before schemas were fingerprinted carries none and is trusted (like the other
    legacy entries); everything written from now on is rebuilt after a schema change. A spec with
    a parser ``revision`` trusts no chunk that carries no digest, because the revision exists to
    replace data an older parser wrote.
    """
    stored = (entry or {}).get("schema_sha256")
    if not stored:
        return not spec.revision
    return bool(stored == spec_fingerprint(spec))


class _ClashIndex:
    """Which chunk owns each (season folder, lower-case file name) of one dataset.

    Every put used to copy the whole manifest and test every other chunk (40,000 entries by the
    last seasons of a game download, 13 times a game): time that grew with the lake. The index is
    extended with the keys that are new since the last call, so a check costs a set difference.
    """

    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        self._keys: frozenset[str] = frozenset()
        self._owner: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def lookup(self, current: frozenset[str], prefix: str, folded: str) -> str | None:
        """The chunk key that already owns ``folded`` inside ``prefix``, if any."""
        with self._lock:
            if self._keys - current:  # chunks were removed: start again
                self._owner.clear()
                added = current
            else:
                added = current - self._keys
            for key in added:
                folder, _, name = key.partition("/") if key.startswith("season=") else ("", "", key)
                if "/" in name:
                    continue
                season = int(folder.removeprefix("season=")) if folder else None
                owner_prefix = f"{folder}/" if folder else ""
                self._owner.setdefault(
                    (owner_prefix, part_filename(self.dataset, name, season).casefold()), key
                )
            self._keys = current
            return self._owner.get((prefix, folded))


_CLASH_INDEXES: dict[tuple[str, str], _ClashIndex] = {}
_CLASH_LOCK = threading.Lock()


def _clash_index(manifest_path: str, dataset: str) -> _ClashIndex:
    with _CLASH_LOCK:
        return _CLASH_INDEXES.setdefault((manifest_path, dataset), _ClashIndex(dataset))


def part_filename(dataset: str, chunk_id: str, season: int | None = None) -> str:
    """File name of a processed part: the chunk id without what its folders already say (ADR 63).

    The dataset name (``<dataset>_`` in front) and the season (``_<season>`` or ``<season>_``) are
    dropped, so ``processed/mlb_api/award_recipients/season=2024/`` holds ``part-AAACMVP.parquet``
    instead of ``part-award_recipients_2024_AAACMVP.parquet``; nothing left means ``part-data``.
    """
    name = _safe_chunk_id(chunk_id)
    if name == dataset:
        name = ""
    elif name.startswith(dataset + "_"):
        name = name[len(dataset) + 1 :]
    if season is not None:
        tokens = [t for t in name.split("_") if t != str(season)]
        name = "_".join(tokens)
    return f"part-{name or 'data'}.parquet"


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
        upstream: Fingerprint | None = None,
        records: int | None = None,
        extra: Mapping[str, Any] | None = None,
    ) -> Path:
        """Atomically write ``data`` and record size + sha256 in the dataset's raw manifest.

        ``upstream`` is the provider's fingerprint of this file version (see ``core/upstream.py``);
        without one, a given ``etag`` is recorded as an ETag fingerprint. ``records`` is the number
        of data rows in the file (omit when unknown) and ``extra`` adds source-specific fields to
        the same manifest entry, so there is exactly one entry per raw file.
        """
        if upstream is None and etag:
            upstream = Fingerprint(ETAG, etag)
        ensure_version_file(self.config)
        directory = self.config.raw_dir(source, dataset, season, create=True)
        path = directory / _safe_chunk_id(name)
        packed = source in self.config.raw_compress_sources and is_compressible(path.name)
        stored = gzip_bytes(data) if packed else data
        target = path.with_name(path.name + GZIP_SUFFIX) if packed else path
        with atomic_write(target) as part:
            part.write_bytes(stored)
        # a refresh may change the form: never leave both forms of one file behind
        (path if packed else path.with_name(path.name + GZIP_SUFFIX)).unlink(missing_ok=True)
        self.config.dataset_manifest(source, dataset, "raw", season).set_completed(
            name,
            records_count=records or 0,
            etag=etag,
            metadata={
                **(extra or {}),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                **({"stored": GZIP, "stored_bytes": len(stored)} if packed else {}),
                "season": season,
                "source_ref": source_ref,
                **({"upstream": upstream.to_dict()} if upstream is not None else {}),
            },
        )
        return path

    def stored_path(
        self, source: str, dataset: str, name: str, season: int | None = None
    ) -> Path | None:
        """The file that holds ``name`` (plain or gzipped), or ``None`` when it is not stored."""
        return stored_path(self.config.raw_dir(source, dataset, season), _safe_chunk_id(name))

    def exists(self, source: str, dataset: str, name: str, season: int | None = None) -> bool:
        """True when the raw file is stored, in either form."""
        return self.stored_path(source, dataset, name, season) is not None

    def get(self, source: str, dataset: str, name: str, season: int | None = None) -> bytes:
        """Read a raw file back as the original bytes (``FileNotFoundError`` if absent)."""
        path = self.stored_path(source, dataset, name, season)
        if path is None:
            raise FileNotFoundError(self.path_for(source, dataset, name, season))
        return read_logical(path, _safe_chunk_id(name))

    def verify(self, source: str, dataset: str, name: str, season: int | None = None) -> bool:
        """True when the file exists and its original bytes match the sha256 in the manifest."""
        path = self.stored_path(source, dataset, name, season)
        if path is None:
            return False
        manifest = self.config.dataset_manifest(source, dataset, "raw", season)
        entry = manifest.get_chunk(name)
        if not entry or "sha256" not in entry:
            return False
        return bool(logical_sha256(path, _safe_chunk_id(name)) == entry["sha256"])


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
        return self.dataset_dir(spec, season) / part_filename(spec.name, chunk_id, season)

    def _refuse_name_clash(self, spec: DatasetSpec, chunk_id: str, season: int | None) -> None:
        """Two different chunks must never share one file name (the second would overwrite the first)."""
        mine = part_filename(spec.name, chunk_id, season).casefold()  # case-insensitive disks too
        key = manifest_key(chunk_id, season)
        prefix = f"season={season}/" if season is not None else ""
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        other = _clash_index(str(manifest.path), spec.name).lookup(
            manifest.chunk_keys(), prefix, mine
        )
        if other is not None and other != key:
            name = other[len(prefix) :] if prefix else other
            raise ValueError(
                f"{spec.key}: chunks {chunk_id!r} and {name!r} would share the file {mine}"
            )

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
        self._refuse_name_clash(spec, chunk_id, season)
        ensure_version_file(self.config)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._release_compacted(spec, chunk_id, season)
        atomic_write_parquet(table, path, compression=PARQUET_COMPRESSION)
        self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(
            manifest_key(chunk_id, season),
            records_count=table.num_rows,
            metadata={
                "season": season,
                "source_ref": source_ref,
                "schema_sha256": spec_fingerprint(spec),
                **(metadata or {}),
            },
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
        self._refuse_name_clash(spec, chunk_id, season)
        ensure_version_file(self.config)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._release_compacted(spec, chunk_id, season)
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
                                part,
                                spec.schema,
                                compression=PARQUET_COMPRESSION,
                                store_decimal_as_integer=True,
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
            # a rebuild that now has no rows must not leave the old rows behind
            path.unlink(missing_ok=True)
            # remember that this chunk legitimately has no rows so it is not re-parsed every run
            self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(
                manifest_key(chunk_id, season),
                records_count=0,
                metadata={
                    "season": season,
                    "source_ref": source_ref,
                    "schema_sha256": spec_fingerprint(spec),
                    **(metadata or {}),
                },
            )
            return 0
        self.config.dataset_manifest(spec.source, spec.name, "processed").set_completed(
            manifest_key(chunk_id, season),
            records_count=total,
            metadata={
                "season": season,
                "source_ref": source_ref,
                "schema_sha256": spec_fingerprint(spec),
                **(metadata or {}),
            },
        )
        return total

    def is_cached(
        self, spec: DatasetSpec, chunk_id: str = "data", season: int | None = None
    ) -> bool:
        """True when the manifest recorded the chunk COMPLETED and its part (if any rows) exists."""
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        entry = manifest.get_chunk(manifest_key(chunk_id, season))
        if entry is None or entry.get("status") != "COMPLETED" or not schema_matches(spec, entry):
            return False
        if self.has_part(spec, chunk_id, season):
            return True
        return entry.get("records_count") == 0

    def _dataset_root(self, spec: DatasetSpec) -> Path:
        return self.config.processed_dir(spec.source, spec.name)

    def has_part(
        self, spec: DatasetSpec, chunk_id: str = "data", season: int | None = None
    ) -> bool:
        """True when the chunk is stored: a part file, a compacted file, or recorded as empty."""
        if self.part_path(spec, chunk_id, season).exists():
            return True
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        key = manifest_key(chunk_id, season)
        entry = manifest.get_chunk(key)
        if entry and entry.get("status") == "COMPLETED" and entry.get("records_count") == 0:
            return True  # downloaded and empty: no file is needed
        return holds_chunk(self._dataset_root(spec), entry, key)

    def find_chunk_season(self, spec: DatasetSpec, chunk_id: str) -> int | None:
        """Season folder that stores ``chunk_id`` (as a part file or inside a compacted file)."""
        root = self._dataset_root(spec)
        if not root.exists():
            return None
        wanted = part_filename(spec.name, chunk_id)
        for match in root.glob(f"season=*/{wanted}"):
            return int(match.parent.name.removeprefix("season="))
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        suffix = f"/{chunk_id}"
        for key, entry in manifest.chunks().items():
            if key.startswith("season=") and key.endswith(suffix):
                season = int(key.split("/", 1)[0].removeprefix("season="))
                if holds_chunk(root, entry, key):
                    return season
        return None

    def _release_compacted(self, spec: DatasetSpec, chunk_id: str, season: int | None) -> None:
        """Before a chunk is rewritten, take its old rows out of the compacted file that holds them."""
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        key = manifest_key(chunk_id, season)
        entry = manifest.get_chunk(key)
        if not entry or not entry.get(INTO):
            return
        release_chunk(self._dataset_root(spec), entry, key, spec.schema)
        manifest.put_entry(key, {k: v for k, v in entry.items() if k != INTO})

    def read_part(
        self, spec: DatasetSpec, chunk_id: str = "data", season: int | None = None
    ) -> pa.Table:
        """Read one stored part back (an empty table for a chunk recorded with zero rows)."""
        path = self.part_path(spec, chunk_id, season)
        if path.exists():
            return pq.read_table(path)
        manifest = self.config.dataset_manifest(spec.source, spec.name, "processed")
        key = manifest_key(chunk_id, season)
        entry = manifest.get_chunk(key)
        if entry and holds_chunk(self._dataset_root(spec), entry, key):
            return read_chunk(self._dataset_root(spec), entry, key)
        return spec.schema.empty_table()

    def files(self, spec: DatasetSpec) -> list[Path]:
        """Every parquet part currently stored for ``spec``."""
        return dataset_files(self.dataset_dir(spec), by_season=spec.partition == "season")

    def read(
        self, spec: DatasetSpec, season: int | None = None, columns: list[str] | None = None
    ) -> pa.Table:
        """Concatenate the stored parts (optionally one season, optionally some columns) into one table."""
        parts = self._parts(spec, season)
        if not parts:
            schema = (
                spec.schema
                if columns is None
                else pa.schema([spec.schema.field(c) for c in columns])
            )
            return schema.empty_table()
        return pa.concat_tables(
            [pq.read_table(p, columns=columns) for p in parts], promote_options="permissive"
        )

    def row_count(self, spec: DatasetSpec, season: int | None = None) -> int:
        """Total rows across all parts (of one season if given), read from parquet footers."""
        return sum(pq.ParquetFile(p).metadata.num_rows for p in self._parts(spec, season))

    def _parts(self, spec: DatasetSpec, season: int | None) -> list[Path]:
        """The data files of one season, or of every season of a split dataset (hidden files left out)."""
        by_season = spec.partition == "season" and season is None
        return dataset_files(self.dataset_dir(spec, season), by_season=by_season)


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
