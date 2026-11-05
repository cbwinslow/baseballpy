"""Real requests are audited and the log is checked against the caps the client enforces (ADR 67)."""

import json
import threading
from datetime import UTC, datetime

import httpx
import pytest
import respx
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.audit import AuditEvent, default_audit_logger
from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient
from baseballpy.core.speed import host_speeds, source_speeds

HOST = "api.example.com"
BASE = 1_800_000_000.0


def _iso(seconds: float) -> str:
    return datetime.fromtimestamp(BASE + seconds, UTC).isoformat()


def _request(start: float, duration: float = 0.2, status: str = "SUCCESS") -> AuditEvent:
    return AuditEvent(
        timestamp_utc=_iso(start + duration),
        started_at_utc=_iso(start),
        completed_at_utc=_iso(start + duration),
        operation="http_request",
        source="http",
        status=status,
        duration_seconds=duration,
        endpoint=f"https://{HOST}/v1/thing",
    )


def _job(source: str, start: float, end: float, rows: int, status: str = "SUCCESS") -> AuditEvent:
    return AuditEvent(
        timestamp_utc=_iso(end),
        started_at_utc=_iso(start),
        completed_at_utc=_iso(end),
        operation="ingest_job",
        source=source,
        status=status,
        records_count=rows,
        duration_seconds=end - start,
    )


def _rate(cap: float, in_flight: int = 4) -> RateLimitConfig:
    return RateLimitConfig(host_rates={HOST: cap}, host_concurrency={HOST: in_flight})


def test_a_host_that_stays_under_its_rate_has_no_problem() -> None:
    events = [_request(i * 0.1) for i in range(200)]  # 10 per second for 20 seconds
    (speed,) = host_speeds(events, _rate(10.0))
    assert speed.problems == [] and speed.requests == 200
    assert speed.peak_in_flight <= 4 and 9.0 <= speed.mean_rps <= 11.0


def test_the_limiters_own_burst_is_allowed_but_more_is_a_broken_cap() -> None:
    allowed = [_request(0.0) for _ in range(10)]  # the bucket's capacity at once
    (ok,) = host_speeds(allowed, _rate(10.0, in_flight=50))
    assert ok.problems == []
    burst = [_request(0.0) for _ in range(60)]  # 60 starts in one second against a cap of 10/s
    (bad,) = host_speeds(burst, _rate(10.0, in_flight=100))
    assert any(p.startswith("rate:") and "within 1 s" in p for p in bad.problems)


def test_a_sustained_rate_over_the_cap_is_found_in_the_long_window() -> None:
    events = [_request(i * 0.05) for i in range(1200)]  # 20 per second for 60 seconds
    (speed,) = host_speeds(events, _rate(10.0, in_flight=100))
    assert any("within 60 s" in p for p in speed.problems)


def test_more_requests_in_flight_than_the_limit_is_a_problem_but_touching_ones_are_not() -> None:
    overlapping = [_request(0.0, duration=1.0) for _ in range(6)]
    (bad,) = host_speeds(overlapping, _rate(100.0, in_flight=4))
    assert any(p.startswith("in flight: 6") for p in bad.problems)
    back_to_back = [
        _request(i * 1.0, duration=1.0) for i in range(6)
    ]  # each ends as the next starts
    (ok,) = host_speeds(back_to_back, _rate(100.0, in_flight=1))
    assert ok.peak_in_flight == 1 and ok.problems == []


def test_failures_are_a_problem_and_retries_are_only_counted() -> None:
    events = [_request(0.0), _request(1.0, status="RETRY"), _request(2.0, status="FAILURE")]
    (speed,) = host_speeds(events, _rate(10.0))
    assert speed.retries == 1 and speed.failures == 1
    assert speed.problems == ["1 request(s) failed"]


def test_events_that_are_not_requests_and_other_hosts_are_filtered() -> None:
    other = _request(0.0)
    other.endpoint = "https://other.example.com/x"
    events = [_request(0.0), other, _job("lahman", 0, 5, 10)]
    assert [s.host for s in host_speeds(events)] == ["api.example.com", "other.example.com"]
    assert [s.host for s in host_speeds(events, host=HOST)] == ["api.example.com"]


def test_rows_per_second_counts_overlapping_jobs_once() -> None:
    events = [
        _job("statcast", 0, 10, 1000),
        _job("statcast", 5, 15, 1000),  # overlaps: busy time is 15 s, not 20 s
        _job("statcast", 100, 110, 500, status="FAILURE"),  # failed rows are not counted
    ]
    (speed,) = source_speeds(events)
    assert speed.jobs == 3 and speed.failed_jobs == 1 and speed.rows == 2000
    assert speed.busy_seconds == 25.0 and speed.rows_per_second == 80.0


def _audit_events() -> list[AuditEvent]:
    return default_audit_logger.read_events()


@respx.mock
def test_the_client_records_one_event_per_real_attempt_with_its_send_time() -> None:
    url = f"https://{HOST}/v1/thing"
    route = respx.get(url).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, content=b"ok")]
    )
    client = HttpClient(
        RateLimitConfig(host_rates={HOST: 1000.0}, max_retries=3, backoff_factor=0.01), http2=False
    )
    try:
        assert client.get_sync(url, params={"secret": "x"}).content == b"ok"
    finally:
        client.close()
    assert route.call_count == 2
    events = [e for e in _audit_events() if e.operation == "http_request"]
    assert [e.status for e in events] == ["RETRY", "SUCCESS"]
    assert events[0].error == "HTTP 503" and events[1].error is None
    assert all(e.endpoint == url and "secret" not in e.endpoint for e in events)  # no query string
    assert all(e.started_at_utc and e.completed_at_utc >= e.started_at_utc for e in events)


@respx.mock
def test_a_real_burst_through_the_real_limiter_stays_inside_the_caps_the_log_is_checked_against() -> (
    None
):
    """The client, its limiter and the checker agree: the log of a real run passes the check."""
    respx.get(f"https://{HOST}/v1/thing").mock(return_value=httpx.Response(200, content=b"x"))
    rate = RateLimitConfig(host_rates={HOST: 40.0}, host_concurrency={HOST: 3})
    client = HttpClient(rate, http2=False)
    url = f"https://{HOST}/v1/thing"
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(15):
                client.get_sync(url)
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(6)]  # 90 requests, 6 callers
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
    finally:
        client.close()
    assert errors == []
    (speed,) = host_speeds(_audit_events(), rate)
    assert speed.requests == 90
    assert speed.problems == [], speed.problems
    assert speed.peak_in_flight <= 3
    # 90 requests at 40/s: the bucket lets 40 go at once, the other 50 need at least 1.25 s
    assert speed.span_seconds >= 1.0


def _run(args: list[str]) -> tuple[int, str]:
    result = CliRunner().invoke(main, ["audit", "speed", *args])
    return result.exit_code, result.output


def _write(events: list[AuditEvent]) -> None:
    for event in events:
        default_audit_logger.log(event)


def test_the_command_exits_zero_when_every_cap_held_and_one_when_not() -> None:
    _write([_request(i * 0.2) for i in range(50)] + [_job("lahman", 0, 10, 5000)])
    code, output = _run([])
    assert code == 0 and "Every host stayed inside" in output
    _write([_request(1000.0, duration=5.0) for _ in range(40)])  # 40 in flight at once
    code, output = _run([])
    assert code == 1 and "in flight" in output


def test_the_command_prints_json_and_says_so_when_there_is_nothing_to_check() -> None:
    code, output = _run([])
    assert code == 0 and "nothing to check" in output
    _write([_request(0.0), _job("statcast", 0, 4, 400)])
    code, output = _run(["--json"])
    data = json.loads(output)
    assert code == 0 and data["hosts"][0]["host"] == HOST
    assert data["sources"][0]["rows_per_second"] == 100.0


def test_a_log_without_request_events_says_the_caps_cannot_be_checked() -> None:
    _write([_job("retrosheet", 0, 10, 1000)])
    code, output = _run([])
    assert code == 0 and "cannot be checked" in output


@pytest.mark.parametrize("flag", ["--host", "--since"])
def test_the_filters_are_accepted(flag: str) -> None:
    value = "nope.example.com" if flag == "--host" else "2999-01-01"
    _write([_request(0.0)])
    code, output = _run([flag, value])
    assert code == 0, output
