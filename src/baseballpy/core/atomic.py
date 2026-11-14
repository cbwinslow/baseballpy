"""Two-phase atomic file writes and lock-protected checkpoint manifest tracking."""

import json
import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Generator, Mapping
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

from baseballpy.core.hostlock import release_file_lock, wait_file_lock

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 30.0


def _part_path_for(path: Path) -> Path:
    """Return a unique temporary sibling path so concurrent writers never collide."""
    return path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.part")


def _fsync_path(path: Path) -> None:
    """Flush file contents to stable storage when the platform allows it."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        with suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def _replace_with_retry(src: Path, dst: Path, attempts: int = 50) -> None:
    """``os.replace`` that tolerates transient Windows sharing violations (readers mid-open)."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.02)


@contextmanager
def atomic_write(target_path: Path | str, mode: str = "wb") -> Generator[Path, None, None]:
    """Context manager for two-phase atomic file writing.

    Yields a unique temporary ``.part`` path next to the target. On clean exit the
    part file is fsynced and atomically renamed over the target; on any exception
    the part file is removed and the exception is re-raised.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part_path = _part_path_for(path)

    try:
        yield part_path
        if part_path.exists():
            _fsync_path(part_path)
            _replace_with_retry(part_path, path)
    except BaseException:
        if part_path.exists():
            with suppress(OSError):
                part_path.unlink()
        raise


def cleanup_stale_parts(directory: Path | str, older_than_seconds: float = 3600.0) -> list[Path]:
    """Remove orphaned ``*.part`` files older than the threshold and return them."""
    root = Path(directory)
    removed: list[Path] = []
    if not root.exists():
        return removed
    cutoff = time.time() - older_than_seconds
    for part in root.rglob("*.part"):
        try:
            if part.stat().st_mtime < cutoff:
                part.unlink()
                removed.append(part)
        except OSError:
            logger.warning("could not remove stale part file %s", part)
    return removed


_SWEPT: set[Path] = set()
_SWEPT_LOCK = threading.Lock()


def forget_swept_folders() -> None:
    """Forget which folders were swept (a new process starts with none; tests simulate a restart)."""
    with _SWEPT_LOCK:
        _SWEPT.clear()


def cleanup_stale_parts_once(directory: Path | str) -> list[Path]:
    """Sweep ``directory`` for stale ``*.part`` files at most once per process.

    Every extractor used to walk its whole source folder when it was built, and one run builds one
    per job: with 400,000 files that was minutes per job, all at the same time, before the first
    request. Leftover parts are only hygiene, so the first caller sweeps and the rest skip it.
    """
    root = Path(directory)
    with _SWEPT_LOCK:
        if root in _SWEPT:
            return []
        _SWEPT.add(root)
    return cleanup_stale_parts(root)


def atomic_write_parquet(
    table: pa.Table, target_path: Path | str, compression: str = "snappy"
) -> None:
    """Atomically write a PyArrow Table to a Parquet file after validating its footer."""
    path = Path(target_path)
    with atomic_write(path) as part_path:
        pq.write_table(table, part_path, compression=compression, store_decimal_as_integer=True)
        footer = pq.ParquetFile(part_path).metadata  # raises if the footer is corrupt
        if footer.num_rows != table.num_rows:
            raise ValueError(
                f"parquet footer row count {footer.num_rows} != table rows {table.num_rows}"
            )


class _FileLock:
    """Cross-process lock of a manifest: an operating-system file lock that waits its turn.

    The OS frees the lock when its holder ends, however it ends, so there is no stale lock to break
    (the old lock file was broken after 60 s, which let two processes save at once, ADR 131). The
    lock file ``<manifest>.lock`` stays on disk after a save; a lock file left by the old scheme is
    just a file the OS lock can be taken on.
    """

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self.path = path
        self.timeout = timeout
        self._fd: int | None = None

    def __enter__(self) -> "_FileLock":
        try:
            self._fd = wait_file_lock(self.path, self.timeout)
        except TimeoutError:
            raise TimeoutError(f"could not acquire manifest lock {self.path}") from None
        return self

    def __exit__(self, *exc: object) -> None:
        fd, self._fd = self._fd, None
        if fd is not None:
            release_file_lock(fd)


def _empty_manifest() -> dict[str, Any]:
    return {"chunks": {}, "updated_at": datetime.now(UTC).isoformat()}


def _entry_time(entry: dict[str, Any]) -> str:
    return str(entry.get("completed_at") or entry.get("failed_at") or "")


#: manifests kept parsed in memory at once (see ``ManifestTracker.for_path``)
MAX_SHARED_TRACKERS = 48
_TRACKERS: "OrderedDict[str, ManifestTracker]" = OrderedDict()
_TRACKERS_LOCK = threading.Lock()


class ManifestTracker:
    """Thread- and process-safe checkpoint manifest tracking download/ingestion chunks.

    Every save re-reads the file under a lock and merges chunk entries (the entry with
    the later timestamp wins), so concurrent writers never drop each other's chunks.
    Corrupt manifests are preserved as ``manifest.json.corrupt-<ts>`` and logged.
    """

    def __init__(self, manifest_path: Path | str) -> None:
        self.path = Path(manifest_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rlock = threading.RLock()
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        # (mtime_ns, size) of the file that ``_data`` mirrors; a matching stat means no re-parse
        self._sig: tuple[int, int] | None = None
        self._data: dict[str, Any] = self._load()
        # saves held back while ``deferred`` is active: chunk id -> entry not yet on disk
        self._defer = 0
        self._defer_every = 1
        self._pending: dict[str, dict[str, Any]] = {}

    @classmethod
    def for_path(cls, manifest_path: Path | str) -> "ManifestTracker":
        """The shared tracker of a manifest file (a few are kept, least recently used dropped).

        Building a tracker parses the whole file; a per-team dataset has a 4.5 MB manifest and
        every chunk lookup used to build a new one. Trackers refresh themselves when the file
        changes, so sharing one is safe across threads.
        """
        key = os.path.normcase(os.path.abspath(manifest_path))
        with _TRACKERS_LOCK:
            tracker = _TRACKERS.get(key)
            if tracker is not None:
                _TRACKERS.move_to_end(key)
                return tracker
        tracker = cls(manifest_path)
        with _TRACKERS_LOCK:
            tracker = _TRACKERS.setdefault(key, tracker)
            _TRACKERS.move_to_end(key)
            while len(_TRACKERS) > MAX_SHARED_TRACKERS:
                _TRACKERS.popitem(last=False)
        return tracker

    def _stat_sig(self) -> tuple[int, int] | None:
        try:
            st = self.path.stat()
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def _read_disk(self) -> dict[str, Any] | None:
        """Read the manifest from disk, preserving corrupt files; None if absent."""
        data = b""
        for attempt in range(50):
            try:
                data = self.path.read_bytes()
            except FileNotFoundError:
                return None
            except PermissionError:
                # transient sharing violation while another writer replaces the file
                if attempt == 49:
                    raise
                time.sleep(0.02)
                continue
            break
        try:
            loaded = json.loads(data)
        except ValueError as exc:  # bad JSON or bad UTF-8
            self._preserve_corrupt(f"{type(exc).__name__}: {exc}")
            return None
        if not isinstance(loaded, dict) or not isinstance(loaded.get("chunks", {}), dict):
            self._preserve_corrupt("manifest root is not an object with a chunks mapping")
            return None
        loaded.setdefault("chunks", {})
        return cast(dict[str, Any], loaded)

    def _preserve_corrupt(self, reason: str) -> None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        backup = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
        logger.error("manifest %s is corrupt (%s); preserving as %s", self.path, reason, backup)
        with suppress(OSError):
            os.replace(self.path, backup)

    def _load(self) -> dict[str, Any]:
        with self._rlock:
            sig = self._stat_sig()
            data = self._read_disk() or _empty_manifest()
            self._sig = sig
            return data

    def reload(self) -> None:
        """Refresh the in-memory view from disk (picks up other writers' chunks).

        A manifest of a per-team dataset is several MB; it is parsed again only when its
        size or modification time changed (a 9-season MLB run re-parsed it for every chunk
        lookup, took hours and ran out of memory).
        """
        with self._rlock:
            sig = self._stat_sig()
            if sig is not None and sig == self._sig:
                return
            self._data = self._load()
            if self._pending:  # entries not yet saved are newer than the file
                self._data.setdefault("chunks", {}).update(self._pending)

    def is_completed(self, chunk_id: str) -> bool:
        """Check if a chunk is recorded as completed."""
        chunk = self.get_chunk(chunk_id)
        return bool(chunk and chunk.get("status") == "COMPLETED")

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get chunk metadata (re-reading disk so other processes' work is visible)."""
        with self._rlock:
            self.reload()
            chunk = self._data.get("chunks", {}).get(chunk_id)
            if isinstance(chunk, dict):
                return cast(dict[str, Any], chunk)
            return None

    def set_completed(
        self,
        chunk_id: str,
        records_count: int = 0,
        etag: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mark a chunk as completed and persist the manifest atomically."""
        entry: dict[str, Any] = {
            "status": "COMPLETED",
            "records_count": records_count,
            "etag": etag,
            "completed_at": datetime.now(UTC).isoformat(),
            "fetched_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }
        self._set(chunk_id, entry)

    def set_failed(self, chunk_id: str, error: str) -> None:
        """Mark a chunk as failed."""
        self._set(
            chunk_id,
            {"status": "FAILED", "error": error, "failed_at": datetime.now(UTC).isoformat()},
        )

    def set_absent(self, chunk_id: str, reason: str = "absent upstream") -> None:
        """Record that the upstream does not provide this chunk (never COMPLETED)."""
        self._set(
            chunk_id,
            {"status": "ABSENT", "reason": reason, "failed_at": datetime.now(UTC).isoformat()},
        )

    def put_entry(self, chunk_id: str, entry: dict[str, Any]) -> None:
        """Store ``entry`` verbatim (keeps timestamps/status); used when migrating manifests."""
        self._set(chunk_id, dict(entry))

    def put_entries(self, entries: Mapping[str, dict[str, Any]]) -> None:
        """Store many entries verbatim with one save (``put_entry`` in a loop saves every time)."""
        with self._rlock:
            self._data.setdefault("chunks", {}).update({k: dict(v) for k, v in entries.items()})
            self.save(_only=frozenset(entries))

    def chunk_keys(self) -> frozenset[str]:
        """The ids of every chunk on disk, without copying their entries."""
        with self._rlock:
            self.reload()
            return frozenset(self._data.get("chunks", {}))

    def chunks(self) -> dict[str, dict[str, Any]]:
        """Snapshot of every chunk entry currently on disk."""
        with self._rlock:
            self.reload()
            return {
                k: dict(v) for k, v in self._data.get("chunks", {}).items() if isinstance(v, dict)
            }

    def _set(self, chunk_id: str, entry: dict[str, Any]) -> None:
        with self._rlock:
            self._data.setdefault("chunks", {})[chunk_id] = entry
            if self._defer:
                self._pending[chunk_id] = entry
                if len(self._pending) >= self._defer_every:
                    self.flush()
                return
            self.save(_only=chunk_id)

    @contextmanager
    def deferred(self, every: int = 500) -> Generator[None, None, None]:
        """Hold back saves while a bulk run records many chunks; save every ``every`` entries.

        Every save rewrites the whole manifest, so recording one chunk at a time costs time
        proportional to the manifest's size each (0.13 s at 29,000 entries, 13 per game). Entries
        are visible to this process at once; other processes see them after each flush and at the
        end. A crash loses at most ``every`` entries, whose chunks are simply fetched again.
        """
        with self._rlock:
            self._defer += 1
            self._defer_every = min(self._defer_every, every) if self._defer > 1 else every
        try:
            yield
        finally:
            with self._rlock:
                self._defer -= 1
                if self._defer == 0:
                    self.flush()

    def flush(self) -> None:
        """Save the entries held back by ``deferred``."""
        with self._rlock:
            if self._pending:
                self.save(_only=frozenset(self._pending))
                self._pending.clear()

    def save(self, _only: str | frozenset[str] | None = None) -> None:
        """Merge with on-disk state under a file lock and atomically persist."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._rlock, _FileLock(self._lock_path):
            if self._sig is not None and self._sig == self._stat_sig():
                disk = {**self._data}  # file unchanged since our last read or write
            else:
                disk = self._read_disk() or _empty_manifest()
            forced = {_only} if isinstance(_only, str) else set(_only or ())
            merged: dict[str, Any] = dict(disk.get("chunks", {}))
            for key, entry in self._data.get("chunks", {}).items():
                existing = merged.get(key)
                if key in forced or existing is None or _entry_time(entry) > _entry_time(existing):
                    merged[key] = entry
            disk["chunks"] = merged
            disk["updated_at"] = datetime.now(UTC).isoformat()
            # stdlib json, not msgspec: msgspec.json.encode crashed the process with a Windows access
            # violation in this call (atomic.py save, three season runs, ADR 88 as amended); compact
            # separators keep the file small, and saves are deferred in bulk runs (ADR 93)
            with atomic_write(self.path) as part_path:
                part_path.write_bytes(json.dumps(disk, separators=(",", ":")).encode("utf-8"))
            self._data = disk
            self._sig = self._stat_sig()


__all__ = [
    "ManifestTracker",
    "atomic_write",
    "atomic_write_parquet",
    "cleanup_stale_parts",
    "cleanup_stale_parts_once",
    "forget_swept_folders",
]
