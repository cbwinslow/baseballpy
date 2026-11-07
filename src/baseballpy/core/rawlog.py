"""Raw answers of a unit of work, kept as one gzip of JSON lines (never a file per request).

Used by the market sources: a unit (a series, a close date, an open date) makes dozens of requests,
and a file per request would be hundreds of thousands of tiny files. The body of every answer is
kept verbatim, so a parsing fix never needs the network.
"""

import gzip
import json
import threading

from baseballpy.core.stores import RawStore


class RawLog:
    """Raw answers of one unit, written as a gzip of JSON lines (the body kept verbatim)."""

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


def keep_raw(
    store: RawStore, source: str, dataset: str, name: str, log: RawLog, **extra: str | int
) -> None:
    """Write ``log`` as ``raw/<source>/<dataset>/<name>`` with its sha256 in the manifest."""
    store.put(source, dataset, name, log.to_bytes(), records=len(log), extra=dict(extra))


__all__ = ["RawLog", "keep_raw"]
