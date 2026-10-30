"""Every registered Retrosheet dataset is selectable with --datasets (retrosheet-source-review 5.7)."""

import pytest

from baseballpy.core.datasets import datasets_for
from baseballpy.ingest.types import Selection
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet.adapter import RetrosheetAdapter, known_datasets
from baseballpy.sources.retrosheet.api import DATASET_UNIT, REFERENCE_UNIT, UNITS, unit_of


def _registry() -> list[str]:
    catalog.register_all()
    return [d.name for d in datasets_for("retrosheet")]


def test_every_registry_dataset_belongs_to_exactly_one_unit() -> None:
    names = _registry()
    assert [n for n in names if unit_of(n) is None] == []
    # the table in api.py and the registry cannot drift apart
    written = {dataset for _, outputs in UNITS.values() for dataset, _ in outputs}
    season_names = {n for n in names if unit_of(n) != REFERENCE_UNIT}
    assert written == season_names == set(DATASET_UNIT)


def test_every_registry_dataset_is_selectable() -> None:
    adapter = RetrosheetAdapter(source=object())
    for name in _registry():
        jobs = adapter.plan(Selection(datasets=(name,), seasons=(2023,)))
        assert jobs, name
        task = "reference" if unit_of(name) == REFERENCE_UNIT else "season"
        assert [j.task for j in jobs] == [task], name
    assert set(_registry()) <= set(known_datasets())


def test_box_and_boxscore_names_select_the_unit_that_writes_them() -> None:
    adapter = RetrosheetAdapter(source=object())
    (job,) = adapter.plan(Selection(datasets=("box_games", "box_records"), seasons=(2023,)))
    assert job.param("datasets") == "box_accounts"
    (job,) = adapter.plan(Selection(datasets=("boxscores_batting",), seasons=(2023,)))
    assert job.param("datasets") == "boxscores"


def test_an_unknown_name_is_rejected_with_the_registry_list() -> None:
    adapter = RetrosheetAdapter(source=object())
    with pytest.raises(ValueError, match="nope.*box_games"):
        adapter.plan(Selection(datasets=("nope",), seasons=(2023,)))


def test_a_season_dataset_without_seasons_fails_with_an_instruction() -> None:
    adapter = RetrosheetAdapter(source=object())
    with pytest.raises(ValueError, match="--seasons"):
        adapter.plan(Selection(datasets=("events",)))
    # season-less datasets need no seasons
    assert [j.task for j in adapter.plan(Selection(datasets=("reference_teams",)))] == ["reference"]
