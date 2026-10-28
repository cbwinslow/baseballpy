"""The MLB glossary parser and the table of leaderboard columns it describes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import build_column_descriptions as build  # noqa: E402

from baseballpy.sources.statcast.lb_tables import LEADERBOARD_COLUMNS  # noqa: E402

BS = chr(92)
PAGE = (
    '{"body":"'
    + BS
    + "u003cp"
    + BS
    + "u003eShort."
    + BS
    + "u003c/p"
    + BS
    + "u003e"
    + BS
    + "u003cp"
    + BS
    + "u003eSprint Speed is a "
    + BS
    + "u003ca href="
    + BS
    + '"x'
    + BS
    + '"'
    + BS
    + "u003eStatcast"
    + BS
    + "u003c/a"
    + BS
    + "u003e metric that measures feet per second. It was introduced in 2017."
    + BS
    + "u003c/p"
    + BS
    + 'u003e"}'
)


def test_the_first_sentence_of_the_first_real_paragraph_is_taken() -> None:
    assert (
        build.glossary_definition(PAGE)
        == "Sprint Speed is a Statcast metric that measures feet per second."
    )


def test_a_page_without_a_definition_gives_an_empty_string() -> None:
    assert build.glossary_definition("<html>no body here</html>") == ""


def test_every_described_column_exists_on_a_leaderboard() -> None:
    columns = {c[0] for cols in LEADERBOARD_COLUMNS.values() for c in cols}
    assert set(build.GLOSSARY_COLUMNS) <= columns


def test_only_exact_metric_names_are_mapped() -> None:
    # a column such as est_woba or last_x_xwoba is not named after the glossary metric itself
    assert not [
        c for c in build.GLOSSARY_COLUMNS if c.startswith(("est_", "last_", "penultimate_"))
    ]
