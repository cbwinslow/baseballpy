"""The game-log field guide parser expands ranges only by structure the document states."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import retro_glfields as g  # noqa: E402

GUIDE = """Field(s)  Meaning
    1     Date in the form "yyyymmdd"
  4-5     Visiting team and league
10-11     Visiting and home team score (unquoted)
22-23     Visiting team offensive statistics (unquoted) (in order):
             at-bats
             hits
24-25     Home team offensive statistics
26-27     Home plate umpire ID and name
28-33     Visiting starting players ID, name and defensive position
"""


def test_ranges_expand_by_the_structure_of_the_document() -> None:
    out = g.describe(g.parse(GUIDE), count=33)
    assert out[1] == 'Date in the form "yyyymmdd"'
    assert (out[4], out[5]) == ("Visiting team", "Visiting league")
    assert (out[10], out[11]) == ("Visiting team score", "Home team score")
    assert out[22] == "Visiting team offensive: at-bats" and out[23].endswith("hits")
    assert out[24] == "Home team offensive: at-bats" and out[25].endswith("hits")
    assert (out[26], out[27]) == ("Home plate umpire ID", "Home plate umpire name")
    assert out[28].endswith("batting order 1: ID") and out[33].endswith("2: defensive position")


def test_fields_the_document_does_not_cover_are_absent() -> None:
    assert 2 not in g.describe(g.parse(GUIDE), count=33)
