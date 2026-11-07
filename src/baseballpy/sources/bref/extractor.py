"""Baseball-Reference extraction: the published WAR files, a handful of requests, raw bytes kept.

All requests use ``core/http.py::HttpClient`` (rate cap of 6 a minute, one in flight, no retry after
a refusal). A file downloaded in the last 12 hours is read from ``raw/`` instead of asked for again.
A refusal or a web page instead of the data stops the run: Sports Reference jails a session for up
to a day when it is asked too often, and asking again only makes that longer.
"""

import logging
from datetime import UTC, datetime

from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, HttpStatusError, get_http_client
from baseballpy.core.stores import RawStore
from baseballpy.core.upstream import response_fingerprint
from baseballpy.sources.bref.endpoints import BREF_BASE, FRESH_SECONDS, BrefFile

logger = logging.getLogger(__name__)


class BrefBlockedError(RuntimeError):
    """Baseball-Reference refused the request or sent a web page instead of the file."""


class BrefExtractor:
    """Downloads the WAR files and keeps the raw bytes."""

    def __init__(
        self, cache_config: LakeConfig | None = None, http: HttpClient | None = None
    ) -> None:
        self._config = cache_config or LakeConfig()
        self._http = http or get_http_client()
        self._raw = RawStore(self._config)

    def _recent(self, file: BrefFile) -> bool:
        entry = self._config.dataset_manifest("bref", file.dataset, "raw").get_chunk(file.name)
        if (
            not entry
            or entry.get("status") != "COMPLETED"
            or not self._raw.exists("bref", file.dataset, file.name)
        ):
            return False
        fetched = datetime.fromisoformat(
            str(entry.get("fetched_at") or "1970-01-01T00:00:00+00:00")
        )
        return (datetime.now(UTC) - fetched).total_seconds() < FRESH_SECONDS

    def fetch(self, file: BrefFile, *, refresh: bool = False) -> bytes:
        """The bytes of one WAR file: from ``raw/`` when recent, else downloaded once and kept."""
        if not refresh and self._recent(file):
            return self._raw.get("bref", file.dataset, file.name)
        url = BREF_BASE + file.path
        try:
            result = self._http.get_sync(url)
        except HttpStatusError as exc:
            raise BrefBlockedError(
                f"{url} answered HTTP {exc.status}. Do not ask again for 24 hours: Sports Reference "
                "blocks a session for up to a day when it is asked too often."
            ) from exc
        if result.content[:1] == b"<":
            raise BrefBlockedError(
                f"{url} sent a web page, not the data file (a block or error page). "
                "Stop for 24 hours."
            )
        self._raw.put(
            "bref",
            file.dataset,
            file.name,
            result.content,
            source_ref=url,
            etag=result.etag or "",
            upstream=response_fingerprint(result.content, result.etag, url),
        )
        return result.content


__all__ = ["BrefBlockedError", "BrefExtractor"]
