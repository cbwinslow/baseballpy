"""Real-time Gameday live play streaming and state diffing engine."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

import msgspec

from baseballpy.core.audit import default_audit_logger
from baseballpy.core.config import StreamingConfig
from baseballpy.core.http import HttpClient, get_http_client
from baseballpy.core.quarantine import Quarantine, get_quarantine

logger = logging.getLogger(__name__)

MLB_LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"
#: Detailed/abstract states after which no further events will arrive in this stream.
TERMINAL_STATES = frozenset(
    {"Final", "Game Over", "Completed Early", "Postponed", "Cancelled", "Suspended"}
)
DELAYED_POLL_SECONDS = 30.0


class GamedayLiveStreamer:
    """Streams discrete play-by-play events from live MLB games using monotonic sequence diffing."""

    def __init__(
        self,
        game_pk: int,
        poll_interval: float | None = None,
        http: HttpClient | None = None,
        config: StreamingConfig | None = None,
        quarantine: Quarantine | None = None,
    ) -> None:
        self.game_pk = game_pk
        self.config = config or StreamingConfig()
        self.poll_interval = (
            poll_interval if poll_interval is not None else self.config.poll_interval_seconds
        )
        self.http = http or get_http_client()
        self._quarantine = quarantine
        self.watermark_at_bat: int = 0
        self.watermark_event: int = -1
        self.last_etag: str | None = None
        self.last_timestamp: str | None = None

    def _diff(self, data: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Yield only plays/events beyond the monotonic ``(atBatIndex, eventIndex)`` watermark."""
        plays = data.get("liveData", {}).get("plays", {}).get("allPlays", [])
        for play in plays:
            about = play.get("about", {})
            ab_idx = about.get("atBatIndex", 0)
            if ab_idx < self.watermark_at_bat:
                continue

            matchup = play.get("matchup", {})
            batter_id = matchup.get("batter", {}).get("id", 0)
            pitcher_id = matchup.get("pitcher", {}).get("id", 0)
            inning = about.get("inning", 1)
            is_top = about.get("isTopInning", True)

            for event in play.get("playEvents", []):
                ev_idx = event.get("index", 0)
                if ab_idx == self.watermark_at_bat and ev_idx <= self.watermark_event:
                    continue

                pitch_data = event.get("pitchData", {})
                coords = pitch_data.get("coordinates", {})
                details = event.get("details", {})
                count = event.get("count", {})

                event_dict: dict[str, Any] = {
                    "game_pk": self.game_pk,
                    "at_bat_index": ab_idx,
                    "event_index": ev_idx,
                    "is_pitch": event.get("isPitch", False),
                    "pitch_type": details.get("type", {}).get("code"),
                    "start_speed": pitch_data.get("startSpeed"),
                    "end_speed": pitch_data.get("endSpeed"),
                    "sz_top": coords.get("szTop"),
                    "sz_bottom": coords.get("szBottom"),
                    "px": coords.get("pX"),
                    "pz": coords.get("pZ"),
                    "x": coords.get("x"),
                    "y": coords.get("y"),
                    "description": details.get("description", ""),
                    "call_code": details.get("call", {}).get("code"),
                    "event": details.get("event"),
                    "event_type": details.get("eventType"),
                    "batter_id": batter_id,
                    "pitcher_id": pitcher_id,
                    "inning": inning,
                    "is_top_inning": is_top,
                    "outs": count.get("outs", 0),
                    "balls": count.get("balls", 0),
                    "strikes": count.get("strikes", 0),
                    "timestamp": event.get("startTime"),
                }

                self.watermark_at_bat = ab_idx
                self.watermark_event = ev_idx
                yield event_dict

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Poll the live feed and yield only NEW discrete play/pitch events as they occur.

        Transient network failures are retried by the shared HTTP client; once retries are
        exhausted the error propagates (and is audited) instead of being swallowed.
        Malformed payloads are quarantined and polling continues.
        """
        url = MLB_LIVE_FEED_URL.format(game_pk=self.game_pk)
        last_activity = time.monotonic()
        emitted = 0

        async with default_audit_logger.async_track(
            operation="mlb_stream", source="mlb_api", endpoint=url
        ) as tracker:
            while True:
                etag = self.last_etag if self.config.enable_conditional_etag else None
                result = await self.http.get(url, etag=etag, allow=(200, 304))
                sleep_for = self.poll_interval

                if not result.not_modified:
                    self.last_etag = result.etag or self.last_etag
                    data: Any = None
                    try:
                        data = msgspec.json.decode(result.content)
                    except msgspec.DecodeError as exc:
                        (self._quarantine or get_quarantine()).write(
                            "mlb_api",
                            "live_feed",
                            [result.content],
                            f"undecodable live feed payload: {exc}",
                            {"game_pk": self.game_pk},
                        )

                    if isinstance(data, dict):
                        stamp = data.get("metaData", {}).get("timeStamp")
                        if stamp is None or stamp != self.last_timestamp:
                            self.last_timestamp = stamp
                            for event in self._diff(data):
                                emitted += 1
                                tracker.set_records(emitted)
                                last_activity = time.monotonic()
                                yield event

                        status = data.get("gameData", {}).get("status", {})
                        state = status.get("abstractGameState", "")
                        detailed = status.get("detailedState", "")
                        if state in TERMINAL_STATES or detailed in TERMINAL_STATES:
                            return
                        if "Delayed" in detailed:
                            sleep_for = max(sleep_for, DELAYED_POLL_SECONDS)

                idle_minutes = (time.monotonic() - last_activity) / 60.0
                if idle_minutes >= self.config.max_inactivity_minutes:
                    logger.warning(
                        "stream for game %s idle %.0f min; stopping", self.game_pk, idle_minutes
                    )
                    return
                await asyncio.sleep(sleep_for)
