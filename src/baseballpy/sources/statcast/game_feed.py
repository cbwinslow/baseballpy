"""Savant per-game feed (``/gf?game_pk=``): raw-only, on-demand JSON (probed live 2026-10-27).

One response is 2-3 MB (pitch lists per team, batted balls, boxscore, lineups). Bulk-ingesting a
season would be ~7 GB, so the feed is **not** part of ``ingest_all``; callers fetch the games they
need. The immutable response is kept under ``raw/statcast/game_feed/season=YYYY/<game_pk>.json``
and no typed table is derived from it (the pitch-level fields are already in ``statcast.pitches``).
"""

import json
from datetime import datetime
from typing import Any

from baseballpy.core.config import LakeConfig, RateLimitConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.lazy import lazy_singleton
from baseballpy.core.stores import RawStore

GAME_FEED_URL = "https://baseballsavant.mlb.com/gf"
REQUIRED_KEYS = ("game_status_code", "scoreboard", "game_date")


class GameFeedError(RuntimeError):
    """The feed answered but is not a game payload (never treated as an empty game)."""


class StatcastGameFeed:
    """Fetch and store Savant game feeds."""

    def __init__(
        self,
        cache_config: LakeConfig | None = None,
        rate_limit_config: RateLimitConfig | None = None,
        http: HttpClient | None = None,
    ) -> None:
        self.cache_config = cache_config or LakeConfig()
        self.http = http or (
            HttpClient(rate_limit_config) if rate_limit_config else get_http_client()
        )
        self.raw = RawStore(self.cache_config)

    @staticmethod
    def _season(payload: dict[str, Any]) -> int:
        game_date = str(payload["game_date"])
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(game_date, fmt).year
            except ValueError:
                continue
        raise GameFeedError(f"unrecognised game_date {game_date!r} in game feed")

    def get(self, game_pk: int, refresh: bool = False) -> dict[str, Any]:
        """The parsed feed of one game; final games are served from the raw store once fetched."""
        cached = self._find_cached(game_pk)
        if cached is not None and not refresh:
            payload = json.loads(cached)
            if payload.get("game_status_code") == "F":
                return payload  # type: ignore[no-any-return]
        result = self.http.get_sync(GAME_FEED_URL, params={"game_pk": game_pk})
        try:
            payload = json.loads(result.content)
        except json.JSONDecodeError as exc:
            raise GameFeedError(f"game feed for {game_pk} is not JSON: {exc}") from exc
        if not isinstance(payload, dict) or any(k not in payload for k in REQUIRED_KEYS):
            raise GameFeedError(f"game feed for {game_pk} lacks {REQUIRED_KEYS}")
        if self.cache_config.enabled:
            self.raw.put(
                "statcast",
                "game_feed",
                f"{game_pk}.json",
                result.content,
                season=self._season(payload),
                source_ref=f"{GAME_FEED_URL}?game_pk={game_pk}",
                etag=result.etag or "",
            )
        return payload

    def _find_cached(self, game_pk: int) -> bytes | None:
        root = self.cache_config.raw_dir("statcast", "game_feed", None)
        if not root.exists():
            return None
        for path in root.glob(f"season=*/{game_pk}.json"):
            return path.read_bytes()
        return None


get_default_feed = lazy_singleton(StatcastGameFeed)


def get_game_feed(game_pk: int, refresh: bool = False) -> dict[str, Any]:
    """Fetch (and store raw) the Savant ``/gf`` feed of one game."""
    return get_default_feed().get(game_pk, refresh=refresh)
