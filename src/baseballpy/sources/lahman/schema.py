"""Canonical PyArrow schemas and Enums for the SABR Lahman Baseball Database (1871-2025)."""

from enum import StrEnum

import pyarrow as pa


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


LAHMAN_PEOPLE_SCHEMA = pa.schema(
    [
        ("playerID", pa.string()),
        ("birthYear", pa.int16()),
        ("birthMonth", pa.int8()),
        ("birthDay", pa.int8()),
        ("birthCountry", pa.string()),
        ("birthState", pa.string()),
        ("birthCity", pa.string()),
        ("deathYear", pa.int16()),
        ("deathMonth", pa.int8()),
        ("deathDay", pa.int8()),
        ("deathCountry", pa.string()),
        ("deathState", pa.string()),
        ("deathCity", pa.string()),
        ("nameFirst", pa.string()),
        ("nameLast", pa.string()),
        ("nameGiven", pa.string()),
        ("weight", pa.int16()),
        ("height", pa.int16()),
        ("bats", pa.string()),
        ("throws", pa.string()),
        ("debut", pa.date32()),
        ("finalGame", pa.date32()),
        ("retroID", pa.string()),
        ("bbrefID", pa.string()),
    ]
)

LAHMAN_BATTING_SCHEMA = pa.schema(
    [
        ("playerID", pa.string()),
        ("yearID", pa.int16()),
        ("stint", pa.int8()),
        ("teamID", pa.string()),
        ("lgID", pa.string()),
        ("G", pa.int16()),
        ("AB", pa.int16()),
        ("R", pa.int16()),
        ("H", pa.int16()),
        ("2B", pa.int16()),
        ("3B", pa.int16()),
        ("HR", pa.int16()),
        ("RBI", pa.int16()),
        ("SB", pa.int16()),
        ("CS", pa.int16()),
        ("BB", pa.int16()),
        ("SO", pa.int16()),
        ("IBB", pa.int16()),
        ("HBP", pa.int16()),
        ("SH", pa.int16()),
        ("SF", pa.int16()),
        ("GIDP", pa.int16()),
    ]
)

LAHMAN_PITCHING_SCHEMA = pa.schema(
    [
        ("playerID", pa.string()),
        ("yearID", pa.int16()),
        ("stint", pa.int8()),
        ("teamID", pa.string()),
        ("lgID", pa.string()),
        ("W", pa.int16()),
        ("L", pa.int16()),
        ("G", pa.int16()),
        ("GS", pa.int16()),
        ("CG", pa.int16()),
        ("SHO", pa.int16()),
        ("SV", pa.int16()),
        ("IPouts", pa.int32()),
        ("H", pa.int16()),
        ("ER", pa.int16()),
        ("HR", pa.int16()),
        ("BB", pa.int16()),
        ("SO", pa.int16()),
        ("BAOpp", pa.float32()),
        ("ERA", pa.float32()),
        ("IBB", pa.int16()),
        ("WP", pa.int16()),
        ("HBP", pa.int16()),
        ("BK", pa.int16()),
        ("BFP", pa.int32()),
        ("GF", pa.int16()),
        ("R", pa.int16()),
        ("SH", pa.int16()),
        ("SF", pa.int16()),
        ("GIDP", pa.int16()),
    ]
)

LAHMAN_TEAMS_SCHEMA = pa.schema(
    [
        ("yearID", pa.int16()),
        ("lgID", pa.string()),
        ("teamID", pa.string()),
        ("franchID", pa.string()),
        ("divID", pa.string()),
        ("Rank", pa.int8()),
        ("G", pa.int16()),
        ("Ghome", pa.int16()),
        ("W", pa.int16()),
        ("L", pa.int16()),
        ("DivWin", pa.string()),
        ("WCWin", pa.string()),
        ("LgWin", pa.string()),
        ("WSWin", pa.string()),
        ("R", pa.int16()),
        ("AB", pa.int16()),
        ("H", pa.int16()),
        ("2B", pa.int16()),
        ("3B", pa.int16()),
        ("HR", pa.int16()),
        ("BB", pa.int16()),
        ("SO", pa.int16()),
        ("SB", pa.int16()),
        ("CS", pa.int16()),
        ("HBP", pa.int16()),
        ("SF", pa.int16()),
        ("RA", pa.int16()),
        ("ER", pa.int16()),
        ("ERA", pa.float32()),
        ("CG", pa.int16()),
        ("SHO", pa.int16()),
        ("SV", pa.int16()),
        ("IPouts", pa.int32()),
        ("HA", pa.int16()),
        ("HRA", pa.int16()),
        ("BBA", pa.int16()),
        ("SOA", pa.int16()),
        ("E", pa.int16()),
        ("DP", pa.int16()),
        ("FP", pa.float32()),
        ("name", pa.string()),
        ("park", pa.string()),
        ("attendance", pa.int32()),
        ("BPF", pa.int16()),
        ("PPF", pa.int16()),
        ("teamIDBR", pa.string()),
        ("teamIDlahman45", pa.string()),
        ("teamIDretro", pa.string()),
    ]
)

LAHMAN_FIELDING_SCHEMA = pa.schema(
    [
        ("playerID", pa.string()),
        ("yearID", pa.int16()),
        ("stint", pa.int8()),
        ("teamID", pa.string()),
        ("lgID", pa.string()),
        ("POS", pa.string()),
        ("G", pa.int16()),
        ("GS", pa.int16()),
        ("InnOuts", pa.int32()),
        ("PO", pa.int16()),
        ("A", pa.int16()),
        ("E", pa.int16()),
        ("DP", pa.int16()),
        ("PB", pa.int16()),
        ("WP", pa.int16()),
        ("SB", pa.int16()),
        ("CS", pa.int16()),
        ("ZR", pa.float32()),
    ]
)

LAHMAN_SALARIES_SCHEMA = pa.schema(
    [
        ("yearID", pa.int16()),
        ("teamID", pa.string()),
        ("lgID", pa.string()),
        ("playerID", pa.string()),
        ("salary", pa.int64()),
    ]
)

LAHMAN_HALL_OF_FAME_SCHEMA = pa.schema(
    [
        ("playerID", pa.string()),
        ("yearid", pa.int16()),
        ("votedBy", pa.string()),
        ("ballots", pa.int16()),
        ("needed", pa.int16()),
        ("votes", pa.int16()),
        ("inducted", pa.string()),
        ("category", pa.string()),
        ("needed_note", pa.string()),
    ]
)

LAHMAN_ALLSTAR_FULL_SCHEMA = pa.schema(
    [
        ("playerID", pa.string()),
        ("yearID", pa.int16()),
        ("gameNum", pa.int8()),
        ("gameID", pa.string()),
        ("teamID", pa.string()),
        ("lgID", pa.string()),
        ("GP", pa.int8()),
        ("startingPos", pa.int8()),
    ]
)

KNOWN_SCHEMAS: dict[str, pa.Schema] = {
    LahmanTable.PEOPLE: LAHMAN_PEOPLE_SCHEMA,
    LahmanTable.BATTING: LAHMAN_BATTING_SCHEMA,
    LahmanTable.PITCHING: LAHMAN_PITCHING_SCHEMA,
    LahmanTable.TEAMS: LAHMAN_TEAMS_SCHEMA,
    LahmanTable.FIELDING: LAHMAN_FIELDING_SCHEMA,
    LahmanTable.SALARIES: LAHMAN_SALARIES_SCHEMA,
    LahmanTable.HALL_OF_FAME: LAHMAN_HALL_OF_FAME_SCHEMA,
    LahmanTable.ALLSTAR_FULL: LAHMAN_ALLSTAR_FULL_SCHEMA,
}
