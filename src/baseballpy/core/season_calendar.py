"""Which seasons exist yet: the MLB season calendar decides, not the year on the clock.

A season counts once its first day (spring training, else opening day) has arrived. This keeps a
planned ``--seasons all`` from asking for the new year's season in January and February, when the
calendar already lists it but nothing has been played (ADR 66). One request to
``/v1/seasons/all`` is cached under ``cache/http/mlb-seasons/all.json`` for twelve hours. Seasons
before the current year are always started and the next year is never started, so neither needs
the calendar; only the current year does.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import date

from baseballpy.core.atomic import atomic_write
from baseballpy.core.config import LakeConfig
from baseballpy.core.http import HttpClient, get_http_client

logger = logging.getLogger(__name__)

SEASONS_ALL_URL = "https://statsapi.mlb.com/api/v1/seasons/all"
#: how long the cached calendar is trusted (dates move rarely, but the current season is edited)
CALENDAR_TTL_SECONDS = 12 * 3600
_START_KEYS = ("springStartDate", "regularSeasonStartDate", "seasonStartDate")
_END_KEYS = ("postSeasonEndDate", "seasonEndDate", "regularSeasonEndDate")


@dataclass(frozen=True)
class SeasonDates:
    """First and last day of one MLB season (spring training to the end of the postseason)."""

    season: int
    start: date
    end: date


def parse_calendar(payload: bytes | str) -> dict[int, SeasonDates]:
    """``{season: SeasonDates}`` from the ``/v1/seasons/all`` answer; seasons without dates are left out."""
    out: dict[int, SeasonDates] = {}
    for record in json.loads(payload).get("seasons", []):
        start = next((record[k] for k in _START_KEYS if record.get(k)), None)
        end = next((record[k] for k in _END_KEYS if record.get(k)), None)
        if start and end:
            season = int(record["seasonId"])
            out[season] = SeasonDates(
                season, date.fromisoformat(str(start)[:10]), date.fromisoformat(str(end)[:10])
            )
    return out


class SeasonCalendar:
    """The MLB season calendar, read at most once per twelve hours and only when it is needed."""

    def __init__(self, config: LakeConfig | None = None, http: HttpClient | None = None) -> None:
        self.config = config or LakeConfig()
        self._http = http
        self._seasons: dict[int, SeasonDates] | None = None

    @property
    def today(self) -> date:
        """The lake clock (tests pin it)."""
        return self.config.today_or_now()

    def seasons(self) -> dict[int, SeasonDates]:
        """Every season the MLB calendar lists, fetched or read from the twelve-hour cache."""
        if self._seasons is None:
            cache = self.config.http_cache_root / "mlb-seasons" / "all.json"
            fresh = cache.exists() and time.time() - cache.stat().st_mtime < CALENDAR_TTL_SECONDS
            if fresh:
                self._seasons = parse_calendar(cache.read_text(encoding="utf-8"))
            else:
                http = self._http or get_http_client()
                content = http.get_sync(SEASONS_ALL_URL, params={"sportId": 1}).content
                self._seasons = parse_calendar(content)
                if self._seasons:
                    with atomic_write(cache) as part:
                        part.write_bytes(content)
        return self._seasons

    def not_started_reason(self, season: int) -> str | None:
        """Why ``season`` has no data yet, or ``None`` when its first day has arrived."""
        today = self.today
        if season < today.year:
            return None
        if season > today.year:
            return f"season {season} is in the future (today is {today.isoformat()})"
        dates = self.seasons().get(season)
        if dates is None:
            return f"the MLB calendar does not list season {season} yet"
        if today < dates.start:
            return (
                f"season {season} has not started (first day {dates.start.isoformat()}, "
                f"today is {today.isoformat()})"
            )
        return None

    def latest_started_season(self) -> int:
        """The newest season with a first day on or before today."""
        year = self.today.year
        return year if self.not_started_reason(year) is None else year - 1

    def is_finished(self, season: int) -> bool:
        """Whether the season's last day (end of the postseason) is behind us."""
        dates = self.seasons().get(season)
        return dates is not None and dates.end < self.today


__all__ = [
    "CALENDAR_TTL_SECONDS",
    "SEASONS_ALL_URL",
    "SeasonCalendar",
    "SeasonDates",
    "parse_calendar",
]
