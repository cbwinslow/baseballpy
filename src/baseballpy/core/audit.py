"""Structured audit logging, execution benchmarking, and telemetry engine."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import msgspec

from baseballpy.core.config import AuditConfig


class AuditEvent(msgspec.Struct, kw_only=True):
    """Structured audit log entry persisted to JSON Lines."""

    timestamp_utc: str
    operation: str
    source: str
    status: str  # "SUCCESS", "FAILURE", "RETRY"
    records_count: int = 0
    duration_seconds: float = 0.0
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
        self.error: str | None = None

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


class AuditLogger:
    """Thread-safe, append-only structured audit logger for pipeline operations."""

    def __init__(self, config: AuditConfig | None = None) -> None:
        self.config = config or AuditConfig()
        self._encoder = msgspec.json.Encoder()
        self._decoder = msgspec.json.Decoder(AuditEvent)

    @property
    def log_path(self) -> Path:
        """Return the path to the audit.jsonl log file."""
        return self.config.audit_file

    def log(self, event: AuditEvent) -> None:
        """Append an audit event to the JSONL log file."""
        if not self.config.enabled:
            return
        line = self._encoder.encode(event) + b"\n"
        with open(self.log_path, "ab") as f:
            f.write(line)

    @contextmanager
    def track(
        self,
        operation: str,
        source: str,
        endpoint: str = "",
        destination: str = "",
    ) -> Generator[ExecutionTracker, None, None]:
        """Context manager benchmarking an operation and persisting structured telemetry."""
        tracker = ExecutionTracker(
            operation=operation,
            source=source,
            endpoint=endpoint,
            destination=destination,
        )
        start_time = time.perf_counter()
        status = "SUCCESS"
        error_msg: str | None = None

        try:
            yield tracker
        except Exception as exc:
            status = "FAILURE"
            error_msg = f"{type(exc).__name__}: {exc}"
            tracker.error = error_msg
            raise
        finally:
            duration = time.perf_counter() - start_time
            throughput = (
                float(tracker.records_count) / duration
                if duration > 0 and tracker.records_count > 0
                else 0.0
            )
            event = AuditEvent(
                timestamp_utc=datetime.now(UTC).isoformat(),
                operation=tracker.operation,
                source=tracker.source,
                status=status,
                records_count=tracker.records_count,
                duration_seconds=round(duration, 4),
                throughput_rps=round(throughput, 1),
                cache_hit=tracker.cache_hit,
                endpoint=tracker.endpoint,
                destination=tracker.destination,
                error=error_msg,
            )
            self.log(event)

    def read_events(self, limit: int | None = None) -> list[AuditEvent]:
        """Read and decode historical audit events from the JSONL log file."""
        if not self.log_path.exists():
            return []
        events: list[AuditEvent] = []
        with open(self.log_path, "rb") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(self._decoder.decode(line))
                except msgspec.DecodeError:
                    continue
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
        successes = sum(1 for e in events if e.status == "SUCCESS")
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


# Global default audit logger
default_audit_logger = AuditLogger()
