"""Shared HTTP client: per-host rate limits, bounded concurrency, HTTP/2 pooling, retries.

All network I/O in baseballpy goes through :class:`HttpClient`. Sync and async callers share
the same per-host limiter and in-flight limit and one connection pool because every request
executes on one private event loop owned by the client.
"""

import asyncio
import concurrent.futures
import hashlib
import math
import os
import threading
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from aiolimiter import AsyncLimiter
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from baseballpy.core.audit import AuditEvent, default_audit_logger
from baseballpy.core.config import RateLimitConfig, get_config
from baseballpy.core.hostlock import claim_host, release_all
from baseballpy.core.lazy import lazy_singleton

#: Re-exported so no other module needs to import httpx directly.
TransportError = httpx.TransportError

RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
#: the statuses with which a host asks its clients to slow down: the whole host pauses, not one request
SLOWDOWN_STATUSES = frozenset({429, 503})
MAX_RETRY_AFTER_SECONDS = 120.0

T = TypeVar("T")

HTTP_OPERATION = "http_request"
HTTP_SOURCE = "http"


#: wall-clock seconds at perf_counter zero: the wall clock alone ticks only every ~15 ms on Windows, which made
#: back-to-back requests look as if they overlapped in the audit log
_CLOCK_OFFSET = time.time() - time.perf_counter()


def _now() -> datetime:
    """The current UTC time with the resolution of ``perf_counter`` (never earlier than a request that ended)."""
    return datetime.fromtimestamp(_CLOCK_OFFSET + time.perf_counter(), UTC)


def _audit_attempt(
    url: str, sent_at: datetime, elapsed: float, status: int | None, outcome: str, error: str | None
) -> None:
    """One audit event per real network attempt (ADR 67).

    ``started_at_utc`` is the moment the request was really sent (after the rate limiter and the
    in-flight gate), so ``baseballpy audit speed`` can count requests per second and requests in
    flight; the query string is left out to keep the log small. ``RETRY`` marks an attempt that
    raised an error the client retries (the last attempt of a failing request is also ``RETRY``;
    the caller's own event carries the final failure).
    """
    parts = urlparse(url)
    ended = sent_at.timestamp() + elapsed
    default_audit_logger.log(
        AuditEvent(
            timestamp_utc=datetime.fromtimestamp(ended, UTC).isoformat(),
            started_at_utc=sent_at.isoformat(),
            completed_at_utc=datetime.fromtimestamp(ended, UTC).isoformat(),
            operation=HTTP_OPERATION,
            source=HTTP_SOURCE,
            status=outcome,
            duration_seconds=round(elapsed, 4),
            endpoint=f"{parts.scheme}://{parts.netloc}{parts.path}",
            error=error
            if error is not None
            else (f"HTTP {status}" if status and status >= 400 else None),
        )
    )


class RetryableStatus(Exception):  # noqa: N818 - internal control-flow signal
    """Raised internally for HTTP statuses that should be retried."""

    def __init__(self, status: int, retry_after: float | None = None) -> None:
        super().__init__(f"retryable HTTP status {status}")
        self.status = status
        self.retry_after = retry_after


class HttpStatusError(Exception):
    """Raised for non-retryable (or exhausted-retry) unexpected HTTP statuses."""

    def __init__(self, url: str, status: int) -> None:
        super().__init__(f"HTTP {status} for {url}")
        self.url = url
        self.status = status


@dataclass(frozen=True)
class HttpResult:
    """Outcome of a GET request."""

    url: str
    status: int
    content: bytes
    etag: str | None
    not_modified: bool
    elapsed_seconds: float

    def json(self) -> Any:
        """Decode the body as JSON."""
        import msgspec

        return msgspec.json.decode(self.content)


@dataclass(frozen=True)
class DownloadResult:
    """Outcome of a streamed download: the file (or none), its size and sha256, and what the server said."""

    url: str
    status: int
    path: Path | None
    size: int
    sha256: str
    etag: str | None
    content_length: int | None
    elapsed_seconds: float
    too_large: bool = False


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        pass
    else:
        if math.isnan(
            seconds
        ):  # "nan" parses as a float, escapes min/max and would crash the sleep
            return None
        return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(
            tzinfo=UTC
        )  # a date without a zone is GMT; naive .timestamp() uses the local clock
    try:
        stamp = when.timestamp()
    except (OverflowError, OSError, ValueError):
        return None
    return min(max(stamp - time.time(), 0.0), MAX_RETRY_AFTER_SECONDS)


#: What pybaseball sends (the ``requests`` default). ``statsapi.mlb.com`` began answering HTTP 403
#: to the earlier ``baseballpy (+https://github...)`` agent on 2026-10-28 (ADR 40).
DEFAULT_USER_AGENT = "python-requests/2.32.3"
USER_AGENT_ENV = "BASEBALLPY_USER_AGENT"


class HttpClient:
    """Rate-limited, retrying, HTTP/2-capable client shared by sync and async callers."""

    def __init__(
        self,
        rate: RateLimitConfig | None = None,
        *,
        http2: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str | None = None,
        lock_dir: Path | None = None,
    ) -> None:
        self.rate = rate or RateLimitConfig()
        #: folder of the per-host claims (``None``: no claim, as in tests with their own client)
        self._lock_dir = lock_dir
        self._http2 = http2
        self._transport = transport
        self._user_agent = user_agent or os.environ.get(USER_AGENT_ENV) or DEFAULT_USER_AGENT
        self._limiters: dict[str, AsyncLimiter] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: httpx.AsyncClient | None = None
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._host_blocked_until: dict[
            str, float
        ] = {}  # host -> time.monotonic() it may be asked again
        self._start_lock = threading.Lock()
        self._header_hooks: dict[str, Callable[[str, str], Mapping[str, str]]] = {}

    @property
    def user_agent(self) -> str:
        """The User-Agent this client sends."""
        return self._user_agent

    def set_header_hook(self, host: str, hook: Callable[[str, str], Mapping[str, str]]) -> None:
        """Add headers made per attempt for one host: ``hook(method, url)`` (request signing).

        Called inside every attempt, so a retry never reuses a stale signature. The hook's values
        are never logged: the audit log records only URL, status, timing and outcome.
        """
        self._header_hooks[host] = hook

    # ------------------------------------------------------------------ loop plumbing
    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._start_lock:
            if self._loop is None or self._loop.is_closed():
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=self._run_loop, args=(loop,), name="baseballpy-http", daemon=True
                )
                thread.start()
                self._loop, self._thread = loop, thread
                self._client = None
                self._semaphores = {}
                self._limiters = {}
                self._host_blocked_until = {}
            return self._loop

    async def _wait_out_host_pause(self, host: str) -> None:
        """Sleep until the quiet period a host asked for (429, 503) is over; nothing is held while waiting."""
        pause = self._host_blocked_until.get(host, 0.0) - time.monotonic()
        if pause > 0:
            await asyncio.sleep(pause)

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _submit(self, coro: Awaitable[T]) -> "asyncio.Future[T]":
        loop = self._ensure_loop()
        future: concurrent.futures.Future[T] = asyncio.run_coroutine_threadsafe(
            coro,  # type: ignore[arg-type]
            loop,
        )
        return asyncio.wrap_future(future)

    def close(self) -> None:
        """Close the pooled client, stop the private loop and give up the host claims."""
        if self._lock_dir is not None:
            release_all(self._lock_dir)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        if self._client is not None:
            asyncio.run_coroutine_threadsafe(self._client.aclose(), loop).result(timeout=10)
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        loop.close()
        self._loop = None
        self._client = None

    # ------------------------------------------------------------------ rate limits
    def _limiter_for(self, host: str) -> AsyncLimiter:
        limiter = self._limiters.get(host)
        if limiter is None:
            rate = self.rate.host_rates.get(host, self.rate.default_requests_per_second)
            rate = max(rate, 0.001)
            # a bucket holds at least one request: a slow host (0.1/s) is one request per 10 s
            limiter = AsyncLimiter(rate, 1.0) if rate >= 1 else AsyncLimiter(1, 1.0 / rate)
            self._limiters[host] = limiter
        return limiter

    def limit_for(self, host: str) -> int:
        """Most requests of ``host`` in flight at once (``host_concurrency`` or ``max_concurrency``)."""
        return max(1, self.rate.host_concurrency.get(host, self.rate.max_concurrency))

    def _semaphore_for(self, host: str) -> asyncio.Semaphore:
        """One in-flight limit per host, so a slow host cannot hold another host's slots."""
        semaphore = self._semaphores.get(host)
        if semaphore is None:
            semaphore = asyncio.Semaphore(self.limit_for(host))
            self._semaphores[host] = semaphore
        return semaphore

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            widest = max([self.rate.max_concurrency, *self.rate.host_concurrency.values()])
            limits = httpx.Limits(
                max_connections=max(20, 4 * widest), max_keepalive_connections=max(10, 2 * widest)
            )
            self._client = httpx.AsyncClient(
                http2=self._http2,
                limits=limits,
                timeout=self.rate.timeout_seconds,
                follow_redirects=True,
                transport=self._transport,
                headers={"User-Agent": self._user_agent},
            )
        return self._client

    # ------------------------------------------------------------------ requests
    async def _get_on_loop(
        self,
        url: str,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, str] | None,
        etag: str | None,
        allow: tuple[int, ...],
        timeout: float | None = None,
    ) -> HttpResult:
        client = self._ensure_client()
        host = urlparse(url).hostname or ""
        if self._lock_dir is not None and not self.rate.allow_parallel_processes:
            claim_host(self._lock_dir, host)
        semaphore = self._semaphore_for(host)
        limiter = self._limiter_for(host)
        req_headers = dict(headers or {})
        if etag:
            req_headers["If-None-Match"] = etag

        def _wait(state: RetryCallState) -> float:
            exc = state.outcome.exception() if state.outcome else None
            if isinstance(exc, RetryableStatus) and exc.retry_after is not None:
                delay = exc.retry_after
            else:
                delay = float(
                    wait_exponential_jitter(multiplier=self.rate.backoff_factor, max=60.0)(state)
                )
            if isinstance(exc, RetryableStatus) and exc.status in SLOWDOWN_STATUSES:
                # the host asked for a slowdown (429, 503): every request to it waits, not only this one
                # (a one-off 500, 502 or 504 is retried by that request alone)
                self._host_blocked_until[host] = max(
                    self._host_blocked_until.get(host, 0.0), time.monotonic() + delay
                )
            return delay

        async def _once() -> HttpResult:
            await self._wait_out_host_pause(host)
            async with semaphore, limiter:
                # a request that queued for a slot before the host asked for quiet asks again once it has one
                await self._wait_out_host_pause(host)
                started = time.perf_counter()
                sent_at = _now()
                hook = self._header_hooks.get(host)
                attempt_headers = (
                    req_headers if hook is None else {**req_headers, **hook("GET", url)}
                )
                try:
                    resp = await client.get(
                        url,
                        params=params,
                        headers=attempt_headers,
                        timeout=httpx.USE_CLIENT_DEFAULT if timeout is None else timeout,
                    )
                except httpx.TransportError as exc:  # audited, then retried or raised as before
                    _audit_attempt(
                        url,
                        sent_at,
                        time.perf_counter() - started,
                        None,
                        "RETRY",
                        type(exc).__name__,
                    )
                    raise
                # measured before the slot is given back, so the logged end never overlaps the next
                # request that takes the slot (the speed check counts overlaps, ADR 67)
                elapsed = time.perf_counter() - started
            status = resp.status_code
            if status in RETRYABLE_STATUSES and status not in allow:
                _audit_attempt(url, sent_at, elapsed, status, "RETRY", None)
                raise RetryableStatus(status, _parse_retry_after(resp.headers.get("Retry-After")))
            if status == 304 and etag:
                _audit_attempt(url, sent_at, elapsed, status, "SUCCESS", None)
                return HttpResult(url, 304, b"", etag, True, elapsed)
            if status not in allow and not (200 <= status < 300 and 200 in allow):
                _audit_attempt(url, sent_at, elapsed, status, "FAILURE", None)
                raise HttpStatusError(url, status)
            _audit_attempt(url, sent_at, elapsed, status, "SUCCESS", None)
            return HttpResult(url, status, resp.content, resp.headers.get("ETag"), False, elapsed)

        retrying = AsyncRetrying(
            stop=stop_after_attempt(
                max(1, self.rate.host_max_attempts.get(host, self.rate.max_retries))
            ),
            wait=_wait,
            retry=retry_if_exception_type((httpx.TransportError, RetryableStatus)),
            reraise=True,
        )
        try:
            return await retrying(_once)
        except RetryableStatus as exc:
            raise HttpStatusError(url, exc.status) from exc

    async def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        etag: str | None = None,
        allow: tuple[int, ...] = (200,),
        timeout: float | None = None,
    ) -> HttpResult:
        """GET ``url`` (async). Statuses in ``allow`` are returned; others raise.

        ``timeout`` overrides the configured request timeout for this call only.
        """
        return await self._submit(self._get_on_loop(url, params, headers, etag, allow, timeout))

    async def _download_on_loop(
        self,
        url: str,
        dest: Path,
        max_bytes: int | None,
        allow: tuple[int, ...],
        timeout: float | None,
    ) -> DownloadResult:
        client = self._ensure_client()
        host = urlparse(url).hostname or ""
        if self._lock_dir is not None and not self.rate.allow_parallel_processes:
            claim_host(self._lock_dir, host)
        part = dest.with_name(dest.name + ".part")
        digest = hashlib.sha256()
        size = 0
        await self._wait_out_host_pause(host)
        async with self._semaphore_for(host), self._limiter_for(host):
            started = time.perf_counter()
            sent_at = _now()
            hook = self._header_hooks.get(host)
            headers = {} if hook is None else dict(hook("GET", url))
            try:
                async with client.stream(
                    "GET",
                    url,
                    headers=headers,
                    timeout=httpx.USE_CLIENT_DEFAULT if timeout is None else timeout,
                ) as resp:
                    status = resp.status_code
                    etag = resp.headers.get("ETag")
                    raw_length = resp.headers.get("Content-Length")
                    length = int(raw_length) if raw_length and raw_length.isdigit() else None
                    if status not in allow:
                        _audit_attempt(
                            url, sent_at, time.perf_counter() - started, status, "FAILURE", None
                        )
                        raise HttpStatusError(url, status)
                    if status != 200:
                        _audit_attempt(
                            url, sent_at, time.perf_counter() - started, status, "SUCCESS", None
                        )
                        return DownloadResult(
                            url, status, None, 0, "", etag, length, time.perf_counter() - started
                        )
                    if max_bytes is not None and length is not None and length > max_bytes:
                        _audit_attempt(
                            url, sent_at, time.perf_counter() - started, status, "SUCCESS", None
                        )
                        return DownloadResult(
                            url,
                            status,
                            None,
                            0,
                            "",
                            etag,
                            length,
                            time.perf_counter() - started,
                            True,
                        )
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    too_large = False
                    with part.open("wb") as handle:
                        async for chunk in resp.aiter_bytes(1024 * 1024):
                            size += len(chunk)
                            if max_bytes is not None and size > max_bytes:
                                too_large = True
                                break
                            handle.write(chunk)
                            digest.update(chunk)
            except httpx.TransportError as exc:
                part.unlink(missing_ok=True)
                _audit_attempt(
                    url, sent_at, time.perf_counter() - started, None, "RETRY", type(exc).__name__
                )
                raise
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            elapsed = time.perf_counter() - started
        if too_large:
            part.unlink(missing_ok=True)
            _audit_attempt(url, sent_at, elapsed, 200, "SUCCESS", None)
            return DownloadResult(url, 200, None, 0, "", etag, length, elapsed, True)
        os.replace(part, dest)
        _audit_attempt(url, sent_at, elapsed, 200, "SUCCESS", None)
        return DownloadResult(url, 200, dest, size, digest.hexdigest(), etag, length, elapsed)

    def download_sync(
        self,
        url: str,
        dest: Path,
        *,
        max_bytes: int | None = None,
        allow: tuple[int, ...] = (200,),
        timeout: float | None = None,
    ) -> DownloadResult:
        """Stream ``url`` to ``dest`` (see :class:`DownloadResult`); no retries, a refusal is the caller's decision.

        Uses the same per-host rate limit, in-flight limit, host claim and audit log as ``get``. The body is written
        to ``<dest>.part`` and renamed when complete; a ``Content-Length`` (or a body) above ``max_bytes`` is not read.
        """
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._download_on_loop(url, dest, max_bytes, allow, timeout), loop
        )
        return future.result()

    def get_sync(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        etag: str | None = None,
        allow: tuple[int, ...] = (200,),
        timeout: float | None = None,
    ) -> HttpResult:
        """Synchronous GET sharing the same limiter, semaphore and pool as async callers."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(
            self._get_on_loop(url, params, headers, etag, allow, timeout), loop
        )
        return future.result()


get_http_client = lazy_singleton(
    lambda: HttpClient(get_config().rate_limit, lock_dir=get_config().lake.locks_root)
)

__all__ = [
    "HttpClient",
    "HttpResult",
    "HttpStatusError",
    "DownloadResult",
    "RetryableStatus",
    "TransportError",
    "get_http_client",
]
