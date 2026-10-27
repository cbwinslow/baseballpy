"""Two-phase atomic file writes and lock-protected checkpoint manifest tracking."""

import json
import logging
import os
import threading
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

LOCK_TIMEOUT_SECONDS = 10.0
LOCK_STALE_SECONDS = 60.0


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


def atomic_write_parquet(
    table: pa.Table, target_path: Path | str, compression: str = "snappy"
) -> None:
    """Atomically write a PyArrow Table to a Parquet file after validating its footer."""
    path = Path(target_path)
    with atomic_write(path) as part_path:
        pq.write_table(table, part_path, compression=compression)
        footer = pq.ParquetFile(part_path).metadata  # raises if the footer is corrupt
        if footer.num_rows != table.num_rows:
            raise ValueError(
                f"parquet footer row count {footer.num_rows} != table rows {table.num_rows}"
            )


class _FileLock:
    """Advisory cross-process lock implemented with an exclusive lock file."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT_SECONDS) -> None:
        self.path = path
        self.timeout = timeout

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except (FileExistsError, PermissionError):
                # PermissionError: Windows reports a lock file pending deletion this way.
                self._break_if_stale()
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"could not acquire manifest lock {self.path}") from None
                time.sleep(0.02)
                continue
            with os.fdopen(fd, "w") as handle:
                handle.write(str(os.getpid()))
            return self

    def _break_if_stale(self) -> None:
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return
        if age > LOCK_STALE_SECONDS:
            logger.warning("breaking stale manifest lock %s (age %.0fs)", self.path, age)
            with suppress(OSError):
                self.path.unlink()

    def __exit__(self, *exc: object) -> None:
        with suppress(OSError):
            self.path.unlink()


def _empty_manifest() -> dict[str, Any]:
    return {"chunks": {}, "updated_at": datetime.now(UTC).isoformat()}


def _entry_time(entry: dict[str, Any]) -> str:
    return str(entry.get("completed_at") or entry.get("failed_at") or "")


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
        self._data: dict[str, Any] = self._load()

    def _read_disk(self) -> dict[str, Any] | None:
        """Read the manifest from disk, preserving corrupt files; None if absent."""
        text: str | None = None
        for attempt in range(50):
            try:
                text = self.path.read_text(encoding="utf-8")
                break
            except FileNotFoundError:
                return None
            except PermissionError:
                # transient sharing violation while another writer replaces the file
                if attempt == 49:
                    raise
                time.sleep(0.02)
            except UnicodeDecodeError as exc:
                self._preserve_corrupt(f"{type(exc).__name__}: {exc}")
                return None
        try:
            loaded = json.loads(text or "")
        except json.JSONDecodeError as exc:
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
            return self._read_disk() or _empty_manifest()

    def reload(self) -> None:
        """Refresh the in-memory view from disk (picks up other writers' chunks)."""
        with self._rlock:
            self._data = self._load()

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

    def _set(self, chunk_id: str, entry: dict[str, Any]) -> None:
        with self._rlock:
            self._data.setdefault("chunks", {})[chunk_id] = entry
            self.save(_only=chunk_id)

    def save(self, _only: str | None = None) -> None:
        """Merge with on-disk state under a file lock and atomically persist."""
        with self._rlock, _FileLock(self._lock_path):
            disk = self._read_disk() or _empty_manifest()
            merged: dict[str, Any] = dict(disk.get("chunks", {}))
            for key, entry in self._data.get("chunks", {}).items():
                existing = merged.get(key)
                if key == _only or existing is None or _entry_time(entry) > _entry_time(existing):
                    merged[key] = entry
            disk["chunks"] = merged
            disk["updated_at"] = datetime.now(UTC).isoformat()
            payload = json.dumps(disk, indent=2)
            with atomic_write(self.path) as part_path:
                part_path.write_text(payload, encoding="utf-8")
            self._data = disk


__all__ = [
    "ManifestTracker",
    "atomic_write",
    "atomic_write_parquet",
    "cleanup_stale_parts",
]
