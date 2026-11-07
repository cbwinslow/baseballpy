"""FanGraphs downloads: the website's own JSON routes, slowly, honestly, stopping at a refusal.

Every request goes through ``core/http.py::HttpClient`` (one request every two seconds, one in
flight, no retry). The program says what it is in its user agent. If FanGraphs refuses a request
(HTTP 403, 429 or 503) or answers with a web page where data should be (a bot challenge), the run
stops with :class:`FangraphsBlockedError`: baseballpy does not change its identity, add browser
headers or try again to get past a bot challenge. The files-you-supply route (``inbox/fangraphs``)
is the way to carry on.
"""

import json
import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from baseballpy.core.config import FANGRAPHS_HOST, LakeConfig
from baseballpy.core.http import HttpClient, HttpStatusError, get_http_client
from baseballpy.core.rawlog import RawLog, keep_raw
from baseballpy.core.stores import RawStore
from baseballpy.sources.fangraphs.web import (
    BASE,
    LEADERS_PATH,
    PROJECTIONS_PATH,
    leaderboard_params,
    projection_params,
    user_agent,
)

logger = logging.getLogger(__name__)


class FangraphsBlockedError(RuntimeError):
    """FanGraphs refused a request or sent a web page instead of data."""


def _package_version() -> str:
    try:
        return version("baseballpy")
    except PackageNotFoundError:
        return "0"


class FangraphsWeb:
    """Downloads FanGraphs leaderboards and projections and keeps the raw answers."""

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
        agent = user_agent(_package_version())
        # an honest, identifying user agent for this host only (the client default is generic)
        if hasattr(self._http, "set_header_hook"):
            self._http.set_header_hook(FANGRAPHS_HOST, lambda _method, _url: {"User-Agent": agent})

    def keep(self, dataset: str, name: str, raw: RawLog) -> None:
        """Store the raw answers of one unit as ``raw/fangraphs/<dataset>/<name>`` (when on)."""
        if self._store_raw:
            keep_raw(self._raw, "fangraphs", dataset, name, raw)

    def _get(self, path: str, params: dict[str, str]) -> bytes:
        url = BASE + path
        try:
            result = self._http.get_sync(url, params=params)
        except HttpStatusError as exc:
            raise FangraphsBlockedError(
                f"{url} answered HTTP {exc.status}. baseballpy stops here and does not retry or "
                "change how it identifies itself; use files you supply (inbox/fangraphs) instead."
            ) from exc
        if result.content[:1] == b"<":
            raise FangraphsBlockedError(
                f"{url} sent a web page where data should be (a bot challenge or an error page). "
                "baseballpy stops here; use files you supply (inbox/fangraphs) instead."
            )
        return result.content

    def leaderboard(self, stats: str, season: int, raw: RawLog) -> list[dict[str, Any]]:
        """Every player's row of one season's leaderboard (batting, pitching or fielding)."""
        body = self._get(LEADERS_PATH, leaderboard_params(stats, season))
        raw.add(f"leaders-{stats}", str(season), 0, body)
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError(
                f"FanGraphs leaderboard {stats} {season}: no 'data' list in the answer"
            )
        return list(payload["data"])

    def projections(self, system: str, group: str, raw: RawLog) -> list[dict[str, Any]]:
        """Every projected player of one system and stat group (a bare JSON list)."""
        body = self._get(PROJECTIONS_PATH, projection_params(system, group))
        raw.add(f"projections-{group}", system, 0, body)
        payload = json.loads(body)
        if not isinstance(payload, list):
            raise ValueError(f"FanGraphs projections {system}/{group}: the answer is not a list")
        return payload


__all__ = ["FangraphsBlockedError", "FangraphsWeb"]
