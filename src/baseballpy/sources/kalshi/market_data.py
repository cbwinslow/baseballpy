"""Kalshi per-market data: trades and hourly candlesticks, fetched per market, stored per close date.

Which route a market needs follows from ``/historical/cutoff`` and the market's own times, never
from a list: trades created before ``trades_created_ts`` live only in the archive, markets settled
before ``market_settled_ts`` have their candles only in the archive, everything newer is live (and
live candles are fetched 100 markets to a call). Every answer is kept as raw JSON, one gzip file per
close date and dataset (a file per request would be about a million files).
"""

import gzip
import json
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from baseballpy.core.http import HttpClient
from baseballpy.sources.kalshi.endpoints import (
    BY_NAME,
    CANDLE_MARGIN_SECONDS,
    CANDLE_PERIOD_MINUTES,
    KALSHI_BASE,
    KalshiEndpoint,
)

logger = logging.getLogger(__name__)

#: a cursor that never ends must not loop forever
MAX_PAGES = 10_000
#: the API refuses a candle request over 5,000 periods ("max candlesticks: 5000", HTTP 400); stay below
MAX_CANDLE_PERIODS = 4_500
_CANDLE_GROUPS = ("price", "yes_bid", "yes_ask")


@dataclass(frozen=True)
class Cutoffs:
    """The archive boundaries (``GET /historical/cutoff``); each data type has its own."""

    trades_created: datetime
    market_settled: datetime


@dataclass(frozen=True)
class MarketRow:
    """What the catalog says about one market, enough to choose its routes and windows."""

    ticker: str
    status: str | None
    open_time: datetime | None
    close_time: datetime | None
    settlement_ts: datetime | None

    @property
    def end(self) -> datetime | None:
        """When the market stopped trading: settlement if known, else its close."""
        return self.settlement_ts or self.close_time


class RawLog:
    """Raw answers of one close date, written as a gzip of JSON lines (the body kept verbatim)."""

    def __init__(self) -> None:
        self._lines: list[str] = []
        self._lock = threading.Lock()

    def add(self, route: str, ticker: str, page: int, body: bytes) -> None:
        """Remember one answer; ``body`` is the exact response text (safe from several threads)."""
        record = {"route": route, "ticker": ticker, "page": page, "body": body.decode("utf-8")}
        line = json.dumps(record, separators=(",", ":"))
        with self._lock:
            self._lines.append(line)

    def __len__(self) -> int:
        return len(self._lines)

    def to_bytes(self) -> bytes:
        """The whole log as gzip bytes (``mtime`` fixed, so equal logs have equal bytes)."""
        with self._lock:
            lines = sorted(self._lines)  # threads add in any order; the file must not depend on it
        return gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0)


def _parse_time(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


def flatten_candle(ticker: str, candle: dict[str, Any]) -> dict[str, Any]:
    """One candlestick as a flat record: ``price_open``, ``yes_bid_close``, ... plus the ticker.

    The answer nests ``price``, ``yes_bid`` and ``yes_ask`` objects; every key found is kept (a new
    group would be flattened the same way), and the period end becomes an ISO time.
    """
    row: dict[str, Any] = {"ticker": ticker}
    for key, value in candle.items():
        if key == "end_period_ts":
            row[key] = datetime.fromtimestamp(int(value), UTC).isoformat()
        elif isinstance(value, dict):
            row.update({f"{key}_{inner}": v for inner, v in value.items()})
        else:
            row[key] = value
    return row


class KalshiMarketData:
    """Fetches trades and candlesticks per market through the shared client."""

    def __init__(self, http: HttpClient) -> None:
        self._http = http
        self._cutoffs: Cutoffs | None = None

    def _get(self, url: str, params: dict[str, str]) -> tuple[bytes, dict[str, Any]]:
        result = self._http.get_sync(url, params=params)
        payload = result.json()
        if not isinstance(payload, dict):
            raise ValueError(f"kalshi {url}: expected a JSON object")
        return result.content, payload

    def cutoffs(self) -> Cutoffs:
        """The archive boundaries, fetched once per extractor."""
        if self._cutoffs is None:
            _, payload = self._get(KALSHI_BASE + "/historical/cutoff", {})
            self._cutoffs = Cutoffs(
                trades_created=_parse_time(payload["trades_created_ts"]),
                market_settled=_parse_time(payload["market_settled_ts"]),
            )
        return self._cutoffs

    # ------------------------------------------------------------------ routing (data, not lists)
    def trade_routes(self, market: MarketRow) -> list[KalshiEndpoint]:
        """Archived only, live only, or both: from the market's open and end against the cutoff."""
        cutoff = self.cutoffs().trades_created
        started = market.open_time
        ended = market.end
        archived = BY_NAME["trades_historical"]
        live = BY_NAME["trades"]
        if ended is not None and ended < cutoff:
            return [archived]
        if started is not None and started >= cutoff:
            return [live]
        return [archived, live]

    def candle_route_is_archived(self, market: MarketRow) -> bool:
        """True when the market settled before the archive boundary (its candles are archived only)."""
        ended = market.end
        return ended is not None and ended < self.cutoffs().market_settled

    # ------------------------------------------------------------------ trades
    def trades(self, market: MarketRow, raw: RawLog) -> list[dict[str, Any]]:
        """Every trade of one market (both routes when needed), de-duplicated by ``trade_id``."""
        seen: dict[str, dict[str, Any]] = {}
        for endpoint in self.trade_routes(market):
            cursor = ""
            for page in range(MAX_PAGES):
                params = {"ticker": market.ticker, "limit": str(endpoint.page_limit)}
                if cursor:
                    params["cursor"] = cursor
                body, payload = self._get(KALSHI_BASE + endpoint.path, params)
                raw.add(endpoint.name, market.ticker, page, body)
                for trade in payload[endpoint.records]:
                    seen.setdefault(str(trade["trade_id"]), trade)
                cursor = str(payload.get("cursor") or "")
                if not cursor:
                    break
            else:
                raise RuntimeError(f"kalshi trades {market.ticker}: more than {MAX_PAGES} pages")
        return list(seen.values())

    # ------------------------------------------------------------------ candlesticks
    @staticmethod
    def _window(markets: Iterable[MarketRow], now: datetime) -> tuple[int, int]:
        starts = [m.open_time for m in markets if m.open_time is not None]
        ends = [m.end or now for m in markets]
        start = min(starts) if starts else now
        return int(start.timestamp()), int(max(ends).timestamp()) + CANDLE_MARGIN_SECONDS

    @staticmethod
    def _windows(start: int, end: int, markets: int) -> list[tuple[int, int]]:
        """Time windows of at most ``MAX_CANDLE_PERIODS`` candles in total (all markets of a call)."""
        step = max(1, MAX_CANDLE_PERIODS // markets) * CANDLE_PERIOD_MINUTES * 60
        edges = list(range(start, end, step)) or [start]
        return [(a, min(a + step, end)) for a in edges]

    def candles_archived(
        self, market: MarketRow, raw: RawLog, now: datetime
    ) -> list[dict[str, Any]]:
        """Hourly candles of one archived market, over its own life (long lives take several calls)."""
        endpoint = BY_NAME["candlesticks_historical"]
        start, end = self._window([market], now)
        rows: dict[str, dict[str, Any]] = {}
        for page, (a, b) in enumerate(self._windows(start, end, 1)):
            params = {
                "start_ts": str(a),
                "end_ts": str(b),
                "period_interval": str(CANDLE_PERIOD_MINUTES),
            }
            url = KALSHI_BASE + endpoint.path.format(ticker=market.ticker)
            body, payload = self._get(url, params)
            raw.add(endpoint.name, market.ticker, page, body)
            for candle in payload[endpoint.records]:
                row = flatten_candle(market.ticker, candle)
                rows[row["end_period_ts"]] = row
        return list(rows.values())

    def candles_live(
        self, markets: Sequence[MarketRow], raw: RawLog, now: datetime
    ) -> list[dict[str, Any]]:
        """Hourly candles of up to ``batch_size`` live markets per call (one call per time window)."""
        endpoint = BY_NAME["candlesticks"]
        if len(markets) > endpoint.batch_size:
            raise ValueError(f"at most {endpoint.batch_size} markets per call, got {len(markets)}")
        start, end = self._window(markets, now)
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for page, (a, b) in enumerate(self._windows(start, end, len(markets))):
            params = {
                "market_tickers": ",".join(m.ticker for m in markets),
                "start_ts": str(a),
                "end_ts": str(b),
                "period_interval": str(CANDLE_PERIOD_MINUTES),
            }
            body, payload = self._get(KALSHI_BASE + endpoint.path, params)
            raw.add(endpoint.name, markets[0].ticker, page, body)
            for market in payload[endpoint.records]:
                ticker = str(market["market_ticker"])
                for candle in market.get("candlesticks", []):
                    row = flatten_candle(ticker, candle)
                    rows[(ticker, row["end_period_ts"])] = row
        return list(rows.values())


Clock = Callable[[], datetime]

__all__ = [
    "MAX_CANDLE_PERIODS",
    "MAX_PAGES",
    "Clock",
    "Cutoffs",
    "KalshiMarketData",
    "MarketRow",
    "RawLog",
    "flatten_candle",
]
