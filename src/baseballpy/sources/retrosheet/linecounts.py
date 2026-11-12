"""How many rows a season of an event-derived Retrosheet table must have, counted from the raw event files.

The event files are not CSV, so the cell-by-cell round-trip check cannot read them. Counting lines is the cheapest
independent proof that no play or substitution was lost or invented (verified on 2023: 190,416 events, 3,263
postseason events and 27,444 substitutions, each equal to the count):

* ``events``: one row per ``play`` line whose event field is not ``NP`` (no play) in the regular-season files (``.EVA``
  and ``.EVN``); ``events_postseason`` the same for ``.EVE``, ``.EVF`` and ``.EVR``; ``events_deduced`` for ``.ED?``;
* ``substitutions``: one row per ``sub`` line of the regular-season files.
"""

import gzip
import re
from collections.abc import Callable
from pathlib import Path

from baseballpy.core.config import LakeConfig

#: dataset -> (file name pattern, record type counted, whether ``NP`` plays are left out)
RULES: dict[str, tuple[re.Pattern[str], str, bool]] = {
    "events": (re.compile(r"\.EV[AN]$", re.I), "play", True),
    "events_postseason": (re.compile(r"\.EV[EFR]$", re.I), "play", True),
    "events_deduced": (re.compile(r"\.ED[ANEFR]$", re.I), "play", True),
    "substitutions": (re.compile(r"\.EV[AN]$", re.I), "sub", False),
}


def _lines(path: Path) -> list[str]:
    data = path.read_bytes()
    if path.name.endswith(".gz"):
        data = gzip.decompress(data)
    return data.decode("latin-1").splitlines()


def expected_rows(config: LakeConfig, dataset: str, season: int) -> int:
    """The rows ``dataset`` must hold for ``season``, counted from the raw event files of that season."""
    pattern, record, skip_no_play = RULES[dataset]
    total = 0
    folder = config.raw_dir("retrosheet", "event_files", season)
    for path in sorted(folder.iterdir()) if folder.is_dir() else []:
        if not pattern.search(path.name.removesuffix(".gz")):
            continue
        for line in _lines(path):
            kind, _, rest = line.partition(",")
            if kind != record:
                continue
            if skip_no_play and rest.split(",")[5].strip() == "NP":
                continue
            total += 1
    return total


def counter(dataset: str) -> Callable[[LakeConfig, int], int]:
    """The counting function of one dataset, in the shape the round-trip check registers."""
    return lambda config, season: expected_rows(config, dataset, season)
