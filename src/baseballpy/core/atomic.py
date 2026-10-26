"""Two-phase atomic file writes and checkpoint manifest tracking."""

import json
import os
from collections.abc import Generator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pyarrow as pa
import pyarrow.parquet as pq


@contextmanager
def atomic_write(target_path: Path | str, mode: str = "wb") -> Generator[Path, None, None]:
    """Context manager for two-phase atomic file writing.

    Writes to a temporary `.part` file and atomically renames to target_path on clean exit.
    Cleans up the `.part` file if an exception occurs.
    """
    path = Path(target_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part_path = path.with_suffix(f"{path.suffix}.part")

    try:
        yield part_path
        if part_path.exists():
            # Atomically replace final file
            os.replace(part_path, path)
    except Exception:
        if part_path.exists():
            with suppress(OSError):
                part_path.unlink()
        raise


def atomic_write_parquet(
    table: pa.Table, target_path: Path | str, compression: str = "snappy"
) -> None:
    """Atomically write a PyArrow Table to a Parquet file."""
    path = Path(target_path)
    with atomic_write(path) as part_path:
        pq.write_table(table, part_path, compression=compression)


class ManifestTracker:
    """Thread-safe checkpoint manifest tracking completed download and ingestion chunks."""

    def __init__(self, manifest_path: Path | str) -> None:
        self.path = Path(manifest_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Load manifest data from disk if it exists."""
        if not self.path.exists():
            return {"chunks": {}, "updated_at": datetime.now(UTC).isoformat()}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return cast(dict[str, Any], loaded)
            return {"chunks": {}, "updated_at": datetime.now(UTC).isoformat()}
        except Exception:
            return {"chunks": {}, "updated_at": datetime.now(UTC).isoformat()}

    def is_completed(self, chunk_id: str) -> bool:
        """Check if a chunk is recorded as completed."""
        chunk = self._data.get("chunks", {}).get(chunk_id)
        return bool(chunk and chunk.get("status") == "COMPLETED")

    def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        """Get chunk metadata."""
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
        """Mark a chunk as completed and persist manifest atomically."""
        if "chunks" not in self._data:
            self._data["chunks"] = {}

        self._data["chunks"][chunk_id] = {
            "status": "COMPLETED",
            "records_count": records_count,
            "etag": etag,
            "completed_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }
        self.save()

    def set_failed(self, chunk_id: str, error: str) -> None:
        """Mark a chunk as failed."""
        if "chunks" not in self._data:
            self._data["chunks"] = {}

        self._data["chunks"][chunk_id] = {
            "status": "FAILED",
            "error": error,
            "failed_at": datetime.now(UTC).isoformat(),
        }
        self.save()

    def save(self) -> None:
        """Atomically persist manifest JSON."""
        self._data["updated_at"] = datetime.now(UTC).isoformat()
        payload = json.dumps(self._data, indent=2)
        with atomic_write(self.path) as part_path:
            part_path.write_text(payload, encoding="utf-8")
