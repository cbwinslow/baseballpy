"""Which seasons Statcast ingestion accepts: the one place the rule lives (ADR 56).

The bottom is a provider/owner rule (2008 for every dataset, 2021 for minor-league pitches, a
leaderboard's own first season when the live probe found a later one). The top is never a constant:
it is the current year of the clock the caller passes in (the lake clock), so it moves with the
seasons.
"""

from __future__ import annotations

from datetime import date

#: first season ingested for any Statcast dataset (owner decision, ADR 56)
FIRST_SEASON = 2008
#: first season with minor-league tracking data (probed 2026-10-27)
FIRST_MINORS_SEASON = 2021


def season_floor(*, minors: bool = False, first_with_data: int | None = None) -> int:
    """First season that may be requested: the latest of every applicable lower bound."""
    floor = FIRST_MINORS_SEASON if minors else FIRST_SEASON
    return max(floor, first_with_data or 0)


def season_skip_reason(
    season: int,
    today: date,
    *,
    minors: bool = False,
    first_with_data: int | None = None,
) -> str | None:
    """Why ``season`` must not be requested, or ``None`` when it may be."""
    if season < FIRST_SEASON:
        return f"Statcast ingestion starts in {FIRST_SEASON} (owner rule, ADR 56); season {season} is skipped"
    floor = season_floor(minors=minors, first_with_data=first_with_data)
    if season < floor:
        what = "minor-league tracking data" if minors else "data for this dataset"
        return f"no {what} before {floor}; season {season} is skipped"
    if season > today.year:
        return f"season {season} is in the future (today is {today.isoformat()})"
    return None


def check_season(
    season: int,
    today: date,
    *,
    minors: bool = False,
    first_with_data: int | None = None,
) -> None:
    """Raise ``ValueError`` naming the bounds when ``season`` must not be requested."""
    reason = season_skip_reason(season, today, minors=minors, first_with_data=first_with_data)
    if reason is not None:
        raise ValueError(reason)


__all__ = [
    "FIRST_MINORS_SEASON",
    "FIRST_SEASON",
    "check_season",
    "season_floor",
    "season_skip_reason",
]
