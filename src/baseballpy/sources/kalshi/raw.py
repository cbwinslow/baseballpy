"""Raw Kalshi answers kept as one gzip of JSON lines per dataset and unit (never a file per request)."""

import gzip
import json
import threading

from baseballpy.core.stores import RawStore


class RawLog:
    """Raw answers of one close date, written as a gzip of JSON lines (the body kept verbatim)."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def add(self, route: str, ticker: str, page: int, body: bytes) -> None:
        """Remember one answer; ``body`` is the exact response text (safe from several threads)."""
        record = {"route": route, "ticker": ticker, "page": page, "body": body.decode("utf-8")}
        line = json.dumps(record, separators=(",", ":"))
        with self._lock:
            self._lines.append(line)

    def __len__(self) -> int:
        return len(self._lines)

    def to_bytes(self) -> bytes:
        """The whole log as gzip bytes (``mtime`` fixed, so equal logs have equal bytes)."""
        with self._lock:
            lines = sorted(self._lines)  # threads add in any order; the file must not depend on it
        return gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0)


def keep_raw(store: RawStore, dataset: str, name: str, log: RawLog, **extra: str | int) -> None:
    """Write ``log`` as ``raw/kalshi/<dataset>/<name>`` with its sha256 in the manifest."""
    store.put("kalshi", dataset, name, log.to_bytes(), records=len(log), extra=dict(extra))


__all__ = ["RawLog", "keep_raw"]
