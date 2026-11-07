"""Polymarket extraction: public GETs through the shared client, every answer kept as raw bytes.

All requests use ``core/http.py::HttpClient`` (per-host rate cap, in-flight cap, retries, audit
log). The raw JSON of each answer goes into a :class:`~baseballpy.core.rawlog.RawLog` with its
sha256 before anything is typed, so a parsing fix never needs the network.
"""

import logging
from collections.abc import Iterator
from typing import Any

from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.rawlog import RawLog, keep_raw
from baseballpy.core.stores import RawStore
from baseballpy.sources.polymarket.endpoints import (
    EVENTS,
    PRICE_FIDELITY_MINUTES,
    PRICES_HISTORY,
    SPORT_SLUG,
    SPORTS,
)
from baseballpy.sources.polymarket.records import price_row

logger = logging.getLogger(__name__)

#: guards against a cursor that never ends (11,653 MLB events are 117 pages of 100)
MAX_PAGES = 10_000


class PolymarketExtractor:
    """Downloads Polymarket catalog pages and price history and keeps the raw bytes."""

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

    def keep(self, dataset: str, name: str, raw: RawLog) -> None:
        """Store the raw answers of one unit as ``raw/polymarket/<dataset>/<name>`` (when on)."""
        if self._store_raw:
            keep_raw(self._raw, "polymarket", dataset, name, raw)

    def sport_tag_id(self, raw: RawLog | None = None) -> int:
        """The tag id of the in-scope sport, read from ``/sports`` (never hard-coded)."""
        result = self._http.get_sync(SPORTS.host_base + SPORTS.path)
        if raw is not None:
            raw.add(SPORTS.name, "-", 0, result.content)
        sports = result.json()
        if not isinstance(sports, list):
            raise ValueError("polymarket /sports: the answer is not a list")
        for sport in sports:
            if sport.get("sport") == SPORT_SLUG and sport.get("primaryTagId") is not None:
                return int(sport["primaryTagId"])
        raise ValueError(f"polymarket /sports lists no sport {SPORT_SLUG!r} with a tag id")

    def events(self, tag_id: int, raw: RawLog) -> Iterator[list[dict[str, Any]]]:
        """Pages of events (each carrying its markets) of one tag, following the keyset cursor."""
        cursor = ""
        for page in range(MAX_PAGES):
            params = {"tag_id": str(tag_id), "limit": str(EVENTS.page_limit)}
            if cursor:
                params[EVENTS.cursor_param] = cursor
            result = self._http.get_sync(EVENTS.host_base + EVENTS.path, params=params)
            raw.add(EVENTS.name, str(tag_id), page, result.content)
            payload = result.json()
            if not isinstance(payload, dict) or not isinstance(payload.get(EVENTS.records), list):
                raise ValueError(f"polymarket {EVENTS.path}: no {EVENTS.records!r} list")
            yield payload[EVENTS.records]
            cursor = str(payload.get(EVENTS.cursor_key) or "")
            if not cursor or not payload[EVENTS.records]:
                return
        raise RuntimeError(f"polymarket {EVENTS.path}: more than {MAX_PAGES} pages")

    def price_history(
        self, token_id: str, start_ts: int, end_ts: int, raw: RawLog, window: int = 0
    ) -> list[dict[str, Any]]:
        """Hourly price points of one outcome token inside one window (at most 15 days)."""
        params = {
            "market": token_id,
            "startTs": str(start_ts),
            "endTs": str(end_ts),
            "fidelity": str(PRICE_FIDELITY_MINUTES),
        }
        result = self._http.get_sync(PRICES_HISTORY.host_base + PRICES_HISTORY.path, params=params)
        raw.add(PRICES_HISTORY.name, token_id, window, result.content)
        payload = result.json()
        if not isinstance(payload, dict) or not isinstance(
            payload.get(PRICES_HISTORY.records), list
        ):
            raise ValueError(f"polymarket {PRICES_HISTORY.path}: no 'history' list for {token_id}")
        return [price_row(token_id, point) for point in payload[PRICES_HISTORY.records]]


__all__ = ["MAX_PAGES", "PolymarketExtractor"]
