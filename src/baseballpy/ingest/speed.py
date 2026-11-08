"""Is a download running as fast as it can? Read the audit log and say where the time goes.

A download is limited by one of three things: the host's rate limit (a polite cap, AGENTS.md section 4),
the number of requests allowed in flight, or the program's own work between requests (parsing and
writing files). The audit log records every request with its time, so the speed of the last few
minutes can be measured without touching the download: requests per second against the cap, the
latency of an answer, and (by Little's law, in flight = rate x latency) how much of the in-flight
allowance is used. From these the report names the limit and says what would help.

The report only measures and advises. It changes no setting: ADR 59 measured that raising
concurrency on a rate-bound host made single requests slower, so the caps stay fixed.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import msgspec

from baseballpy.core.config import RateLimitConfig

#: how much of the end of the audit log is read (a day of downloading is far more than this)
TAIL_BYTES = 24_000_000
#: fewer requests than this in the window is too little traffic to judge
MIN_REQUESTS = 20
AT_CAP = 0.8
IDLE_IN_FLIGHT = 0.5
PUSHBACK = 0.02


class _Event(msgspec.Struct):
    timestamp_utc: str
    operation: str
    status: str = ""
    duration_seconds: float | None = None
    endpoint: str | None = None
    error: str | None = None


@dataclass
class HostSpeed:
    """The last minutes of one host."""

    host: str
    requests: int = 0
    requests_per_second: float = 0.0
    cap: float | None = None
    utilization: float | None = None
    latency_p50: float = 0.0
    latency_p90: float = 0.0
    in_flight: float = 0.0
    in_flight_limit: int = 0
    pushed_back: int = 0
    not_found: int = 0
    diagnosis: str = ""


@dataclass
class SpeedReport:
    """What the audit log says about the last ``window_seconds``."""

    window_seconds: float
    hosts: list[HostSpeed] = field(default_factory=list)
    chunks_written: int = 0

    def line(self) -> str:
        """One line per busy host for a log."""
        if not self.hosts:
            return f"speed: no requests in the last {self.window_seconds / 60:.0f} min"
        return " | ".join(
            f"speed {h.host}: {h.requests_per_second:.1f} of {h.cap or 0:g} req/s "
            f"({(h.utilization or 0) * 100:.0f}%), answer {h.latency_p50:.2f}s, "
            f"~{h.in_flight:.1f} of {h.in_flight_limit} in flight: {h.diagnosis}"
            for h in self.hosts
        )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def read_events(path: Path, since: datetime) -> list[_Event]:
    """Events at or after ``since`` from the end of the audit log (damaged lines are skipped)."""
    try:
        size = path.stat().st_size
    except OSError:
        return []
    decoder = msgspec.json.Decoder(_Event)
    events: list[_Event] = []
    with path.open("rb") as handle:
        start = max(0, size - TAIL_BYTES)
        handle.seek(start)
        data = handle.read()
    lines = data.split(b"\n")
    if start > 0:
        lines = lines[1:]  # the first line is cut in the middle
    cutoff = since.isoformat()
    for raw in lines:
        if not raw.strip():
            continue
        try:
            event = decoder.decode(raw)
        except (msgspec.DecodeError, UnicodeDecodeError):
            continue  # a line cut by a crash or by the end of the read
        if event.timestamp_utc >= cutoff:
            events.append(event)
    return events


def diagnose(speed: HostSpeed) -> str:
    """The limit of a host in one sentence, and what would help."""
    if speed.requests < MIN_REQUESTS:
        return "too little traffic to judge (idle, or a phase without requests)"
    if speed.pushed_back / speed.requests >= PUSHBACK:
        return (
            f"the host is pushing back ({speed.pushed_back} answers of 429 or 5xx): do not speed up"
        )
    if speed.utilization is not None and speed.utilization >= AT_CAP:
        return "at the rate limit: network bound, only a higher cap would be faster"
    if speed.in_flight_limit and speed.in_flight < IDLE_IN_FLIGHT * speed.in_flight_limit:
        return (
            "below the cap with idle capacity: the wait is local (parsing and writing files), "
            "not the network"
        )
    return "below the cap with the in-flight allowance mostly used: the host answers slowly"


def measure(
    audit_path: Path,
    *,
    seconds: float = 600.0,
    now: datetime | None = None,
    rate: RateLimitConfig | None = None,
) -> SpeedReport:
    """Speed of every host over the last ``seconds``, from the audit log."""
    moment = now or datetime.now(UTC)
    cfg = rate or RateLimitConfig()
    events = read_events(audit_path, moment - timedelta(seconds=seconds))
    report = SpeedReport(window_seconds=seconds)
    by_host: dict[str, list[_Event]] = {}
    for event in events:
        if event.operation == "http_request" and event.endpoint:
            by_host.setdefault(_host_of(event.endpoint), []).append(event)
        elif event.status == "SUCCESS" and event.operation.startswith("mlb_game_"):
            report.chunks_written += 1
    for host, items in sorted(by_host.items()):
        latencies = [e.duration_seconds for e in items if e.duration_seconds is not None]
        stamps = [e.timestamp_utc for e in items]
        span = (
            datetime.fromisoformat(max(stamps)) - datetime.fromisoformat(min(stamps))
        ).total_seconds()
        span = max(span, 1.0)
        cap = cfg.host_rates.get(host)
        speed = HostSpeed(
            host=host,
            requests=len(items),
            requests_per_second=len(items) / span,
            cap=cap,
            latency_p50=_percentile(latencies, 0.5),
            latency_p90=_percentile(latencies, 0.9),
            in_flight_limit=max(1, cfg.host_concurrency.get(host, cfg.max_concurrency)),
            pushed_back=sum(1 for e in items if _pushed_back(e)),
            not_found=sum(1 for e in items if e.error and "404" in e.error),
        )
        speed.utilization = speed.requests_per_second / cap if cap else None
        speed.in_flight = speed.requests_per_second * speed.latency_p50
        speed.diagnosis = diagnose(speed)
        report.hosts.append(speed)
    return report


def _host_of(url: str) -> str:
    """``host`` of ``https://host/path`` (no network library is imported in the ingest layer)."""
    return url.split("//", 1)[-1].split("/", 1)[0]


def _pushed_back(event: _Event) -> bool:
    text = event.error or ""
    return any(code in text for code in ("429", "500", "502", "503", "504"))


def default_audit_path() -> Path:
    """The audit log of the current lake (``$BASEBALLPY_HOME/logs/audit.jsonl``)."""
    from baseballpy.core.config import AuditConfig

    return AuditConfig().audit_file


__all__ = [
    "HostSpeed",
    "SpeedReport",
    "default_audit_path",
    "diagnose",
    "measure",
    "read_events",
]
