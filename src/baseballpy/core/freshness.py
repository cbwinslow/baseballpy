"""Cache freshness policy: completed historical seasons are immutable; current data uses TTLs."""

from datetime import UTC, date, datetime
from typing import Any

#: Default time-to-live (seconds) per dataset family for current-season / reference data.
#: ``None`` means immutable once downloaded (until ``refresh=True``).
DEFAULT_TTLS: dict[str, int | None] = {
    "schedule": 900,
    "standings": 900,
    "boxscore": 60,
    "roster": 21600,
    "transactions": 3600,
    "draft": 86400,
    "teams": 86400,
    "venues": 86400,
    "statcast": 21600,
    "leaderboard": 86400,
    "chadwick": 86400,
    "lahman": None,
    "retrosheet": None,
}


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def is_fresh(
    entry: dict[str, Any] | None,
    *,
    ttl_seconds: float | None,
    season: int | None = None,
    today: date | None = None,
    now: datetime | None = None,
    refresh: bool = False,
) -> bool:
    """Decide whether a cached manifest ``entry`` can be served without re-fetching.

    - ``refresh`` always forces a re-fetch.
    - Only COMPLETED entries are ever fresh.
    - A season-partitioned chunk whose ``season`` is before the current year is immutable.
    - ``ttl_seconds is None`` means immutable; otherwise fresh while ``now - fetched_at < ttl``.
    """
    if refresh or not entry or entry.get("status") != "COMPLETED":
        return False
    current = now or datetime.now(UTC)
    current_year = (today or current.date()).year
    if season is not None and season < current_year:
        return True
    if ttl_seconds is None:
        return True
    fetched = _parse_ts(entry.get("fetched_at") or entry.get("completed_at"))
    if fetched is None:
        return False
    return (current - fetched).total_seconds() < ttl_seconds
