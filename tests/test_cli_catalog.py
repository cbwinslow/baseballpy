"""Tests for CLI catalog list and show subcommands."""

import json
from collections.abc import Generator
from pathlib import Path

import click
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from click.testing import CliRunner

from baseballpy.cli import catalog, main
from baseballpy.cli_catalog import register_catalog_commands, resolve_dataset
from baseballpy.core.config import reset_config
from baseballpy.core.datasets import DATASETS
from baseballpy.sources.catalog import register_all

register_catalog_commands(catalog)


@pytest.fixture(autouse=True)
def isolated_lake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Isolate lake home directory with temporary BASEBALLPY_HOME."""
    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    reset_config()
    yield
    reset_config()


@pytest.fixture
def runner() -> CliRunner:
    """Fixture providing a Click CliRunner."""
    return CliRunner()


def test_catalog_list_filters_by_source_and_json_parses(runner: CliRunner) -> None:
    """Verify catalog list --source filters results and outputs valid JSON lines."""
    result = runner.invoke(main, ["catalog", "list", "--source", "statcast", "--json"])
    assert result.exit_code == 0, result.output

    lines = [json.loads(line) for line in result.output.strip().splitlines() if line.strip()]
    assert len(lines) > 0
    for item in lines:
        assert item["source"] == "statcast"
        assert "name" in item
        assert "view" in item
        assert "partition" in item
        assert isinstance(item["columns"], int)
        assert isinstance(item["keys"], str)


def test_catalog_list_human_output(runner: CliRunner) -> None:
    """Verify catalog list prints a human-readable table."""
    result = runner.invoke(main, ["catalog", "list", "--source", "statcast"])
    assert result.exit_code == 0, result.output
    assert "Catalog Datasets" in result.output
    assert "statcast" in result.output
    assert "pitches" in result.output


def test_catalog_show_by_full_key(runner: CliRunner) -> None:
    """Verify catalog show works with a full 'source.name' key."""
    result = runner.invoke(main, ["catalog", "show", "statcast.pitches"])
    assert result.exit_code == 0, result.output
    assert "statcast.pitches" in result.output
    assert "statcast_pitches" in result.output
    assert "MISSING" in result.output


def test_catalog_show_by_unique_bare_name(runner: CliRunner) -> None:
    """Verify catalog show resolves an unambiguous bare dataset name."""
    register_all()
    name_counts: dict[str, int] = {}
    for spec in DATASETS.values():
        name_counts[spec.name] = name_counts.get(spec.name, 0) + 1

    unique_names = [name for name, count in name_counts.items() if count == 1]
    assert unique_names, "Expected at least one unique dataset name in registry"
    target_name = "pitches" if "pitches" in unique_names else unique_names[0]

    result = runner.invoke(main, ["catalog", "show", target_name])
    assert result.exit_code == 0, result.output
    assert target_name in result.output


def test_catalog_show_unknown_name_exits_code_two(runner: CliRunner) -> None:
    """Verify catalog show exits 2 via BadParameter on unknown dataset."""
    result = runner.invoke(main, ["catalog", "show", "totally_nonexistent_dataset_name"])
    assert result.exit_code == 2, result.output
    assert "unknown dataset" in result.output.lower() or "error" in result.output.lower()


def test_catalog_show_unknown_name_lists_close_matches(runner: CliRunner) -> None:
    """Verify close matches are suggested when an unknown dataset key is passed."""
    result = runner.invoke(main, ["catalog", "show", "statcast.pitch"])
    assert result.exit_code == 2, result.output
    assert "statcast.pitches" in result.output


def test_catalog_show_ambiguous_bare_name_exits_code_two(runner: CliRunner) -> None:
    """Verify ambiguous bare dataset name exits code 2 listing candidate keys."""
    register_all()
    name_to_sources: dict[str, list[str]] = {}
    for spec in DATASETS.values():
        name_to_sources.setdefault(spec.name, []).append(spec.source)

    ambiguous_name: str | None = None
    for name, sources in sorted(name_to_sources.items()):
        if len(sources) >= 2:
            ambiguous_name = name
            break

    if ambiguous_name is None:
        pytest.skip("No ambiguous dataset name found across registered DATASETS")

    result = runner.invoke(main, ["catalog", "show", ambiguous_name])
    assert result.exit_code == 2, result.output
    assert "ambiguous" in result.output.lower()


def test_catalog_show_json_includes_every_column(runner: CliRunner) -> None:
    """Verify catalog show --json includes all metadata and all schema columns."""
    register_all()
    spec = DATASETS["statcast.pitches"]

    result = runner.invoke(main, ["catalog", "show", "statcast.pitches", "--json"])
    assert result.exit_code == 0, result.output

    data = json.loads(result.output)
    assert data["key"] == "statcast.pitches"
    assert data["source"] == "statcast"
    assert data["name"] == "pitches"
    assert data["view"] == spec.view
    assert data["description"] == spec.description
    assert data["partition"] == spec.partition
    assert data["keys"] == list(spec.keys)
    assert data["endpoint_doc"] == spec.endpoint_doc
    assert data["status"] in ("MISSING", "INGESTED")
    assert isinstance(data["files"], int)
    assert isinstance(data["rows"], int)
    assert isinstance(data["seasons"], list)

    columns = data["columns"]
    assert len(columns) == len(spec.schema)

    schema_dict = {f.name: (str(f.type), f.nullable) for f in spec.schema}
    for col in columns:
        assert col["name"] in schema_dict
        expected_type, expected_nullable = schema_dict[col["name"]]
        assert col["type"] == expected_type
        assert col["nullable"] == expected_nullable


def test_catalog_show_fabricated_parquet_reports_ingested(
    tmp_path: Path, runner: CliRunner
) -> None:
    """Verify fabricated parquet in lake makes show report INGESTED and row count."""
    target_dir = tmp_path / "processed" / "statcast" / "pitches" / "season=2020"
    target_dir.mkdir(parents=True, exist_ok=True)

    sample_table = pa.table(
        {
            "game_pk": [1001, 1002, 1003],
            "at_bat_number": [1, 1, 2],
            "pitch_number": [1, 2, 1],
        }
    )
    pq.write_table(sample_table, target_dir / "pitches.parquet")

    result = runner.invoke(main, ["catalog", "show", "statcast.pitches"])
    assert result.exit_code == 0, result.output
    assert "INGESTED" in result.output
    assert "2020" in result.output
    assert "3" in result.output

    result_json = runner.invoke(main, ["catalog", "show", "statcast.pitches", "--json"])
    assert result_json.exit_code == 0, result_json.output
    data = json.loads(result_json.output)
    assert data["status"] == "INGESTED"
    assert data["rows"] == 3
    assert data["files"] == 1
    assert data["seasons"] == [2020]


def test_resolve_dataset_direct() -> None:
    """Unit test dataset resolver directly for exact, bare, and unknown lookups."""
    register_all()
    exact = resolve_dataset("statcast.pitches")
    assert exact.key == "statcast.pitches"

    bare = resolve_dataset("pitches")
    assert bare.key == "statcast.pitches"

    with pytest.raises(click.BadParameter):
        resolve_dataset("nonexistent_unknown_dataset_xyz")
