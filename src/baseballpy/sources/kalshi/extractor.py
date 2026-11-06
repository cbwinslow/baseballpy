"""Kalshi extraction: public GETs through the shared client, every answer kept as raw bytes.

All requests use ``core/http.py::HttpClient`` (rate cap, in-flight cap, retries, audit log). One
call fetches every page of one route for one series; the raw JSON of each page is stored with its
sha256 before anything is typed, so a parsing fix never needs the network.
"""

import logging
from collections.abc import Callable
from typing import Any

from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.stores import RawStore
from baseballpy.sources.kalshi.endpoints import (
    BY_NAME,
    ENDPOINTS,
    KALSHI_BASE,
    MLB_SCOPE,
    KalshiEndpoint,
)
from baseballpy.sources.kalshi.raw import RawLog, keep_raw
from baseballpy.sources.kalshi.signing import sign_with_environment

logger = logging.getLogger(__name__)

#: the series list needs no series ticker; a bounded page count guards against a cursor that never ends
MAX_PAGES = 10_000


class KalshiExtractor:
    """Downloads Kalshi catalog pages and keeps the raw bytes."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        http: HttpClient | None = None,
        *,
        store_raw: bool = True,
    ) -> None:
        self._config = cache_config or LakeConfig()
        self._http = http or get_http_client()
        self._raw = RawStore(self._config)
        self._store_raw = store_raw and self._config.enabled
        # optional: a signed account has a higher, documented read budget
        self.signed = sign_with_environment(self._http)

    def _get(
        self, endpoint: KalshiEndpoint, params: dict[str, str]
    ) -> tuple[bytes, dict[str, Any]]:
        result = self._http.get_sync(KALSHI_BASE + endpoint.path, params=params)
        payload = result.json()
        if not isinstance(payload, dict) or not isinstance(payload.get(endpoint.records), list):
            raise ValueError(f"kalshi {endpoint.path}: no {endpoint.records!r} list in the answer")
        return result.content, payload

    def keep(self, dataset: str, name: str, raw: RawLog) -> None:
        """Store the raw answers of one unit as ``raw/kalshi/<dataset>/<name>`` (when storing is on)."""
        if self._store_raw:
            keep_raw(self._raw, dataset, name, raw)

    def series(self) -> list[dict[str, Any]]:
        """Every in-scope series record (the series list, filtered by the MLB scope rule)."""
        endpoint = BY_NAME["series"]
        data, payload = self._get(endpoint, dict(endpoint.params))
        raw = RawLog()
        raw.add(endpoint.name, "-", 0, data)
        self.keep("series", "series-all.jsonl.gz", raw)
        return [r for r in payload[endpoint.records] if MLB_SCOPE.includes(r)]

    def records(
        self, endpoint: KalshiEndpoint, series_ticker: str, raw: RawLog
    ) -> list[dict[str, Any]]:
        """Every record of one route for one series, following the cursor to the end."""
        out: list[dict[str, Any]] = []
        cursor = ""
        for page in range(MAX_PAGES):
            params = {"series_ticker": series_ticker, "limit": str(endpoint.page_limit)}
            if cursor:
                params["cursor"] = cursor
            data, payload = self._get(endpoint, params)
            raw.add(endpoint.name, series_ticker, page, data)
            out.extend(payload[endpoint.records])
            cursor = str(payload.get("cursor") or "")
            if not cursor:
                return out
        raise RuntimeError(f"kalshi {endpoint.path} {series_ticker}: more than {MAX_PAGES} pages")


def route_names(dataset: str) -> list[str]:
    """Names of the routes that feed ``dataset`` (the table is the only list)."""
    return [e.name for e in ENDPOINTS if e.dataset == dataset and e.fan_out == "series"]


Fetcher = Callable[[KalshiEndpoint, str], list[dict[str, Any]]]

__all__ = ["MAX_PAGES", "Fetcher", "KalshiExtractor", "route_names"]
