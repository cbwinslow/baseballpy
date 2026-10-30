"""Every registered Retrosheet dataset is selectable with --datasets (retrosheet-source-review 5.7)."""

from pathlib import Path

import pytest
import respx
from conftest import RetroRepo
from test_retrosheet_coverage import GAMELOG, full_season

from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import datasets_for
from baseballpy.ingest.types import Selection
from baseballpy.sources import catalog
from baseballpy.sources.retrosheet.adapter import RetrosheetAdapter, known_datasets
from baseballpy.sources.retrosheet.api import (
    ACCESSORS,
    DATASET_UNIT,
    REFERENCE_UNIT,
    UNITS,
    RetrosheetSource,
    unit_of,
)


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


@respx.mock
def test_every_registry_dataset_is_selectable_and_readable(
    tmp_path: Path, retro_repo: RetroRepo
) -> None:
    full_season(retro_repo)
    reference = {
        "ballparks": b"PARKID,NAME,AKA,CITY,STATE,START,END,LEAGUE,NOTES\nBOS07,Fenway Park,,Boston,MA,1/1/1912,,AL,\n",
        "teams": b"TEAM,LEAGUE,CITY,NICKNAME,FIRST,LAST\nBOS,AL,Boston,Red Sox,1901,2024\n",
    }
    for ref_name, content in reference.items():
        retro_repo.add(f"reference/{ref_name}.csv", content)
    retro_repo.add("gamelog/GLWS.TXT", GAMELOG)
    retro_repo.mount()
    source = RetrosheetSource(cache_config=LakeConfig(home=tmp_path))
    names = _registry()
    assert {n for n in names if unit_of(n) != REFERENCE_UNIT} <= set(
        ACCESSORS
    )  # the table covers the registry
    for name in names:
        if name.startswith("reference_") and name.removeprefix("reference_") not in reference:
            continue  # this fake repository publishes only two reference files
        season = None if unit_of(name) == REFERENCE_UNIT else 2024
        table = source.table(name, season)
        assert table.schema.equals(datasets_for_name(name).schema), name
    with pytest.raises(ValueError, match="pass season"):
        source.table("events")
    with pytest.raises(ValueError, match="unknown retrosheet dataset"):
        source.table("nope", 2024)


def datasets_for_name(name: str):  # type: ignore[no-untyped-def]
    return next(d for d in datasets_for("retrosheet") if d.name == name)
