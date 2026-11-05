"""One naming rule for every table: lower-case words joined by underscores, folder = view minus source."""

import re

import pytest

from baseballpy.core.datasets import DATASETS
from baseballpy.sources import catalog
from baseballpy.sources.lahman.schema import (
    UPSTREAM_NAMES,
    LahmanTable,
    canonical_table_name,
    upstream_name,
)

#: ``<source>_<words>``: lower case letters and digits, single underscores, no leading digit in a word list
RULE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")


def test_every_dataset_name_and_view_follow_the_rule_and_the_view_is_source_plus_folder() -> None:
    catalog.register_all()
    bad: list[str] = []
    for spec in DATASETS.values():
        if not RULE.match(spec.view):
            bad.append(f"view {spec.view!r}")
        if not re.match(r"^[a-z][a-z0-9_]*$", spec.name) or "__" in spec.name:
            bad.append(f"folder {spec.key!r}")
        if spec.source != "mlb_api" and spec.view != f"{spec.source}_{spec.name}":
            bad.append(f"view {spec.view!r} is not {spec.source}_{spec.name}")
    assert not bad, bad


def test_lahman_tables_use_underscores_and_provider_spelling_stays_at_the_edge() -> None:
    assert LahmanTable.AWARDS_SHARE_MANAGERS == "awards_share_managers"
    assert upstream_name("awards_share_managers") == "AwardsShareManagers"
    assert upstream_name(LahmanTable.FIELDING_OF_SPLIT) == "FieldingOFsplit"
    assert len(UPSTREAM_NAMES) == 27


@pytest.mark.parametrize(
    "spelling",
    ["fielding_of_split", "FieldingOFsplit", "fieldingofsplit", " FIELDING_OF_SPLIT "],
)
def test_any_spelling_of_a_lahman_table_gives_the_underscore_name(spelling: str) -> None:
    assert canonical_table_name(spelling) == "fielding_of_split"
