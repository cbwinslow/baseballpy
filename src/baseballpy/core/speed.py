"""Check real request speeds in the audit log against the caps the client enforces (ADR 67).

The input is the audit events (``http_request`` events written by ``HttpClient`` for every real
network attempt, plus the ``ingest_job`` events of the runner); the caps come from
:class:`RateLimitConfig`, the same numbers the client enforces. Everything here is a pure function
of its arguments so tests feed it synthetic events.

How the rate bound is derived: the client uses a leaky bucket of ``rate`` requests per second that
starts empty, so in any window of ``W`` seconds at most ``rate * (W + 1)`` requests may start (the
bucket's capacity plus what leaks out during the window). A window with more starts broke the cap.
"""

import bisect
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlparse

from baseballpy.core.audit import AuditEvent
from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HTTP_OPERATION

JOB_OPERATION = "ingest_job"
#: window lengths (seconds) the rate bound is checked over
WINDOWS = (1.0, 10.0, 60.0)


@dataclass(frozen=True)
class HostSpeed:
    """What one host's requests did, next to the caps."""

    host: str
    requests: int
    retries: int
    failures: int
    span_seconds: float
    mean_rps: float
    peak_rps_1s: float
    sustained_rps_60s: float
    peak_in_flight: int
    p50_seconds: float
    p95_seconds: float
    rate_cap: float
    in_flight_cap: int
    problems: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceSpeed:
    """How fast one source turned requests into rows, over the time its jobs were running."""

    source: str
    jobs: int
    failed_jobs: int
    rows: int
    busy_seconds: float
    rows_per_second: float


def _ts(text: str) -> float:
    return datetime.fromisoformat(text).timestamp()


def _interval(event: AuditEvent) -> tuple[float, float]:
    """``(sent, ended)`` seconds of an event; old events without a start use end minus duration."""
    ended = _ts(event.completed_at_utc or event.timestamp_utc)
    started = _ts(event.started_at_utc) if event.started_at_utc else ended - event.duration_seconds
    return started, max(ended, started)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, round(fraction * (len(sorted_values) - 1)))
    return sorted_values[index]


def _max_starts_in_window(starts: list[float], window: float) -> int:
    """Most request starts inside any half-open window of ``window`` seconds."""
    best = 0
    for i, start in enumerate(starts):
        best = max(best, bisect.bisect_left(starts, start + window) - i)
    return best


def _peak_in_flight(intervals: list[tuple[float, float]]) -> int:
    """Largest number of requests that were in flight at the same moment."""
    edges = [(s, 1) for s, _ in intervals] + [(e, -1) for _, e in intervals]
    edges.sort(key=lambda edge: (edge[0], edge[1]))  # an end before a start at the same instant
    level = peak = 0
    for _, delta in edges:
        level += delta
        peak = max(peak, level)
    return peak


def host_speeds(
    events: Iterable[AuditEvent], rate: RateLimitConfig | None = None, *, host: str | None = None
) -> list[HostSpeed]:
    """Per-host request speeds with the cap problems each host broke (empty list: nothing broke)."""
    rate = rate or RateLimitConfig()
    by_host: dict[str, list[AuditEvent]] = {}
    for event in events:
        if event.operation != HTTP_OPERATION:
            continue
        name = urlparse(event.endpoint).netloc
        if host is None or name == host:
            by_host.setdefault(name, []).append(event)
    out: list[HostSpeed] = []
    for name, items in sorted(by_host.items()):
        intervals = sorted(_interval(e) for e in items)
        starts = [s for s, _ in intervals]
        span = max(e for _, e in intervals) - starts[0]
        cap = rate.host_rates.get(name, rate.default_requests_per_second)
        in_flight_cap = max(1, rate.host_concurrency.get(name, rate.max_concurrency))
        latency = sorted(e.duration_seconds for e in items)
        peak_1s = _max_starts_in_window(starts, 1.0)
        peak_60s = _max_starts_in_window(starts, 60.0)
        peak_flight = _peak_in_flight(intervals)
        problems: list[str] = []
        for window in WINDOWS:
            count = _max_starts_in_window(starts, window)
            allowed = cap * (window + 1.0) + 1.0
            if count > allowed:
                problems.append(
                    f"rate: {count} requests started within {window:g} s, "
                    f"the cap of {cap:g}/s allows {allowed:g}"
                )
        if peak_flight > in_flight_cap:
            problems.append(
                f"in flight: {peak_flight} requests at once, the limit is {in_flight_cap}"
            )
        failures = sum(1 for e in items if e.status == "FAILURE")
        if failures:
            problems.append(f"{failures} request(s) failed")
        out.append(
            HostSpeed(
                host=name,
                requests=len(items),
                retries=sum(1 for e in items if e.status == "RETRY"),
                failures=failures,
                span_seconds=round(span, 2),
                mean_rps=round(len(items) / span, 2) if span > 0 else float(len(items)),
                peak_rps_1s=float(peak_1s),
                sustained_rps_60s=round(peak_60s / 60.0, 2),
                peak_in_flight=peak_flight,
                p50_seconds=round(_percentile(latency, 0.5), 3),
                p95_seconds=round(_percentile(latency, 0.95), 3),
                rate_cap=cap,
                in_flight_cap=in_flight_cap,
                problems=problems,
            )
        )
    return out


def _union_seconds(intervals: list[tuple[float, float]]) -> float:
    """Total time covered by the intervals (overlaps counted once)."""
    total = 0.0
    current_start = current_end = None
    for start, end in sorted(intervals):
        if current_end is None or start > current_end:
            if current_end is not None and current_start is not None:
                total += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None and current_start is not None:
        total += current_end - current_start
    return total


def source_speeds(events: Iterable[AuditEvent]) -> list[SourceSpeed]:
    """Rows per second of each source's ingest jobs, counting the time any of its jobs ran once."""
    by_source: dict[str, list[AuditEvent]] = {}
    for event in events:
        if event.operation == JOB_OPERATION:
            by_source.setdefault(event.source, []).append(event)
    out: list[SourceSpeed] = []
    for source, items in sorted(by_source.items()):
        busy = _union_seconds([_interval(e) for e in items])
        rows = sum(e.records_count for e in items if e.status == "SUCCESS")
        out.append(
            SourceSpeed(
                source=source,
                jobs=len(items),
                failed_jobs=sum(1 for e in items if e.status != "SUCCESS"),
                rows=rows,
                busy_seconds=round(busy, 1),
                rows_per_second=round(rows / busy, 1) if busy > 0 else 0.0,
            )
        )
    return out


__all__ = ["HostSpeed", "SourceSpeed", "host_speeds", "source_speeds"]
