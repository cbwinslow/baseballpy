"""Shared HTTP client: per-host rate limits, bounded concurrency, HTTP/2 pooling, retries.

All network I/O in baseballpy goes through :class:`HttpClient`. Sync and async callers share
the same per-host limiter and in-flight limit and one connection pool because every request
executes on one private event loop owned by the client.
"""

import asyncio
import concurrent.futures
import os
import threading
import time
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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
from baseballpy.core.lazy import lazy_singleton

#: Re-exported so no other module needs to import httpx directly.
TransportError = httpx.TransportError

RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
MAX_RETRY_AFTER_SECONDS = 120.0

T = TypeVar("T")

HTTP_OPERATION = "http_request"
HTTP_SOURCE = "http"


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


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    value = value.strip()
    try:
        return min(max(float(value), 0.0), MAX_RETRY_AFTER_SECONDS)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return min(max(when.timestamp() - time.time(), 0.0), MAX_RETRY_AFTER_SECONDS)


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
    ) -> None:
        self.rate = rate or RateLimitConfig()
        self._http2 = http2
        self._transport = transport
        self._user_agent = user_agent or os.environ.get(USER_AGENT_ENV) or DEFAULT_USER_AGENT
        self._limiters: dict[str, AsyncLimiter] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: httpx.AsyncClient | None = None
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._start_lock = threading.Lock()

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
            return self._loop

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
        """Close the pooled client and stop the private loop."""
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
            limiter = AsyncLimiter(max(rate, 0.001), 1.0)
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
        semaphore = self._semaphore_for(host)
        limiter = self._limiter_for(host)
        req_headers = dict(headers or {})
        if etag:
            req_headers["If-None-Match"] = etag

        def _wait(state: RetryCallState) -> float:
            exc = state.outcome.exception() if state.outcome else None
            if isinstance(exc, RetryableStatus) and exc.retry_after is not None:
                return exc.retry_after
            return float(
                wait_exponential_jitter(multiplier=self.rate.backoff_factor, max=60.0)(state)
            )

        async def _once() -> HttpResult:
            async with semaphore, limiter:
                started = time.perf_counter()
                sent_at = datetime.now(UTC)
                try:
                    resp = await client.get(
                        url,
                        params=params,
                        headers=req_headers,
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
            stop=stop_after_attempt(max(1, self.rate.max_retries)),
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


get_http_client = lazy_singleton(lambda: HttpClient(get_config().rate_limit))

__all__ = [
    "HttpClient",
    "HttpResult",
    "HttpStatusError",
    "RetryableStatus",
    "TransportError",
    "get_http_client",
]
