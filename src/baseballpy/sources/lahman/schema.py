"""Strict PyArrow schemas (generated from the real headers) and Enums for the Lahman database."""

from enum import StrEnum

import pyarrow as pa

from baseballpy.core.schema_tools import schema_from_columns
from baseballpy.sources.lahman.tables import LAHMAN_COLUMNS, LAHMAN_KEYS


class LahmanTable(StrEnum):
    """Enumeration of all 27 tables in the SABR Lahman Baseball Database."""

    ALLSTAR_FULL = "AllstarFull"
    APPEARANCES = "Appearances"
    AWARDS_MANAGERS = "AwardsManagers"
    AWARDS_PLAYERS = "AwardsPlayers"
    AWARDS_SHARE_MANAGERS = "AwardsShareManagers"
    AWARDS_SHARE_PLAYERS = "AwardsSharePlayers"
    BATTING = "Batting"
    BATTING_POST = "BattingPost"
    COLLEGE_PLAYING = "CollegePlaying"
    FIELDING = "Fielding"
    FIELDING_OF = "FieldingOF"
    FIELDING_OF_SPLIT = "FieldingOFsplit"
    FIELDING_POST = "FieldingPost"
    HALL_OF_FAME = "HallOfFame"
    HOME_GAMES = "HomeGames"
    MANAGERS = "Managers"
    MANAGERS_HALF = "ManagersHalf"
    PARKS = "Parks"
    PEOPLE = "People"
    PITCHING = "Pitching"
    PITCHING_POST = "PitchingPost"
    SALARIES = "Salaries"
    SCHOOLS = "Schools"
    SERIES_POST = "SeriesPost"
    TEAMS = "Teams"
    TEAMS_FRANCHISES = "TeamsFranchises"
    TEAMS_HALF = "TeamsHalf"


_BY_LOWER = {table.value.lower(): table.value for table in LahmanTable}


def canonical_table_name(name: str | LahmanTable) -> str:
    """The table name as Lahman spells it, accepting any letter case (``"batting"`` -> ``Batting``).

    Raises ``ValueError`` listing the 27 known names for anything else.
    """
    found = _BY_LOWER.get(str(name).strip().lower())
    if found is None:
        raise ValueError(
            f"unknown table {str(name)!r} for lahman; known: {sorted(_BY_LOWER.values())}"
        )
    return found


#: Strict schema for every one of the 27 tables (typed columns + trailing ``_extras`` JSON string).
LAHMAN_SCHEMAS: dict[str, pa.Schema] = {
    table: schema_from_columns(columns) for table, columns in LAHMAN_COLUMNS.items()
}
#: Documented primary key per table (uniqueness verified on the full release).
LAHMAN_PRIMARY_KEYS = LAHMAN_KEYS
KNOWN_SCHEMAS = LAHMAN_SCHEMAS

LAHMAN_PEOPLE_SCHEMA = LAHMAN_SCHEMAS["People"]
LAHMAN_BATTING_SCHEMA = LAHMAN_SCHEMAS["Batting"]
LAHMAN_PITCHING_SCHEMA = LAHMAN_SCHEMAS["Pitching"]
LAHMAN_TEAMS_SCHEMA = LAHMAN_SCHEMAS["Teams"]
LAHMAN_FIELDING_SCHEMA = LAHMAN_SCHEMAS["Fielding"]
LAHMAN_SALARIES_SCHEMA = LAHMAN_SCHEMAS["Salaries"]
LAHMAN_HALL_OF_FAME_SCHEMA = LAHMAN_SCHEMAS["HallOfFame"]
LAHMAN_ALLSTAR_FULL_SCHEMA = LAHMAN_SCHEMAS["AllstarFull"]
