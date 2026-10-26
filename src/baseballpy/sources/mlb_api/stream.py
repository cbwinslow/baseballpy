"""Real-time Gameday live play streaming and state diffing engine."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import msgspec

MLB_LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live"


class GamedayLiveStreamer:
    """Streams discrete play-by-play events from live MLB games using monotonic sequence diffing."""

    def __init__(
        self,
        game_pk: int,
        poll_interval: float = 2.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.game_pk = game_pk
        self.poll_interval = poll_interval
        self._external_client = client
        self.watermark_at_bat: int = 0
        self.watermark_event: int = -1
        self.last_etag: str | None = None

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """Poll the live feed and yield only NEW discrete play/pitch events as they occur."""
        url = MLB_LIVE_FEED_URL.format(game_pk=self.game_pk)

        async def _run(client: httpx.AsyncClient) -> AsyncIterator[dict[str, Any]]:
            while True:
                headers: dict[str, str] = {}
                if self.last_etag:
                    headers["If-None-Match"] = self.last_etag

                try:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 304:
                        await asyncio.sleep(self.poll_interval)
                        continue

                    if resp.status_code == 200:
                        self.last_etag = resp.headers.get("ETag") or resp.headers.get("etag")
                        data = msgspec.json.decode(resp.content)

                        # Extract game status
                        game_data = data.get("gameData", {})
                        status = game_data.get("status", {}).get("abstractGameState", "")

                        # Diff plays
                        live_data = data.get("liveData", {})
                        plays = live_data.get("plays", {})
                        all_plays = plays.get("allPlays", [])

                        for play in all_plays:
                            about = play.get("about", {})
                            ab_idx = about.get("atBatIndex", 0)
                            if ab_idx < self.watermark_at_bat:
                                continue

                            matchup = play.get("matchup", {})
                            batter_id = matchup.get("batter", {}).get("id", 0)
                            pitcher_id = matchup.get("pitcher", {}).get("id", 0)
                            inning = about.get("inning", 1)
                            is_top = about.get("isTopInning", True)

                            play_events = play.get("playEvents", [])
                            for event in play_events:
                                ev_idx = event.get("index", 0)
                                if ab_idx == self.watermark_at_bat and ev_idx <= self.watermark_event:
                                    continue

                                is_pitch = event.get("isPitch", False)
                                pitch_data = event.get("pitchData", {})
                                coords = pitch_data.get("coordinates", {})
                                details = event.get("details", {})
                                count = event.get("count", {})

                                event_dict: dict[str, Any] = {
                                    "game_pk": self.game_pk,
                                    "at_bat_index": ab_idx,
                                    "event_index": ev_idx,
                                    "is_pitch": is_pitch,
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

                                # Advance monotonic watermark
                                self.watermark_at_bat = ab_idx
                                self.watermark_event = ev_idx

                                yield event_dict

                        if status == "Final":
                            break

                except Exception:
                    # In live streaming, ignore intermittent network jitter and retry after interval
                    pass

                await asyncio.sleep(self.poll_interval)

        if self._external_client:
            async for item in _run(self._external_client):
                yield item
        else:
            async with httpx.AsyncClient(http2=True, timeout=10.0) as client:
                async for item in _run(client):
                    yield item
