"""Dead-letter quarantine for payloads and rows that fail schema coercion."""

import base64
import json
import logging
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from baseballpy.core.config import QuarantineConfig
from baseballpy.core.lazy import lazy_singleton

logger = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    """Make an arbitrary payload JSON-serializable (bytes become base64 strings)."""
    if isinstance(value, bytes | bytearray):
        return {"__base64__": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return repr(value)


class Quarantine:
    """Persists unparseable records as JSONL dead letters and logs a structured warning."""

    def __init__(self, config: QuarantineConfig | None = None) -> None:
        self.config = config or QuarantineConfig()

    def write(
        self,
        source: str,
        dataset: str,
        records: Iterable[Any],
        reason: str,
        context: dict[str, Any] | None = None,
    ) -> Path | None:
        """Write dead letters; returns the file path (None if disabled or nothing to write)."""
        items = list(records)
        if not items or not self.config.enabled:
            return None
        now = datetime.now(UTC)
        directory = self.config.quarantine_dir / source / now.strftime("%Y-%m-%d")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{dataset}-{uuid.uuid4().hex[:8]}.jsonl"
        with open(path, "w", encoding="utf-8") as handle:
            for item in items:
                line = {
                    "ts": now.isoformat(),
                    "source": source,
                    "dataset": dataset,
                    "reason": reason,
                    "context": _jsonable(context or {}),
                    "payload": _jsonable(item),
                }
                handle.write(json.dumps(line) + "\n")
        logger.warning(
            "quarantined %d record(s) from %s/%s: %s -> %s", len(items), source, dataset, reason, path
        )
        # Local import: audit depends on config only; avoids any import cycle with sinks.
        from baseballpy.core.audit import get_audit_logger

        with get_audit_logger().track(
            operation="quarantine_write", source=source, destination=str(path)
        ) as tracker:
            tracker.set_records(len(items))
        return path


get_quarantine = lazy_singleton(Quarantine)


def checked_cast(
    array: pa.Array | pa.ChunkedArray,
    target: pa.DataType,
    *,
    quarantine: Quarantine | None,
    source: str,
    dataset: str,
    column: str,
) -> pa.ChunkedArray:
    """Safely cast ``array`` to ``target``; failing cells become NULL and are quarantined.

    Never uses ``safe=False``: lossy conversions (truncation, overflow) are treated as
    failures for the offending value only, not for the whole column.
    """
    chunked = array if isinstance(array, pa.ChunkedArray) else pa.chunked_array([array])
    try:
        return pc.cast(chunked, target, safe=True)  # type: ignore[no-any-return]
    except (pa.ArrowInvalid, pa.ArrowNotImplementedError, pa.ArrowTypeError):
        pass

    values = chunked.to_pylist()
    out: list[Any] = []
    bad: list[dict[str, Any]] = []
    for idx, value in enumerate(values):
        if value is None:
            out.append(None)
            continue
        try:
            scalar = pa.array([value]).cast(target, safe=True)
            out.append(scalar[0].as_py())
        except (pa.ArrowInvalid, pa.ArrowNotImplementedError, pa.ArrowTypeError):
            out.append(None)
            bad.append({"column": column, "row": idx, "value": value})
    if bad:
        (quarantine or get_quarantine()).write(
            source, dataset, bad, f"uncastable values in column {column!r} to {target}"
        )
    return pa.chunked_array([pa.array(out, type=target)])
