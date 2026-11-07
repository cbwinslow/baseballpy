"""Baseball-Reference downloads, as data (no network, no side effects).

Baseball-Reference publishes its WAR tables as plain download files linked from its About page; that
is the only route used. Its pages are not scraped: Sports Reference blocks a session for up to a day
above 20 requests a minute and asks that its pages are not spidered (``docs/sources/bref.md``).
"""

from dataclasses import dataclass

from baseballpy.core.config import BREF_HOST

BREF_BASE = f"https://{BREF_HOST}"
#: the word these files use for a missing value
NULL_TOKEN = "NULL"  # noqa: S105 - the file's word for a missing cell, not a secret
#: a file downloaded less than this long ago is not downloaded again (the files change once a day)
FRESH_SECONDS = 12 * 3600


@dataclass(frozen=True)
class BrefFile:
    """One published file and the dataset it feeds."""

    dataset: str
    path: str
    keys: tuple[str, ...]
    #: the column that holds the season (the processed chunk of a year is stored under it)
    season_column: str
    description: str

    @property
    def name(self) -> str:
        """File name as published (``war_daily_bat.txt``)."""
        return self.path.rsplit("/", 1)[-1]


FILES: tuple[BrefFile, ...] = (
    BrefFile(
        "war_batting",
        "/data/war_daily_bat.txt",
        ("player_ID", "year_ID", "stint_ID"),
        "year_ID",
        "Baseball-Reference WAR, batting side: one row per player, season and stint.",
    ),
    BrefFile(
        "war_pitching",
        "/data/war_daily_pitch.txt",
        ("player_ID", "year_ID", "stint_ID"),
        "year_ID",
        "Baseball-Reference WAR, pitching side: one row per player, season and stint.",
    ),
)
BY_DATASET: dict[str, BrefFile] = {f.dataset: f for f in FILES}
DATASET_KEYS: dict[str, tuple[str, ...]] = {f.dataset: f.keys for f in FILES}

__all__ = [
    "BREF_BASE",
    "BY_DATASET",
    "DATASET_KEYS",
    "FILES",
    "FRESH_SECONDS",
    "NULL_TOKEN",
    "BrefFile",
]
