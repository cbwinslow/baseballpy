"""Classify the files of the Retrosheet GitHub tree into datasets (the dataset-to-pattern registry).

The tree (``GET /git/trees/<pinned sha>?recursive=1``) is the only source of truth for which
seasons and files exist; nothing is hard-coded except the *patterns* below that map a path to the
dataset family it belongs to.
"""

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field

from baseballpy.core.github_tree import TreeEntry

#: file kind -> raw dataset directory (``raw/retrosheet/<dataset>/...``)
RAW_DATASET = {
    "team": "event_files",
    "event_regular": "event_files",
    "event_postseason": "event_files",
    "event_deduced": "event_files",
    "box": "box_files",
    "roster": "rosters",
    "gamelog": "gamelogs",
    "schedule": "schedule",
    "umpires": "umpires",
    "discrepancies": "discrepancies",
}

#: kinds whose files hold play-by-play events (parsed with chadwickpy)
EVENT_KINDS = ("event_regular", "event_postseason", "event_deduced")

_SEASON_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("team", re.compile(r"^TEAM\d{4}$")),
    ("event_regular", re.compile(r"\.EV[AN]$", re.I)),
    ("event_postseason", re.compile(r"\.EV[EFR]$", re.I)),
    ("event_deduced", re.compile(r"\.ED[ANEFR]$", re.I)),
    ("box", re.compile(r"\.EB[ANEFR]$", re.I)),
    ("roster", re.compile(r"\.ROS$", re.I)),
    ("gamelog", re.compile(r"^GL\d{4}\.TXT$", re.I)),
    ("schedule", re.compile(r"schedule\.csv$", re.I)),
    ("umpires", re.compile(r"^UMPIRES\d{4}\.txt$", re.I)),
    ("discrepancies", re.compile(r"discs\.csv$", re.I)),
)
_SEASON_PATH = re.compile(r"^seasons/(\d{4})/([^/]+)$")
_POSTSEASON_GAMELOG = re.compile(r"^gamelog/(GL[A-Z]{2})\.TXT$", re.I)
_REFERENCE = re.compile(r"^reference/([^/]+)\.csv$", re.I)

POSTSEASON_GAMELOG_KINDS = {
    "wild_card": "GLWC",
    "division_series": "GLDV",
    "lcs": "GLLC",
    "world_series": "GLWS",
    "all_star": "GLAS",
}


@dataclass(frozen=True)
class RetroFile:
    """One upstream file and the dataset family it belongs to."""

    path: str
    kind: str
    name: str
    season: int | None
    size: int = 0

    @property
    def raw_dataset(self) -> str:
        """``raw/retrosheet/<dataset>/`` directory for this file."""
        if self.kind == "reference":
            return f"reference_{self.name.rsplit('.', 1)[0].lower()}"
        if self.kind == "gamelog_postseason":
            return "gamelogs_postseason"
        return RAW_DATASET[self.kind]


@dataclass
class RetroTree:
    """The classified tree: files grouped by season, plus top-level reference/gamelog files."""

    by_season: dict[int, list[RetroFile]] = field(default_factory=lambda: defaultdict(list))
    reference: list[RetroFile] = field(default_factory=list)
    postseason_gamelogs: list[RetroFile] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)

    def seasons(self) -> list[int]:
        """Seasons that have at least one file, ascending."""
        return sorted(self.by_season)

    def season_files(self, year: int, kinds: Iterable[str] | None = None) -> list[RetroFile]:
        """Files of one season, optionally restricted to some kinds."""
        wanted = set(kinds) if kinds is not None else None
        return [f for f in self.by_season.get(year, []) if wanted is None or f.kind in wanted]

    def reference_file(self, table: str) -> RetroFile | None:
        """The ``reference/<table>.csv`` entry, if the tree lists it."""
        return next((f for f in self.reference if f.name.lower() == f"{table.lower()}.csv"), None)

    def postseason_gamelog(self, kind: str) -> RetroFile | None:
        """The ``gamelog/GLxx.TXT`` file for a postseason/all-star log kind."""
        stem = POSTSEASON_GAMELOG_KINDS[kind.lower()]
        return next((f for f in self.postseason_gamelogs if f.name.upper() == f"{stem}.TXT"), None)


def classify(entries: Iterable[TreeEntry]) -> RetroTree:
    """Group tree blobs by dataset family; unrecognised data-like files are listed as uncovered."""
    tree = RetroTree()
    for entry in entries:
        path = entry.path
        if match := _SEASON_PATH.match(path):
            year, name = int(match.group(1)), match.group(2)
            kind = next((k for k, rx in _SEASON_RULES if rx.search(name)), None)
            if kind is None:
                tree.uncovered.append(path)
                continue
            tree.by_season[year].append(RetroFile(path, kind, name, year, entry.size))
        elif match := _POSTSEASON_GAMELOG.match(path):
            name = f"{match.group(1)}.TXT"
            tree.postseason_gamelogs.append(
                RetroFile(path, "gamelog_postseason", name, None, entry.size)
            )
        elif match := _REFERENCE.match(path):
            tree.reference.append(
                RetroFile(path, "reference", f"{match.group(1)}.csv", None, entry.size)
            )
        elif path.startswith(("seasons/", "gamelog/", "reference/", "misc/")):
            tree.uncovered.append(path)
    return tree
