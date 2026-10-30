"""The single place that imports ``chadwickpy`` (GPL-3.0) for Retrosheet parsing.

Keeping the import here isolates the licence boundary (see ADR 26): the rest of baseballpy talks to
this module's re-exports only, and a missing/broken install produces one clear error.
"""

try:
    from chadwickpy.box import box_create
    from chadwickpy.roster import League
    from chadwickpy.tools import daily, sub
    from chadwickpy.tools.daily import COLUMNS as DAILY_COLUMNS
    from chadwickpy.tools.events import COLUMNS as EVENT_COLUMNS
    from chadwickpy.tools.events import event_rows
    from chadwickpy.tools.sub import COLUMNS as SUB_COLUMNS
    from chadwickpy.tools.tools import iterate_games
except ImportError as exc:  # pragma: no cover - exercised only without the dependency
    raise ImportError(
        "Retrosheet parsing needs the GPL-licensed 'chadwickpy' package. "
        "Install it with: pip install 'baseballpy[retrosheet]'"
    ) from exc

__all__ = [
    "DAILY_COLUMNS",
    "EVENT_COLUMNS",
    "SUB_COLUMNS",
    "League",
    "box_create",
    "daily",
    "event_rows",
    "iterate_games",
    "sub",
]
