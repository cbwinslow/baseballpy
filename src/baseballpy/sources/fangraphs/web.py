"""FanGraphs website API routes and rules, as data (no network, no side effects).

These are the JSON routes the FanGraphs website itself calls for its leaderboards, projections and
prospect board (checked 2026-11-06). FanGraphs documents none of them and says it does not support
scraping, so the downloader is deliberately slow (one request every two seconds, one at a time),
introduces itself with an honest user agent, never retries a refusal and stops at the first
challenge. It never changes its identity to get past bot protection.
"""

from datetime import date

from baseballpy.core.config import FANGRAPHS_HOST

BASE = f"https://{FANGRAPHS_HOST}"
LEADERS_PATH = "/api/leaders/major-league/data"
PROJECTIONS_PATH = "/api/projections"

#: first season the leaderboards serve (batting and pitching boards start in 1871)
FIRST_SEASON = 1871

#: dataset -> the ``stats`` group of the leaderboard route
LEADERBOARDS: dict[str, str] = {"batting": "bat", "pitching": "pit", "fielding": "fld"}

#: projection systems by horizon (``steamer`` for the pre-season, ``steamerr`` rest of season, ...)
PRESEASON_SYSTEMS = (
    "steamer",
    "zips",
    "zipsdc",
    "fangraphsdc",
    "atc",
    "thebat",
    "thebatx",
    "oopsy",
)
ROS_SYSTEMS = (
    "steamerr",
    "rzips",
    "rzipsdc",
    "rfangraphsdc",
    "ratcdc",
    "roopsydc",
    "rthebat",
    "rthebatx",
)
PROJECTION_GROUPS = ("bat", "pit")

#: FanGraphs sends pairs of boards whose keys differ only by a sign or symbol; after lowercasing they
#: would collide, so they are renamed first (the names the existing files use)
COLUMN_RENAMES: dict[str, str] = {
    "-WPA": "WPA_neg",
    "+WPA": "WPA_pos",
    "K-BB%": "K_minus_BB_pct",
    "K/BB+": "K_per_BB_plus",
}


def user_agent(version: str) -> str:
    """An honest, identifiable user agent (what the program is and where to ask about it)."""
    return f"baseballpy/{version} (research use; +https://github.com/cbwinslow/baseballpy)"


def leaderboard_params(stats: str, season: int) -> dict[str, str]:
    """Query for one full-season leaderboard: every player (``qual=0``), one row per player-season."""
    return {
        "age": "",
        "pos": "all",
        "stats": stats,
        "lg": "all",
        "qual": "0",
        "season": str(season),  # FanGraphs names are inverted: season = end year, season1 = start
        "season1": str(season),
        "startdate": "",
        "enddate": "",
        "month": "0",
        "hand": "",
        "team": "0",
        "pageitems": "500000",
        "pagenum": "1",
        "ind": "1",
        "rost": "0",
        "players": "",
        "type": "8",
        "postseason": "",
        "sortdir": "default",
        "sortstat": "WAR",
    }


def projection_params(system: str, group: str) -> dict[str, str]:
    """Query for every projected player of one system and stat group."""
    return {
        "type": system,
        "stats": group,
        "pos": "all",
        "team": "0",
        "players": "0",
        "lg": "all",
    }


def current_season(today: date | None = None) -> int:
    """The calendar year, the newest season a leaderboard can have."""
    return (today or date.today()).year


__all__ = [
    "BASE",
    "COLUMN_RENAMES",
    "FIRST_SEASON",
    "LEADERBOARDS",
    "LEADERS_PATH",
    "PRESEASON_SYSTEMS",
    "PROJECTIONS_PATH",
    "PROJECTION_GROUPS",
    "ROS_SYSTEMS",
    "current_season",
    "leaderboard_params",
    "projection_params",
    "user_agent",
]
