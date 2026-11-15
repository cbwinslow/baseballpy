"""Today's games for the live supervisor: one small request to the MLB schedule (through the shared ``HttpClient``).

``GET /api/v1/schedule?sportId=<ids>&date=<YYYY-MM-DD>`` lists ``dates[].games[]`` with ``gamePk``, ``season``,
``gameDate`` (UTC) and ``status.abstractGameState``. The answer is small (kilobytes) and is asked once per schedule
pass, not per game. A game with no usable ``gamePk`` is skipped with a warning (never silently).
"""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

import msgspec

from baseballpy.core.http import HttpClient
from baseballpy.sources.mlb_api.live.supervisor import ScheduledGame

logger = logging.getLogger(__name__)

SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def _start(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_schedule(payload: Any, fallback_season: int) -> list[ScheduledGame]:
    """The games of a schedule answer; a game without a usable ``gamePk`` is logged and skipped."""
    games: list[ScheduledGame] = []
    for day in payload.get("dates", []) if isinstance(payload, dict) else []:
        for raw in day.get("games", []):
            try:
                pk = int(raw["gamePk"])
            except (KeyError, TypeError, ValueError):
                logger.warning(
                    "live: a schedule entry without a usable gamePk was skipped: %r", raw
                )
                continue
            try:
                season = int(raw.get("season", fallback_season))
            except (TypeError, ValueError):
                season = fallback_season
            state = str(raw.get("status", {}).get("abstractGameState", ""))
            games.append(ScheduledGame(pk, season, state, _start(raw.get("gameDate"))))
    return games


class MlbScheduleSource:
    """The real :class:`~.supervisor.ScheduleSource`: the games of a day at the given levels (1 = the major leagues)."""

    def __init__(self, http: HttpClient, sport_ids: Sequence[int] = (1,)) -> None:
        self.http = http
        self.sport_ids = tuple(sport_ids)

    async def games(self, day: date) -> list[ScheduledGame]:
        """Every game scheduled on ``day`` (a UTC calendar date as the supervisor sees it)."""
        result = await self.http.get(
            SCHEDULE_URL,
            params={"sportId": ",".join(str(s) for s in self.sport_ids), "date": day.isoformat()},
        )
        return parse_schedule(msgspec.json.decode(result.content), day.year)
