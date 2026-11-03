"""Retrosheet parsing: the default worker count, the shared process pool and its bounded window."""

from concurrent.futures import Future
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from baseballpy.core import config
from baseballpy.core.config import LakeConfig
from baseballpy.sources.retrosheet import pool


def _game(game_id: str) -> bytes:
    year = game_id[3:7]
    return (
        f"id,{game_id}\n"
        f"info,date,{year}/04/01\n"
        "info,hometeam,BOS\n"
        "info,visteam,BAL\n"
        "start,play01,Batter One,0,1,4\n"
        "start,pitch01,Pitcher One,1,1,1\n"
        "play,1,0,play01,00,,S\n"
        "data,er,pitch01,0\n"
    ).encode()


def _files(tmp_path: Path, count: int) -> list[Path]:
    paths = []
    for i in range(count):
        path = tmp_path / f"2024T{i:02d}.EVA"
        path.write_bytes(_game(f"T{i:02d}2024040{i % 9 + 1}"))
        paths.append(path)
    return paths


@pytest.fixture(autouse=True)
def _clean_pools() -> Any:
    pool.shutdown_pools()
    yield
    pool.shutdown_pools()


def test_default_parse_workers_follow_the_cpu_count_with_a_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BASEBALLPY_PARSE_WORKERS", raising=False)
    for cpus, expected in ((1, 1), (4, 4), (32, 32), (56, 32)):
        monkeypatch.setattr(config.os, "cpu_count", lambda cpus=cpus: cpus)
        assert LakeConfig().parse_workers == expected
    monkeypatch.setattr(config.os, "cpu_count", lambda: None)
    assert LakeConfig().parse_workers == 1
    monkeypatch.setattr(config.os, "cpu_count", lambda: 56)
    assert LakeConfig(parse_workers=0).parse_workers == 0, "an explicit value, even 0, wins"
    assert LakeConfig(parse_workers=3).parse_workers == 3


def test_pooled_parse_equals_in_process_parse_in_order_and_reuses_the_pool(
    tmp_path: Path,
) -> None:
    paths = _files(tmp_path, 6)
    serial = list(pool.parse_stream("events", paths, 2024, 0))
    first = list(pool.parse_stream("events", paths, 2024, 2))
    second = list(pool.parse_stream("events", paths[:3], 2024, 2))
    assert len(first) == 6 and all(a.equals(b) for a, b in zip(serial, first, strict=True))  # type: ignore[union-attr]
    assert all(a.equals(b) for a, b in zip(serial[:3], second, strict=True))  # type: ignore[union-attr]
    assert list(pool._pools) == [2], "both streams used the one pool of two workers"


class _FakePool:
    """Runs submitted work at once in this process and counts what was submitted."""

    def __init__(self) -> None:
        self.submitted = 0

    def submit(self, fn: Any, *args: Any) -> "Future[Any]":
        self.submitted += 1
        future: Future[Any] = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as exc:
            future.set_exception(exc)
        return future


def test_a_stream_never_runs_more_than_two_times_workers_ahead(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakePool()
    monkeypatch.setattr(pool, "shared_pool", lambda workers: fake)
    monkeypatch.setattr(pool, "parse_one", lambda kind, path, year: pa.table({"p": [path]}))
    paths = _files(tmp_path, 20)
    consumed = 0
    for _ in pool.parse_stream("events", paths, 2024, 3):
        consumed += 1
        assert fake.submitted - consumed <= pool.WINDOW_PER_WORKER * 3
    assert consumed == 20 and fake.submitted == 20


def test_a_failing_file_raises_and_cancels_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakePool()
    monkeypatch.setattr(pool, "shared_pool", lambda workers: fake)

    def parse(kind: str, path: str, year: int | None) -> pa.Table:
        if path.endswith("T01.EVA"):
            raise ValueError("cannot parse")
        return pa.table({"p": [path]})

    monkeypatch.setattr(pool, "parse_one", parse)
    stream = pool.parse_stream("events", _files(tmp_path, 40), 2024, 2)
    next(stream)
    with pytest.raises(ValueError, match="cannot parse"):
        next(stream)
    assert fake.submitted <= 2 * pool.WINDOW_PER_WORKER + 2, "queued files were never submitted"
