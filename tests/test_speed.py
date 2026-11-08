"""Download speed from the audit log: requests per second against the cap, and what limits it."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import RateLimitConfig
from baseballpy.ingest.speed import HostSpeed, diagnose, measure

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)
HOST = "statsapi.mlb.com"


def _event(
    seconds_ago: float, *, host: str = HOST, latency: float = 1.0, error: str | None = None
) -> str:
    stamp = (NOW - timedelta(seconds=seconds_ago)).isoformat()
    return json.dumps(
        {
            "timestamp_utc": stamp,
            "operation": "http_request",
            "source": "http",
            "status": "FAILED" if error else "SUCCESS",
            "duration_seconds": latency,
            "endpoint": f"https://{host}/api/v1/game/1/boxscore",
            "error": error,
        }
    )


def _log(tmp_path: Path, lines: list[str]) -> Path:
    path = tmp_path / "audit.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _rate(in_flight: int = 12) -> RateLimitConfig:
    return RateLimitConfig(host_concurrency={HOST: in_flight})


def test_speed_is_requests_per_second_against_the_cap(tmp_path: Path) -> None:
    # 300 requests spread over 100 seconds, 1 s answers: 3 per second, ~3 in flight, cap 10
    lines = [_event(100 - i / 3) for i in range(300)]
    report = measure(_log(tmp_path, lines), seconds=600, now=NOW, rate=_rate())
    host = report.hosts[0]
    assert host.host == HOST and host.requests == 300
    assert 2.9 < host.requests_per_second < 3.1
    assert host.cap == 10.0 and 0.28 < (host.utilization or 0) < 0.32
    assert 2.9 < host.in_flight < 3.1 and host.in_flight_limit == 12
    assert "local" in host.diagnosis  # idle capacity: the wait is not the network


def test_the_four_verdicts() -> None:
    base = {"host": HOST, "requests": 100, "cap": 10.0, "in_flight_limit": 12}
    assert "too little" in diagnose(HostSpeed(**{**base, "requests": 5}))  # type: ignore[arg-type]
    assert "pushing back" in diagnose(
        HostSpeed(**base, requests_per_second=5, utilization=0.5, in_flight=6, pushed_back=3)  # type: ignore[arg-type]
    )
    assert "rate limit" in diagnose(
        HostSpeed(**base, requests_per_second=9, utilization=0.9, in_flight=9)  # type: ignore[arg-type]
    )
    assert "local" in diagnose(
        HostSpeed(**base, requests_per_second=3, utilization=0.3, in_flight=3)  # type: ignore[arg-type]
    )
    assert "answers slowly" in diagnose(
        HostSpeed(**base, requests_per_second=3, utilization=0.3, in_flight=10)  # type: ignore[arg-type]
    )


def test_a_full_in_flight_allowance_below_the_cap_means_the_host_is_slow(tmp_path: Path) -> None:
    lines = [_event(100 - i / 3, latency=4.0) for i in range(300)]
    host = measure(_log(tmp_path, lines), seconds=600, now=NOW, rate=_rate(in_flight=12)).hosts[0]
    assert "answers slowly" in host.diagnosis
    assert (
        measure(_log(tmp_path, lines), seconds=600, now=NOW, rate=_rate(in_flight=4))
        .hosts[0]
        .in_flight_limit
        == 4
    )


def test_pushback_and_old_or_damaged_lines(tmp_path: Path) -> None:
    lines = [
        '{"timestamp_utc": "2026-11-08T11',  # a line cut by a crash
        _event(7200),  # outside the window
        *[_event(50 - i / 3, error="HTTP 429") for i in range(30)],
        *[_event(50 - i / 3) for i in range(70)],
    ]
    host = measure(_log(tmp_path, lines), seconds=600, now=NOW, rate=_rate()).hosts[0]
    assert host.requests == 100 and host.pushed_back == 30
    assert "pushing back" in host.diagnosis


def test_a_missing_log_or_no_traffic_says_so(tmp_path: Path) -> None:
    empty = measure(tmp_path / "none.jsonl", seconds=60, now=NOW, rate=_rate())
    assert empty.hosts == [] and "no requests" in empty.line()


def test_the_speed_command(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = _log(tmp_path, [_event(10 - i / 20) for i in range(60)])
    monkeypatch.setattr("baseballpy.cli_speed.default_audit_path", lambda: path)
    monkeypatch.setattr(
        "baseballpy.cli_speed.measure",
        lambda p, seconds: measure(p, seconds=seconds, now=NOW, rate=_rate()),
    )
    result = CliRunner().invoke(main, ["speed", "--minutes", "5", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["hosts"][0]["host"] == HOST and data["hosts"][0]["requests"] == 60
