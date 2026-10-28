"""Sync and async callers share one rate limiter and one concurrency bound (spec: concurrency)."""

import asyncio
import threading
import time

import httpx
import respx

from baseballpy.core.config import RateLimitConfig
from baseballpy.core.http import HttpClient

URL = "https://shared.example.com/r"
RATE = 20.0
BURST = 20  # the limiter's bucket holds one second of requests


@respx.mock
def test_sync_threads_and_async_callers_share_one_host_limiter() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"x"))
    client = HttpClient(
        RateLimitConfig(host_rates={"shared.example.com": RATE}, max_concurrency=8), http2=False
    )
    per_caller = 10
    callers = 4  # two sync threads and two async tasks: 40 requests in all

    def sync_caller() -> None:
        for _ in range(per_caller):
            client.get_sync(URL)

    async def async_callers() -> None:
        async def one() -> None:
            for _ in range(per_caller):
                await client.get(URL)

        await asyncio.gather(one(), one())

    try:
        threads = [threading.Thread(target=sync_caller) for _ in range(callers // 2)]
        started = time.perf_counter()
        for thread in threads:
            thread.start()
        asyncio.run(async_callers())
        for thread in threads:
            thread.join()
        elapsed = time.perf_counter() - started
    finally:
        client.close()
    total = per_caller * callers
    # one shared limiter: the requests beyond the initial burst are paced at RATE per second, so
    # 40 requests take at least (40 - 20) / 20 = 1 s; separate limiters per caller would be ~0.5 s
    assert elapsed >= (total - BURST) / RATE * 0.9
    assert len(respx.calls) == total


@respx.mock
def test_concurrency_bound_holds_across_sync_and_async_callers() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.03)
        with lock:
            active -= 1
        return httpx.Response(200, content=b"x")

    respx.get(URL).mock(side_effect=handler)
    bound = 3
    client = HttpClient(
        RateLimitConfig(host_rates={"shared.example.com": 1000.0}, max_concurrency=bound),
        http2=False,
    )

    def sync_caller() -> None:
        for _ in range(6):
            client.get_sync(URL)

    async def async_callers() -> None:
        async def one() -> None:
            for _ in range(6):
                await client.get(URL)

        await asyncio.gather(one(), one(), one())

    try:
        threads = [threading.Thread(target=sync_caller) for _ in range(3)]
        for thread in threads:
            thread.start()
        asyncio.run(async_callers())
        for thread in threads:
            thread.join()
    finally:
        client.close()
    assert 1 <= peak <= bound
