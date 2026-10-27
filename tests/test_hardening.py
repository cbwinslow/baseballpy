"""Tests for the hardened core: manifest locking, audit status, quarantine, freshness, HTTP, sinks."""

import asyncio
import inspect
import json
import threading
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import respx

from baseballpy.core.atomic import (
    ManifestTracker,
    atomic_write,
    cleanup_stale_parts,
)
from baseballpy.core.audit import AuditConfig, AuditLogger
from baseballpy.core.coerce import CoercionError, to_bool, to_date, to_float, to_int
from baseballpy.core.config import CacheConfig, QuarantineConfig, RateLimitConfig
from baseballpy.core.freshness import is_fresh
from baseballpy.core.http import HttpClient, HttpStatusError
from baseballpy.core.protocols import SinkProtocol
from baseballpy.core.quarantine import Quarantine, checked_cast
from baseballpy.core.sql import quote_ident
from baseballpy.sinks.dlt import DltSink
from baseballpy.sinks.duckdb import DuckDBSink
from baseballpy.sinks.parquet import ParquetSink
from baseballpy.sinks.polars import PolarsSink

# ----------------------------------------------------------------------------- atomic / manifest


def test_atomic_part_names_are_unique(tmp_path: Path) -> None:
    target = tmp_path / "x.bin"
    seen: list[Path] = []
    for _ in range(2):
        with atomic_write(target) as part:
            seen.append(part)
            part.write_bytes(b"1")
    assert seen[0] != seen[1]
    assert all(p.name.endswith(".part") and not p.exists() for p in seen)
    assert target.read_bytes() == b"1"


def test_atomic_write_cleans_up_on_keyboard_interrupt(tmp_path: Path) -> None:
    target = tmp_path / "x.bin"
    with pytest.raises(KeyboardInterrupt), atomic_write(target) as part:
        part.write_bytes(b"partial")
        raise KeyboardInterrupt
    assert not target.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_cleanup_stale_parts(tmp_path: Path) -> None:
    stale = tmp_path / "a.csv.1.abc.part"
    stale.write_bytes(b"x")
    old = time.time() - 7200
    import os

    os.utime(stale, (old, old))
    fresh = tmp_path / "b.csv.1.def.part"
    fresh.write_bytes(b"x")
    removed = cleanup_stale_parts(tmp_path, older_than_seconds=3600)
    assert removed == [stale]
    assert fresh.exists()


def test_manifest_concurrent_writers_do_not_lose_chunks(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    trackers = [ManifestTracker(path) for _ in range(4)]

    def work(idx: int) -> None:
        for n in range(10):
            trackers[idx].set_completed(f"chunk-{idx}-{n}", records_count=n)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = json.loads(path.read_text(encoding="utf-8"))
    assert len(final["chunks"]) == 40
    assert ManifestTracker(path).is_completed("chunk-3-9")


def test_manifest_sees_other_instances_chunks(tmp_path: Path) -> None:
    path = tmp_path / "m.json"
    a, b = ManifestTracker(path), ManifestTracker(path)
    a.set_completed("one")
    assert b.is_completed("one")


def test_corrupt_manifest_is_preserved_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text("{not json", encoding="utf-8")
    with caplog.at_level("ERROR"):
        tracker = ManifestTracker(path)
    assert not tracker.is_completed("x")
    backups = list(tmp_path.glob("manifest.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not json"
    assert any("corrupt" in r.message for r in caplog.records)


def test_manifest_absent_status_is_not_completed(tmp_path: Path) -> None:
    tracker = ManifestTracker(tmp_path / "m.json")
    tracker.set_absent("season_1800", "404")
    assert not tracker.is_completed("season_1800")
    chunk = tracker.get_chunk("season_1800")
    assert chunk is not None and chunk["status"] == "ABSENT"


# ----------------------------------------------------------------------------- audit


def test_audit_records_cancellation_not_success(tmp_path: Path) -> None:
    logger = AuditLogger(AuditConfig(base_dir=tmp_path))

    async def run() -> None:
        async def body() -> None:
            async with logger.async_track("op", "src"):
                await asyncio.sleep(10)

        task = asyncio.create_task(body())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    events = logger.read_events()
    assert [e.status for e in events] == ["CANCELLED"]


def test_audit_keyboard_interrupt_is_cancelled(tmp_path: Path) -> None:
    logger = AuditLogger(AuditConfig(base_dir=tmp_path))
    with pytest.raises(KeyboardInterrupt), logger.track("op", "src"):
        raise KeyboardInterrupt
    assert logger.read_events()[0].status == "CANCELLED"


def test_audit_counts_corrupt_lines(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    logger = AuditLogger(AuditConfig(base_dir=tmp_path))
    with logger.track("op", "src"):
        pass
    with open(logger.log_path, "ab") as f:
        f.write(b"garbage\n")
    with caplog.at_level("WARNING"):
        events = logger.read_events()
    assert len(events) == 1
    assert any("corrupt audit line" in r.message for r in caplog.records)


def test_default_audit_logger_honors_late_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.core.audit import default_audit_logger, get_audit_logger

    get_audit_logger.reset()
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    try:
        with default_audit_logger.track("op", "src"):
            pass
        assert (tmp_path / "logs" / "audit.jsonl").exists()
    finally:
        get_audit_logger.reset()


# ----------------------------------------------------------------------------- coerce


def test_coerce_parses_or_raises() -> None:
    assert to_int("12") == 12
    assert to_int("12.0") == 12
    assert to_int("") is None
    assert to_int("NA") is None
    with pytest.raises(CoercionError):
        to_int("12.5")
    with pytest.raises(CoercionError):
        to_int("abc")
    assert to_float("1,234.5") == 1234.5
    assert to_float("50%", strip_percent=True) == 50.0
    with pytest.raises(CoercionError):
        to_float("x")
    assert to_bool("Y") is True
    assert to_bool("0") is False
    with pytest.raises(CoercionError):
        to_bool("maybe")
    assert to_date("2024-04-05") == date(2024, 4, 5)
    with pytest.raises(CoercionError):
        to_date("04/05/2024")


# ----------------------------------------------------------------------------- quarantine


def test_quarantine_writes_dead_letters(tmp_path: Path) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    path = q.write("statcast", "pitches", [{"a": 1}, b"raw"], "bad", {"file": "x"})
    assert path is not None and path.exists()
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    assert lines[0]["reason"] == "bad" and lines[0]["context"] == {"file": "x"}
    assert "__base64__" in lines[1]["payload"]
    assert "quarantine" in str(path)


def test_checked_cast_nulls_only_bad_cells_and_quarantines(tmp_path: Path) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    arr = pa.array(["1", "2", "3.7", "x", None])
    out = checked_cast(arr, pa.int32(), quarantine=q, source="s", dataset="d", column="c")
    assert out.to_pylist() == [1, 2, None, None, None]
    files = list((tmp_path / "quarantine").rglob("*.jsonl"))
    assert len(files) == 1
    payloads = [json.loads(x)["payload"] for x in files[0].read_text().splitlines()]
    assert {p["value"] for p in payloads} == {"3.7", "x"}


def test_checked_cast_never_truncates(tmp_path: Path) -> None:
    q = Quarantine(QuarantineConfig(base_dir=tmp_path))
    out = checked_cast(
        pa.array([1.9]), pa.int32(), quarantine=q, source="s", dataset="d", column="c"
    )
    assert out.to_pylist() == [None]


# ----------------------------------------------------------------------------- freshness


def test_freshness_rules() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    entry = {
        "status": "COMPLETED",
        "fetched_at": (now - timedelta(minutes=20)).isoformat(),
    }
    assert not is_fresh(entry, ttl_seconds=900, season=2026, now=now)
    assert is_fresh(entry, ttl_seconds=3600, season=2026, now=now)
    assert is_fresh(entry, ttl_seconds=900, season=2024, now=now)  # historical = immutable
    assert is_fresh(entry, ttl_seconds=None, now=now)
    assert not is_fresh(entry, ttl_seconds=None, now=now, refresh=True)
    assert not is_fresh({"status": "FAILED"}, ttl_seconds=None, now=now)
    assert not is_fresh(None, ttl_seconds=None, now=now)


def test_cache_config_ttl_policy(tmp_path: Path) -> None:
    cfg = CacheConfig(base_dir=tmp_path, today=date(2026, 6, 1), ttl_overrides={"schedule": 5})
    assert cfg.ttl_for("schedule") == 5
    assert cfg.ttl_for("lahman") is None
    assert cfg.ttl_for("unknown-dataset") == cfg.ttl_seconds
    old = {"status": "COMPLETED", "fetched_at": "2000-01-01T00:00:00+00:00"}
    assert cfg.is_fresh(old, "schedule", season=2020)
    assert not cfg.is_fresh(old, "schedule", season=2026)


# ----------------------------------------------------------------------------- http


def _client(**kw: float | int) -> HttpClient:
    cfg = RateLimitConfig(
        backoff_factor=0.01,
        max_retries=int(kw.pop("max_retries", 3)),
        **kw,  # type: ignore[arg-type]
    )
    return HttpClient(cfg, http2=False)


@respx.mock
def test_http_retries_429_with_retry_after_then_succeeds() -> None:
    route = respx.get("https://api.example.com/x").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, content=b"ok", headers={"ETag": '"e1"'}),
        ]
    )
    client = _client()
    try:
        res = client.get_sync("https://api.example.com/x")
    finally:
        client.close()
    assert res.content == b"ok" and res.etag == '"e1"'
    assert route.call_count == 2


@respx.mock
def test_http_does_not_retry_404() -> None:
    route = respx.get("https://api.example.com/missing").mock(return_value=httpx.Response(404))
    client = _client()
    try:
        with pytest.raises(HttpStatusError) as err:
            client.get_sync("https://api.example.com/missing")
    finally:
        client.close()
    assert err.value.status == 404
    assert route.call_count == 1


@respx.mock
def test_http_allow_404_returns_result() -> None:
    respx.get("https://api.example.com/missing").mock(return_value=httpx.Response(404))
    client = _client()
    try:
        res = client.get_sync("https://api.example.com/missing", allow=(200, 404))
    finally:
        client.close()
    assert res.status == 404


@respx.mock
def test_http_retries_transport_errors() -> None:
    route = respx.get("https://api.example.com/t").mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, content=b"fine")]
    )
    client = _client()
    try:
        assert client.get_sync("https://api.example.com/t").content == b"fine"
    finally:
        client.close()
    assert route.call_count == 2


@respx.mock
def test_http_gives_up_after_max_retries() -> None:
    route = respx.get("https://api.example.com/e").mock(return_value=httpx.Response(503))
    client = _client(max_retries=3)
    try:
        with pytest.raises(HttpStatusError):
            client.get_sync("https://api.example.com/e")
    finally:
        client.close()
    assert route.call_count == 3


@respx.mock
def test_http_conditional_304() -> None:
    respx.get("https://api.example.com/c").mock(return_value=httpx.Response(304))
    client = _client()
    try:
        res = client.get_sync("https://api.example.com/c", etag='"abc"')
    finally:
        client.close()
    assert res.not_modified and res.content == b""


@respx.mock
def test_http_rate_limit_spaces_requests() -> None:
    respx.get("https://slow.example.com/r").mock(return_value=httpx.Response(200, content=b"1"))
    client = HttpClient(
        RateLimitConfig(host_rates={"slow.example.com": 5.0}, max_concurrency=8), http2=False
    )
    try:
        started = time.perf_counter()
        for _ in range(8):
            client.get_sync("https://slow.example.com/r")
        elapsed = time.perf_counter() - started
    finally:
        client.close()
    # 5 req/s with an initial burst of 5: 8 requests need >= ~0.5s
    assert elapsed >= 0.5


@respx.mock
def test_http_semaphore_bounds_concurrency() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.05)
        with lock:
            active -= 1
        return httpx.Response(200, content=b"x")

    respx.get(url__startswith="https://c.example.com/").mock(side_effect=handler)
    client = HttpClient(
        RateLimitConfig(default_requests_per_second=1000, max_concurrency=2), http2=False
    )

    async def run() -> None:
        await asyncio.gather(*[client.get(f"https://c.example.com/{i}") for i in range(8)])

    try:
        asyncio.run(run())
    finally:
        client.close()
    assert peak <= 2


# ----------------------------------------------------------------------------- sinks


def _table(n: int = 3, offset: int = 0) -> pa.Table:
    return pa.table(
        {
            "game_pk": pa.array([1] * n, pa.int32()),
            "at_bat_number": pa.array([i + offset for i in range(n)], pa.int32()),
            "pitch_number": pa.array([1] * n, pa.int32()),
            "speed": pa.array([90.0 + i for i in range(n)], pa.float32()),
        }
    )


def test_quote_ident_rejects_injection() -> None:
    assert quote_ident("pitches") == '"pitches"'
    assert quote_ident("main.pitches") == '"main"."pitches"'
    for bad in ("x; DROP TABLE y", 'a"b', "", "a.b.c", "1abc", "a b"):
        with pytest.raises(ValueError):
            quote_ident(bad)


def test_duckdb_sink_rejects_injection(tmp_path: Path) -> None:
    db = str(tmp_path / "t.duckdb")
    with pytest.raises(ValueError):
        DuckDBSink().write(_table(), db, table_name="x; DROP TABLE y")
    assert not Path(db).exists()


def test_duckdb_upsert_is_idempotent(tmp_path: Path) -> None:
    db = str(tmp_path / "t.duckdb")
    keys = ["game_pk", "at_bat_number", "pitch_number"]
    sink = DuckDBSink()
    sink.write(_table(3), db, table_name="p", mode="upsert", key_columns=keys)
    sink.write(_table(3), db, table_name="p", mode="upsert", key_columns=keys)
    updated = _table(2).set_column(3, "speed", pa.array([99.0, 98.0], pa.float32()))
    sink.write(updated, db, table_name="p", mode="upsert", key_columns=keys)
    con = duckdb.connect(db)
    assert con.execute("SELECT count(*) FROM p").fetchone() == (3,)
    assert con.execute("SELECT speed FROM p WHERE at_bat_number = 0").fetchone() == (99.0,)
    con.close()


def test_duckdb_upsert_requires_keys(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="key_columns"):
        DuckDBSink().write(_table(), str(tmp_path / "t.duckdb"), table_name="p", mode="upsert")


def test_duckdb_append_by_name_and_schema_drift(tmp_path: Path) -> None:
    db = str(tmp_path / "t.duckdb")
    sink = DuckDBSink()
    sink.write(_table(2), db, table_name="p")
    reordered = _table(2, offset=10).select(["speed", "pitch_number", "at_bat_number", "game_pk"])
    sink.write(reordered, db, table_name="p")
    extra = _table(1, offset=20).append_column("new_metric", pa.array([1.5], pa.float64()))
    sink.write(extra, db, table_name="p")
    con = duckdb.connect(db)
    assert con.execute("SELECT count(*) FROM p").fetchone() == (5,)
    assert con.execute("SELECT game_pk FROM p WHERE at_bat_number = 10").fetchone() == (1,)
    assert con.execute("SELECT new_metric FROM p WHERE at_bat_number = 20").fetchone() == (1.5,)
    assert con.execute("SELECT count(*) FROM p WHERE new_metric IS NULL").fetchone() == (4,)
    con.close()


def test_duckdb_replace_with_empty_table_replaces(tmp_path: Path) -> None:
    db = str(tmp_path / "t.duckdb")
    sink = DuckDBSink()
    sink.write(_table(3), db, table_name="p")
    sink.write(_table(0), db, table_name="p", mode="replace")
    con = duckdb.connect(db)
    assert con.execute("SELECT count(*) FROM p").fetchone() == (0,)
    con.close()


def test_duckdb_stream_uses_single_audit_event(tmp_path: Path) -> None:
    from baseballpy.core.audit import get_audit_logger

    get_audit_logger.reset()
    import os

    os.environ["BASEBALLPY_HOME"] = str(tmp_path / "home")
    try:
        batches = _table(6).to_batches(max_chunksize=2)
        reader = pa.RecordBatchReader.from_batches(_table(6).schema, batches)
        total = DuckDBSink().write_stream(reader, str(tmp_path / "s.duckdb"), table_name="p")
        events = get_audit_logger().read_events()
    finally:
        os.environ.pop("BASEBALLPY_HOME", None)
        get_audit_logger.reset()
    assert total == 6
    assert [e.operation for e in events] == ["duckdb_write_stream"]


def test_parquet_sink_atomic_and_partitioned(tmp_path: Path) -> None:
    sink = ParquetSink()
    single = tmp_path / "one.parquet"
    assert sink.write(_table(3), str(single)) == 3
    assert pq.read_table(single).num_rows == 3
    assert list(tmp_path.glob("*.part")) == []

    root = tmp_path / "ds"
    table = _table(4).append_column("season", pa.array([2023, 2023, 2024, 2024], pa.int16()))
    assert sink.write(table, str(root), partition_by=["season"]) == 4
    assert {p.name for p in root.iterdir()} == {"season=2023", "season=2024"}
    assert not [p for p in tmp_path.iterdir() if "staging" in p.name]


def test_parquet_stream_roundtrip(tmp_path: Path) -> None:
    out = tmp_path / "s.parquet"
    reader = pa.RecordBatchReader.from_batches(
        _table(6).schema, _table(6).to_batches(max_chunksize=2)
    )
    assert ParquetSink().write_stream(reader, str(out)) == 6
    assert pq.read_table(out).num_rows == 6


def test_all_sinks_conform_to_protocol_signatures() -> None:
    for cls in (DuckDBSink, ParquetSink, PolarsSink, DltSink):
        assert hasattr(cls, "write") and hasattr(cls, "write_stream")
        for method, first in (("write", "table"), ("write_stream", "reader")):
            params = list(inspect.signature(getattr(cls, method)).parameters)
            assert params[1] == first and params[2] == "destination", (cls, method, params)
            assert inspect.signature(getattr(cls, method)).return_annotation in (int, "int")
    assert isinstance(PolarsSink(), SinkProtocol)
    assert isinstance(DuckDBSink(), SinkProtocol)
    assert isinstance(ParquetSink(), SinkProtocol)


def test_polars_sink_returns_row_count() -> None:
    sink = PolarsSink()
    assert sink.write(_table(3), "ignored") == 3
    assert sink.last is not None and len(sink.last) == 3
