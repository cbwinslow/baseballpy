"""Strict PyArrow schemas (generated from the real headers) and Enums for the Lahman database."""

from enum import StrEnum

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.lahman.tables import LAHMAN_COLUMNS, LAHMAN_KEYS


class LahmanTable(StrEnum):
    """Enumeration of all 27 tables in the SABR Lahman Baseball Database."""

    ALLSTAR_FULL = "allstar_full"
    APPEARANCES = "appearances"
    AWARDS_MANAGERS = "awards_managers"
    AWARDS_PLAYERS = "awards_players"
    AWARDS_SHARE_MANAGERS = "awards_share_managers"
    AWARDS_SHARE_PLAYERS = "awards_share_players"
    BATTING = "batting"
    BATTING_POST = "batting_post"
    COLLEGE_PLAYING = "college_playing"
    FIELDING = "fielding"
    FIELDING_OF = "fielding_of"
    FIELDING_OF_SPLIT = "fielding_of_split"
    FIELDING_POST = "fielding_post"
    HALL_OF_FAME = "hall_of_fame"
    HOME_GAMES = "home_games"
    MANAGERS = "managers"
    MANAGERS_HALF = "managers_half"
    PARKS = "parks"
    PEOPLE = "people"
    PITCHING = "pitching"
    PITCHING_POST = "pitching_post"
    SALARIES = "salaries"
    SCHOOLS = "schools"
    SERIES_POST = "series_post"
    TEAMS = "teams"
    TEAMS_FRANCHISES = "teams_franchises"
    TEAMS_HALF = "teams_half"


def _squash(name: str) -> str:
    """A name without letter case and underscores, the common form of every spelling."""
    return str(name).replace("_", "").strip().lower()


#: underscore name -> the spelling Lahman uses in its file names (``batting_post`` -> ``BattingPost``);
#: found by matching the enum names to the generated table list, so there is no second list to keep
UPSTREAM_NAMES: dict[str, str] = {
    table.value: next(k for k in LAHMAN_COLUMNS if _squash(k) == _squash(table.value))
    for table in LahmanTable
}
_BY_SQUASHED = {_squash(slug): slug for slug in UPSTREAM_NAMES}


def canonical_table_name(name: str | LahmanTable) -> str:
    """The underscore table name (``batting_post``) for any spelling of it.

    ``batting_post``, ``BattingPost``, ``battingpost`` and ``BATTING_POST`` all give ``batting_post``.
    Raises ``ValueError`` listing the 27 known names for anything else.
    """
    found = _BY_SQUASHED.get(_squash(name))
    if found is None:
        raise ValueError(f"unknown table {str(name)!r} for lahman; known: {sorted(UPSTREAM_NAMES)}")
    return found


def upstream_name(name: str | LahmanTable) -> str:
    """The name in Lahman's own file names (``batting_post`` -> ``BattingPost``) for the provider."""
    return UPSTREAM_NAMES[canonical_table_name(name)]


#: Strict schema for every one of the 27 tables (typed columns + trailing ``_extras`` JSON string).
LAHMAN_SCHEMAS: dict[str, pa.Schema] = {
    canonical_table_name(table): schema_from_columns(columns)
    for table, columns in LAHMAN_COLUMNS.items()
}
#: Documented primary key per table (uniqueness verified on the full release).
LAHMAN_PRIMARY_KEYS: dict[str, tuple[str, ...]] = {
    canonical_table_name(table): tuple(keys) for table, keys in LAHMAN_KEYS.items()
}
KNOWN_SCHEMAS = LAHMAN_SCHEMAS

LAHMAN_PEOPLE_SCHEMA = LAHMAN_SCHEMAS["people"]
LAHMAN_BATTING_SCHEMA = LAHMAN_SCHEMAS["batting"]
LAHMAN_PITCHING_SCHEMA = LAHMAN_SCHEMAS["pitching"]
LAHMAN_TEAMS_SCHEMA = LAHMAN_SCHEMAS["teams"]
LAHMAN_FIELDING_SCHEMA = LAHMAN_SCHEMAS["fielding"]
LAHMAN_SALARIES_SCHEMA = LAHMAN_SCHEMAS["salaries"]
LAHMAN_HALL_OF_FAME_SCHEMA = LAHMAN_SCHEMAS["hall_of_fame"]
LAHMAN_ALLSTAR_FULL_SCHEMA = LAHMAN_SCHEMAS["allstar_full"]
