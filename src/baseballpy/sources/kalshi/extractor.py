"""Kalshi extraction: public GETs through the shared client, every answer kept as raw bytes.

All requests use ``core/http.py::HttpClient`` (rate cap, in-flight cap, retries, audit log). One
call fetches every page of one route for one series; the raw JSON of each page is stored with its
sha256 before anything is typed, so a parsing fix never needs the network.
"""

import logging
import re
from collections.abc import Callable
from typing import Any

from baseballpy.core.config import KALSHI_HOST, LakeConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.stores import RawStore
from baseballpy.sources.kalshi.endpoints import (
    BY_NAME,
    ENDPOINTS,
    KALSHI_BASE,
    MLB_SCOPE,
    KalshiEndpoint,
)
from baseballpy.sources.kalshi.signing import KalshiSigner

logger = logging.getLogger(__name__)

#: the series list needs no series ticker; a bounded page count guards against a cursor that never ends
MAX_PAGES = 10_000
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


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
        signer = KalshiSigner.from_config()
        if signer is not None:  # optional: a signed account has a higher, documented read budget
            self._http.set_header_hook(KALSHI_HOST, signer.headers)
        self.signed = signer is not None

    def _get(
        self, endpoint: KalshiEndpoint, params: dict[str, str]
    ) -> tuple[bytes, dict[str, Any]]:
        result = self._http.get_sync(KALSHI_BASE + endpoint.path, params=params)
        payload = result.json()
        if not isinstance(payload, dict) or not isinstance(payload.get(endpoint.records), list):
            raise ValueError(f"kalshi {endpoint.path}: no {endpoint.records!r} list in the answer")
        return result.content, payload

    def _keep(
        self, endpoint: KalshiEndpoint, label: str, page: int, data: bytes, rows: int
    ) -> None:
        if self._store_raw:
            name = _SAFE.sub("_", f"{label}-p{page:05d}.json")
            self._raw.put("kalshi", endpoint.dataset, name, data, records=rows,
                          extra={"route": endpoint.name})  # fmt: skip

    def series(self) -> list[dict[str, Any]]:
        """Every in-scope series record (the series list, filtered by the MLB scope rule)."""
        endpoint = BY_NAME["series"]
        data, payload = self._get(endpoint, dict(endpoint.params))
        rows = payload[endpoint.records]
        self._keep(endpoint, "series", 0, data, len(rows))
        return [r for r in rows if MLB_SCOPE.includes(r)]

    def records(self, endpoint: KalshiEndpoint, series_ticker: str) -> list[dict[str, Any]]:
        """Every record of one route for one series, following the cursor to the end."""
        out: list[dict[str, Any]] = []
        cursor = ""
        for page in range(MAX_PAGES):
            params = {"series_ticker": series_ticker, "limit": str(endpoint.page_limit)}
            if cursor:
                params["cursor"] = cursor
            data, payload = self._get(endpoint, params)
            rows = payload[endpoint.records]
            self._keep(endpoint, f"{endpoint.name}-{series_ticker}", page, data, len(rows))
            out.extend(rows)
            cursor = str(payload.get("cursor") or "")
            if not cursor:
                return out
        raise RuntimeError(f"kalshi {endpoint.path} {series_ticker}: more than {MAX_PAGES} pages")


def route_names(dataset: str) -> list[str]:
    """Names of the routes that feed ``dataset`` (the table is the only list)."""
    return [e.name for e in ENDPOINTS if e.dataset == dataset and e.fan_out == "series"]


Fetcher = Callable[[KalshiEndpoint, str], list[dict[str, Any]]]

__all__ = ["MAX_PAGES", "Fetcher", "KalshiExtractor", "route_names"]
