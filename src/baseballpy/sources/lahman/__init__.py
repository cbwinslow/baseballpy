"""SABR Lahman Baseball Database source package."""

from pathlib import Path

import pyarrow as pa

from baseballpy.core.lazy import lazy_singleton
from baseballpy.sources.lahman.api import LahmanSource
from baseballpy.sources.lahman.extractor import LahmanExtractor
from baseballpy.sources.lahman.normalizer import LahmanNormalizer
from baseballpy.sources.lahman.schema import (
    LAHMAN_ALLSTAR_FULL_SCHEMA,
    LAHMAN_BATTING_SCHEMA,
    LAHMAN_FIELDING_SCHEMA,
    LAHMAN_HALL_OF_FAME_SCHEMA,
    LAHMAN_PEOPLE_SCHEMA,
    LAHMAN_PITCHING_SCHEMA,
    LAHMAN_SALARIES_SCHEMA,
    LAHMAN_TEAMS_SCHEMA,
    LahmanTable,
)

get_default_source = lazy_singleton(LahmanSource)


def batting(refresh: bool = False) -> pa.Table:
    """Extract regular season Batting statistics (1871-2025)."""
    return get_default_source().batting(refresh=refresh)


def pitching(refresh: bool = False) -> pa.Table:
    """Extract regular season Pitching statistics (1871-2025)."""
    return get_default_source().pitching(refresh=refresh)


def people(refresh: bool = False) -> pa.Table:
    """Extract People table (biographical player registry)."""
    return get_default_source().people(refresh=refresh)


def teams(refresh: bool = False) -> pa.Table:
    """Extract Teams standings and seasonal team totals."""
    return get_default_source().teams(refresh=refresh)


def fielding(refresh: bool = False) -> pa.Table:
    """Extract Fielding statistics by position and year."""
    return get_default_source().fielding(refresh=refresh)


def salaries(refresh: bool = False) -> pa.Table:
    """Extract historical player Salaries."""
    return get_default_source().salaries(refresh=refresh)


def hall_of_fame(refresh: bool = False) -> pa.Table:
    """Extract Hall of Fame voting outcomes and ballots."""
    return get_default_source().hall_of_fame(refresh=refresh)


def allstar(refresh: bool = False) -> pa.Table:
    """Extract All-Star Game roster appearances."""
    return get_default_source().allstar(refresh=refresh)


def import_archive(archive_path: Path | str) -> int:
    """Import a local Lahman ZIP archive or unzipped directory downloaded from SABR Box."""
    return get_default_source().import_archive(archive_path)


__all__ = [
    "LAHMAN_ALLSTAR_FULL_SCHEMA",
    "LAHMAN_BATTING_SCHEMA",
    "LAHMAN_FIELDING_SCHEMA",
    "LAHMAN_HALL_OF_FAME_SCHEMA",
    "LAHMAN_PEOPLE_SCHEMA",
    "LAHMAN_PITCHING_SCHEMA",
    "LAHMAN_SALARIES_SCHEMA",
    "LAHMAN_TEAMS_SCHEMA",
    "LahmanExtractor",
    "LahmanNormalizer",
    "LahmanSource",
    "LahmanTable",
    "allstar",
    "batting",
    "fielding",
    "hall_of_fame",
    "import_archive",
    "people",
    "pitching",
    "salaries",
    "teams",
]
