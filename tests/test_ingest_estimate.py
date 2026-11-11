"""`ingest --dry-run` says what a command would download: held vs missing, measured sizes, unknowns."""

import json
from pathlib import Path

import pyarrow as pa
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.stores import ProcessedStore
from baseballpy.ingest import estimate as estimate_module
from baseballpy.ingest.estimate import TypicalSize, estimate
from baseballpy.ingest.types import Selection
from baseballpy.sources import catalog

SIZES = {
    "statcast.pitches": TypicalSize(bytes_per_folder=100, folders_measured=3),
    "chadwick.register": TypicalSize(bytes_per_folder=40, folders_measured=1),
}


def _put(spec: DatasetSpec, cfg: LakeConfig, season: int | None) -> None:
    schema = spec.schema
    columns = {f.name: pa.nulls(1, f.type) for f in schema}
    ProcessedStore(cfg).put(
        spec, pa.table(columns, schema=schema), chunk_id="a" if season else "data", season=season
    )


@pytest.fixture(autouse=True)
def _registered() -> None:
    catalog.register_all()


def test_held_season_folders_are_not_counted_and_unknown_datasets_are_not_zero(
    tmp_path: Path,
) -> None:
    cfg = LakeConfig(home=tmp_path)
    _put(get_dataset("statcast", "pitches"), cfg, 2023)
    selection = Selection(sources=("statcast",), datasets=("pitches",), seasons=(2023, 2024))
    result = estimate([selection], cfg, SIZES)
    assert (result.datasets, result.folders_total) == (1, 2)
    assert (result.folders_held, result.folders_missing) == (1, 1)
    assert result.bytes_typical == 100  # only the missing 2024 folder, at the measured median
    assert result.unknown_datasets == 0
    # a default dataset with no measurement is unknown, never zero
    wide = estimate([Selection(sources=("statcast",), seasons=(2024,))], cfg, SIZES)
    assert wide.datasets > 1 and wide.unknown_datasets == wide.datasets - 1
    assert wide.bytes_typical == 100


def test_datasets_without_seasons_count_one_folder_and_need_no_season_list(tmp_path: Path) -> None:
    cfg = LakeConfig(home=tmp_path)
    selection = Selection(sources=("chadwick",), datasets=("register",))
    first = estimate([selection], cfg, SIZES)
    assert (first.folders_total, first.folders_missing, first.bytes_typical) == (1, 1, 40)
    _put(get_dataset("chadwick", "register"), cfg, None)
    second = estimate([selection], cfg, SIZES)
    assert (second.folders_held, second.folders_missing, second.bytes_typical) == (1, 0, 0)


def test_season_datasets_without_a_season_list_are_reported_not_estimated(tmp_path: Path) -> None:
    result = estimate(
        [Selection(sources=("statcast",), datasets=("pitches",))], LakeConfig(home=tmp_path), SIZES
    )
    assert result.seasons_given is False
    assert result.folders_total == 0 and result.unestimated_datasets == 1


def test_a_name_that_is_not_a_registered_dataset_is_listed_not_dropped(tmp_path: Path) -> None:
    selection = Selection(sources=("statcast",), datasets=("leaderboards",), seasons=(2024,))
    result = estimate([selection], LakeConfig(home=tmp_path), SIZES)
    assert result.unresolved == ("leaderboards",) and result.datasets == 0


def test_the_dry_run_prints_the_estimate_and_json_stays_one_object_per_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    monkeypatch.setattr(estimate_module, "load_typical_sizes", lambda: (SIZES, "2026-11-11"))
    runner = CliRunner()
    shown = runner.invoke(main, ["ingest", "statcast", "-s", "2024", "-d", "pitches", "--dry-run"])
    assert shown.exit_code == 0, shown.output
    assert "Estimate" in shown.output and "season folder" in shown.output
    assert "typical" in shown.output and "2026-11-11" in shown.output
    as_json = runner.invoke(
        main, ["ingest", "statcast", "-s", "2024", "-d", "pitches", "--dry-run", "--json"]
    )
    lines = [json.loads(line) for line in as_json.output.strip().splitlines()]
    assert len(lines) == 1 and lines[0]["status"] == "planned", "--json stays one object per job"
