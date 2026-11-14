"""Structured audit logging, execution benchmarking, and telemetry engine."""

import asyncio
import gzip
import logging
import shutil
import threading
import time
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import msgspec

from baseballpy.core.config import AuditConfig
from baseballpy.core.lazy import lazy_singleton

logger = logging.getLogger(__name__)

STATUS_SUCCESS = "SUCCESS"
STATUS_FAILURE = "FAILURE"
STATUS_CANCELLED = "CANCELLED"


class AuditEvent(msgspec.Struct, kw_only=True):
    """Structured audit log entry persisted to JSON Lines."""

    timestamp_utc: str
    started_at_utc: str = ""
    completed_at_utc: str = ""
    operation: str
    source: str
    status: str  # "SUCCESS", "FAILURE", "CANCELLED", "RETRY"
    records_count: int = 0
    duration_seconds: float = 0.0
    download_seconds: float | None = None
    processing_seconds: float | None = None
    throughput_rps: float = 0.0
    cache_hit: bool = False
    endpoint: str = ""
    destination: str = ""
    error: str | None = None


class ExecutionTracker:
    """Mutable tracker passed to context manager blocks."""

    def __init__(
        self, operation: str, source: str, endpoint: str = "", destination: str = ""
    ) -> None:
        self.operation = operation
        self.source = source
        self.endpoint = endpoint
        self.destination = destination
        self.records_count: int = 0
        self.cache_hit: bool = False
        self.download_seconds: float | None = None
        self.processing_seconds: float | None = None
        self.error: str | None = None
        self._start_perf: float = time.perf_counter()

    def set_records(self, count: int) -> None:
        """Set the number of records returned or processed."""
        self.records_count = count

    def set_cache_hit(self, hit: bool) -> None:
        """Set whether the data was loaded from cache."""
        self.cache_hit = hit

    def set_endpoint(self, endpoint: str) -> None:
        """Set or update the endpoint URL or identifier."""
        self.endpoint = endpoint

    def set_destination(self, destination: str) -> None:
        """Set or update the target destination path."""
        self.destination = destination

    def mark_download_complete(self) -> None:
        """Record the elapsed time up to now as download time."""
        now = time.perf_counter()
        self.download_seconds = round(now - self._start_perf, 4)

    def set_timing(
        self,
        download_seconds: float | None = None,
        processing_seconds: float | None = None,
    ) -> None:
        """Manually record discrete download vs processing durations."""
        if download_seconds is not None:
            self.download_seconds = round(download_seconds, 4)
        if processing_seconds is not None:
            self.processing_seconds = round(processing_seconds, 4)


class _Run:
    """Shared bookkeeping for ``track`` and ``async_track`` (single implementation)."""

    def __init__(self, tracker: ExecutionTracker) -> None:
        self.tracker = tracker
        self.started_utc = datetime.now(UTC).isoformat()
        self.start_perf = time.perf_counter()
        self.status = STATUS_SUCCESS
        self.error_msg: str | None = None

    def record_exception(self, exc: BaseException) -> None:
        """Map an exception to an audit status (cancellation is never SUCCESS)."""
        if isinstance(exc, asyncio.CancelledError | KeyboardInterrupt | GeneratorExit):
            self.status = STATUS_CANCELLED
        else:
            self.status = STATUS_FAILURE
        self.error_msg = f"{type(exc).__name__}: {exc}"
        self.tracker.error = self.error_msg

    def build_event(self) -> AuditEvent:
        """Finalize timings and build the event to persist."""
        tracker = self.tracker
        if self.status == STATUS_SUCCESS and tracker.error:
            # the caller recorded an error and returned instead of raising (a job that was not run because
            # its prerequisite failed): the audit log must not call it a success
            self.status = STATUS_FAILURE
            self.error_msg = tracker.error
        duration = time.perf_counter() - self.start_perf
        completed_utc = datetime.now(UTC).isoformat()
        if tracker.download_seconds is not None and tracker.processing_seconds is None:
            tracker.processing_seconds = max(0.0, round(duration - tracker.download_seconds, 4))
        throughput = (
            float(tracker.records_count) / duration
            if duration > 0 and tracker.records_count > 0
            else 0.0
        )
        return AuditEvent(
            timestamp_utc=completed_utc,
            started_at_utc=self.started_utc,
            completed_at_utc=completed_utc,
            operation=tracker.operation,
            source=tracker.source,
            status=self.status,
            records_count=tracker.records_count,
            duration_seconds=round(duration, 4),
            download_seconds=tracker.download_seconds,
            processing_seconds=tracker.processing_seconds,
            throughput_rps=round(throughput, 1),
            cache_hit=tracker.cache_hit,
            endpoint=tracker.endpoint,
            destination=tracker.destination,
            error=self.error_msg,
        )


class AuditLogger:
    """Thread-safe, async-safe, append-only structured audit logger for pipeline operations."""

    def __init__(self, config: AuditConfig | None = None) -> None:
        self.config = config or AuditConfig()
        self._encoder = msgspec.json.Encoder()
        self._decoder = msgspec.json.Decoder(AuditEvent)
        self._lock = threading.Lock()

    @property
    def log_path(self) -> Path:
        """Return the path to the audit.jsonl log file."""
        return self.config.audit_file

    def log(self, event: AuditEvent) -> None:
        """Atomically append an audit event to the JSONL log file under thread lock."""
        if not self.config.enabled:
            return
        line = self._encoder.encode(event) + b"\n"
        with self._lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "ab") as f:
                f.write(line)
            if self.config.auto_rotate:
                try:
                    if self.log_path.stat().st_size >= self.config.max_bytes:
                        self._rotate_unlocked(self.config.max_bytes, force=False)
                except OSError:
                    pass

    def _log_or_warn(self, event: AuditEvent) -> None:
        """Write the event; a failed write (a full disk, a locked file, an unencodable message) is a warning,
        never the error that ends the operation: it would hide the real failure that is being propagated."""
        try:
            self.log(event)
        except (
            OSError,
            ValueError,
            TypeError,
            msgspec.MsgspecError,
        ) as exc:  # writing a record never ends the operation
            logger.warning("could not write the audit record of %s: %s", event.operation, exc)

    def _rotate_unlocked(self, threshold: int, force: bool) -> Path | None:
        """Rotate audit.jsonl into audit-YYYY-MM-DD[-N].jsonl.gz (must hold _lock)."""
        if not self.log_path.exists():
            return None
        size = self.log_path.stat().st_size
        if not force and size < threshold:
            return None

        dest_dir = self.log_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        candidate = dest_dir / f"audit-{date_str}.jsonl.gz"
        idx = 1
        while candidate.exists():
            candidate = dest_dir / f"audit-{date_str}-{idx}.jsonl.gz"
            idx += 1

        rot_tmp = self.log_path.with_name(f"{self.log_path.name}.rot")
        try:
            self.log_path.replace(rot_tmp)
        except OSError:
            return None

        # Re-create empty active file immediately so concurrent writers can proceed
        self.log_path.touch()

        part_path = candidate.with_name(f"{candidate.name}.part")
        try:
            with open(rot_tmp, "rb") as f_in, gzip.open(part_path, "wb", compresslevel=6) as f_out:
                shutil.copyfileobj(f_in, f_out)
            part_path.replace(candidate)
        except BaseException:
            # the compressed copy is not complete (a full disk, an interrupt): put the records back in front of
            # what was written since, so the log loses nothing
            self._restore_unlocked(rot_tmp)
            raise
        finally:
            part_path.unlink(missing_ok=True)
        rot_tmp.unlink(missing_ok=True)
        return candidate

    def _restore_unlocked(self, rot_tmp: Path) -> None:
        """Make ``rot_tmp`` plus the lines written since the active file was replaced the active file again."""
        try:
            with open(rot_tmp, "ab") as merged, open(self.log_path, "rb") as newer:
                shutil.copyfileobj(newer, merged)
            rot_tmp.replace(self.log_path)
        except OSError:
            logger.error("audit rotation failed and the old records stay in %s", rot_tmp)

    def rotate(self, max_bytes: int | None = None, *, force: bool = False) -> Path | None:
        """Rotate and gzip-compress audit.jsonl if size >= max_bytes (or force=True)."""
        threshold = self.config.max_bytes if max_bytes is None else max_bytes
        with self._lock:
            return self._rotate_unlocked(threshold, force=force)

    @contextmanager
    def track(
        self,
        operation: str,
        source: str,
        endpoint: str = "",
        destination: str = "",
    ) -> Generator[ExecutionTracker, None, None]:
        """Context manager benchmarking an operation and persisting structured telemetry."""
        tracker = ExecutionTracker(operation, source, endpoint, destination)
        run = _Run(tracker)
        try:
            yield tracker
        except BaseException as exc:
            run.record_exception(exc)
            raise
        finally:
            self._log_or_warn(run.build_event())

    @asynccontextmanager
    async def async_track(
        self,
        operation: str,
        source: str,
        endpoint: str = "",
        destination: str = "",
    ) -> AsyncGenerator[ExecutionTracker, None]:
        """Asynchronous variant of :meth:`track`; the file write runs off the event loop."""
        tracker = ExecutionTracker(operation, source, endpoint, destination)
        run = _Run(tracker)
        try:
            yield tracker
        except BaseException as exc:
            run.record_exception(exc)
            raise
        finally:
            event = run.build_event()
            # shield so a cancelled caller still persists its CANCELLED event
            await asyncio.shield(asyncio.to_thread(self._log_or_warn, event))

    def read_events(
        self,
        limit: int | None = None,
        *,
        source: str | None = None,
        status: str | None = None,
        since: str | None = None,
    ) -> list[AuditEvent]:
        """Read and decode audit events from the JSONL log, optionally filtered.

        ``source`` and ``status`` match exactly (status case-insensitively); ``since`` is an ISO
        date or timestamp compared with the event's ``timestamp_utc``. The filters apply before
        ``limit``, which keeps the most recent matches.
        """
        if not self.log_path.exists():
            return []
        events: list[AuditEvent] = []
        skipped = 0
        with self._lock, open(self.log_path, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(self._decoder.decode(line))
                except msgspec.DecodeError:
                    skipped += 1
        if skipped:
            logger.warning("skipped %d corrupt audit line(s) in %s", skipped, self.log_path)
        if source is not None:
            events = [e for e in events if e.source == source]
        if status is not None:
            events = [e for e in events if e.status.upper() == status.upper()]
        if since is not None:
            events = [e for e in events if e.timestamp_utc >= since]
        if limit is not None and limit > 0:
            return events[-limit:]
        return events

    def get_stats(self) -> dict[str, Any]:
        """Compute aggregated telemetry statistics."""
        events = self.read_events()
        if not events:
            return {
                "total_operations": 0,
                "total_records": 0,
                "success_rate": 1.0,
                "cache_hit_rate": 0.0,
                "average_duration_seconds": 0.0,
            }

        total_ops = len(events)
        total_records = sum(e.records_count for e in events)
        successes = sum(1 for e in events if e.status == STATUS_SUCCESS)
        cache_hits = sum(1 for e in events if e.cache_hit)
        total_duration = sum(e.duration_seconds for e in events)

        return {
            "total_operations": total_ops,
            "total_records": total_records,
            "success_rate": round(successes / total_ops, 4),
            "cache_hit_rate": round(cache_hits / total_ops, 4),
            "average_duration_seconds": round(total_duration / total_ops, 4),
            "by_source": {
                source: sum(1 for e in events if e.source == source)
                for source in {e.source for e in events}
            },
        }


get_audit_logger = lazy_singleton(AuditLogger)


class _LazyAuditLogger:
    """Proxy that resolves the real logger on first attribute access (honors late config)."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_audit_logger(), name)


# Backward-compatible module-level name; no file system work happens at import time.
default_audit_logger: AuditLogger = cast(AuditLogger, _LazyAuditLogger())

__all__ = [
    "AuditConfig",
    "AuditEvent",
    "AuditLogger",
    "ExecutionTracker",
    "default_audit_logger",
    "get_audit_logger",
]
