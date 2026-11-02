"""Sync and async callers share one rate limiter and one concurrency bound (spec: concurrency)."""

import asyncio
import threading
import time
from pathlib import Path

import httpx
import pytest
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


@respx.mock
def test_a_per_call_timeout_overrides_the_configured_one() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, content=b"x"))
    client = HttpClient(RateLimitConfig(timeout_seconds=30.0), http2=False)
    try:
        client.get_sync(URL)
        client.get_sync(URL, timeout=180.0)
    finally:
        client.close()
    default, override = (call.request.extensions["timeout"] for call in route.calls)
    assert default["read"] == 30.0
    assert override["read"] == 180.0


@respx.mock
def test_hydrate_batches_execute_concurrently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from baseballpy.core.config import LakeConfig, RateLimitConfig
    from baseballpy.core.http import HttpClient
    from baseballpy.sources.mlb_api import generic
    from baseballpy.sources.mlb_api.endpoints import BY_NAME, Request
    from baseballpy.sources.mlb_api.generic import MlbEndpointExtractor

    active = 0
    peak = 0
    lock = threading.Lock()

    async def people_handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.03)
        with lock:
            active -= 1
        return httpx.Response(200, json={"people": [{"id": 1, "stats": [{"splits": []}]}]})

    respx.get("https://statsapi.mlb.com/api/v1/people").mock(side_effect=people_handler)
    respx.get("https://statsapi.mlb.com/api/v1/sports/1/players").mock(
        return_value=httpx.Response(200, json={"people": [{"id": i} for i in range(1, 21)]})
    )

    monkeypatch.setattr(generic, "POOL_BATCH", 2)
    rate_cfg = RateLimitConfig(max_concurrency=4, statsapi_rps=100.0)
    http_client = HttpClient(rate_cfg, http2=False)
    lake = LakeConfig(home=tmp_path)
    extractor = MlbEndpointExtractor(cache_config=lake, http=http_client)

    ep = BY_NAME["stats_stat_splits_hitting"]
    req = Request(
        "stats_stat_splits_hitting_2024_sport1",
        "v1/stats",
        {"stats": "statSplits", "group": "hitting", "season": "2024", "sportIds": "1"},
        2024,
    )
    pages = extractor._pool_pages_by_hydrate(ep, req)
    http_client.close()
    assert len(pages) == 10
    assert peak >= 2, f"expected concurrent execution across batches, got peak={peak}"
    assert peak <= 4, f"expected concurrency to be bounded by max_concurrency 4, got peak={peak}"
