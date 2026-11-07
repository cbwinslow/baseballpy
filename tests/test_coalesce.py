"""Coalescer: one fetch per key, shared across threads, failures not kept."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from baseballpy.core.coalesce import Coalescer


def test_threads_asking_for_one_key_cause_one_fetch() -> None:
    memo: Coalescer[int] = Coalescer(8)
    calls: list[int] = []
    gate = threading.Event()

    def fetch() -> int:
        calls.append(1)
        gate.wait(2)
        return 42

    with ThreadPoolExecutor(6) as pool:
        futures = [pool.submit(memo.get, "k", fetch) for _ in range(6)]
        gate.set()
        assert [f.result() for f in futures] == [42] * 6
    assert len(calls) == 1


def test_only_the_last_few_results_are_kept() -> None:
    memo: Coalescer[int] = Coalescer(2)
    calls: list[str] = []

    def fetch(key: str) -> int:
        calls.append(key)
        return len(calls)

    for key in ("a", "b", "c"):
        memo.get(key, lambda k=key: fetch(k))
    memo.get("c", lambda: fetch("c"))  # still kept
    memo.get("a", lambda: fetch("a"))  # forgotten: fetched again
    assert calls == ["a", "b", "c", "a"]


def test_a_failure_is_raised_to_the_caller_and_not_kept() -> None:
    memo: Coalescer[int] = Coalescer(4)

    def boom() -> int:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        memo.get("k", boom)
    assert memo.get("k", lambda: 7) == 7
