"""A sample download is compared with the lake (change sample-compare, ADR 108).

The interface these tests fix (``baseballpy.ingest.sample``):

* ``compare_lakes(sample, lake, sources=())`` compares two lakes offline. For every completed processed chunk
  of the sample it finds the same chunk of the lake (a part or a compacted file) and compares the rows sorted
  by the registered keys, all registered columns. For every raw file of the sample it compares the sha256 with
  the lake's record. It returns a ``SampleReport``.
* The report: ``compared`` and ``identical`` (processed chunks), ``missing_in_lake``, ``raw_compared`` and
  ``raw_identical``, ``differences`` (a list of ``Difference(kind, source, dataset, item, detail)`` with kind
  ``rows_differ``, ``missing_in_lake`` or ``raw_differs``) and ``failed`` (true when a chunk's rows or a raw
  file's bytes differ; a chunk the lake never fetched is reported but does not fail).
* ``run_scratch_ingest(source, home, *, seasons, datasets, limit)`` runs the normal ingest in a child process
  with ``BASEBALLPY_HOME=home`` and returns its exit code; the command ``baseballpy verify-sample`` uses it, then
  compares the scratch home with the real lake and exits 1 when the report failed.
"""

from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import get_dataset
from baseballpy.core.stores import ProcessedStore, RawStore
from baseballpy.ingest import sample as sample_module
from baseballpy.ingest.sample import compare_lakes
from baseballpy.sources import catalog

RAW_NAME = "2023-06-01_2023-06-05.csv"


def _pitches(speeds: list[float]) -> pa.Table:
    schema = get_dataset("statcast", "pitches").schema
    n = len(speeds)
    columns: dict[str, Any] = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["release_speed"] = pa.array(speeds, schema.field("release_speed").type)
    columns["game_pk"] = pa.array([1] * n, schema.field("game_pk").type)
    columns["at_bat_number"] = pa.array(list(range(1, n + 1)), schema.field("at_bat_number").type)
    columns["pitch_number"] = pa.array([1] * n, schema.field("pitch_number").type)
    columns["game_year"] = pa.array([2023] * n, schema.field("game_year").type)
    return pa.table(columns, schema=schema)


def _lake(home: Path, chunks: dict[str, list[float]], raw: bytes = b"a,b\n1,2\n") -> LakeConfig:
    catalog.register_all()
    cfg = LakeConfig(home=home)
    spec = get_dataset("statcast", "pitches")
    for chunk, speeds in chunks.items():
        ProcessedStore(cfg).put(spec, _pitches(speeds), chunk_id=chunk, season=2023)
    RawStore(cfg).put("statcast", "pitches", RAW_NAME, raw, season=2023, source_ref="https://x/y")
    return cfg


def test_identical_lakes_compare_identical(tmp_path: Path) -> None:
    sample = _lake(tmp_path / "sample", {"a": [90.0, 91.0], "b": [92.0]})
    lake = _lake(tmp_path / "lake", {"a": [90.0, 91.0], "b": [92.0]})
    report = compare_lakes(sample, lake, ("statcast",))
    assert (report.compared, report.identical, report.missing_in_lake) == (2, 2, 0)
    assert (report.raw_compared, report.raw_identical) == (1, 1)
    assert report.differences == [] and not report.failed


def test_a_compacted_chunk_compares_like_a_part(tmp_path: Path) -> None:
    sample = _lake(tmp_path / "sample", {"a": [90.0], "b": [92.0]})
    lake = _lake(tmp_path / "lake", {"a": [90.0], "b": [92.0]})
    compact_dataset(get_dataset("statcast", "pitches"), lake)
    report = compare_lakes(sample, lake, ("statcast",))
    assert report.identical == 2 and not report.failed


def test_a_changed_value_a_missing_chunk_and_a_changed_raw_file_are_reported(
    tmp_path: Path,
) -> None:
    sample = _lake(tmp_path / "sample", {"a": [90.0, 91.0], "b": [92.0]})
    lake = _lake(tmp_path / "lake", {"a": [90.0, 99.0]}, raw=b"a,b\n1,3\n")
    report = compare_lakes(sample, lake, ("statcast",))
    kinds = sorted(d.kind for d in report.differences)
    assert kinds == ["missing_in_lake", "raw_differs", "rows_differ"]
    changed = next(d for d in report.differences if d.kind == "rows_differ")
    assert changed.item.endswith("a") and "release_speed" in changed.detail
    assert (report.compared, report.identical, report.missing_in_lake) == (2, 0, 1)
    assert report.failed
    only_missing = compare_lakes(
        _lake(tmp_path / "s2", {"a": [90.0], "b": [92.0]}),
        _lake(tmp_path / "l2", {"a": [90.0]}),
        ("statcast",),
    )
    assert [d.kind for d in only_missing.differences] == ["missing_in_lake"]
    assert not only_missing.failed, (
        "a chunk the lake never fetched is reported but is not a difference"
    )


def test_the_verify_sample_command_exits_one_on_a_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lake = _lake(tmp_path / "lake", {"a": [90.0]})
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    calls: list[tuple[str, Path]] = []

    def fake_scratch(source: str, home: Path, **kwargs: Any) -> int:
        calls.append((source, home))
        _lake(home, {"a": [95.0]})  # the "download" gives another value than the lake holds
        return 0

    monkeypatch.setattr(sample_module, "run_scratch_ingest", fake_scratch)
    result = CliRunner().invoke(main, ["verify-sample", "statcast", "-s", "2023", "-d", "pitches"])
    assert result.exit_code == 1, result.output
    assert calls and calls[0][0] == "statcast" and calls[0][1] != lake.home
    assert "rows_differ" in result.output and "differ" in result.output
    assert not calls[0][1].exists(), "the scratch home is removed"


def test_dictionary_columns_with_different_dictionaries_compare_by_value() -> None:
    """Statcast stores category columns as dictionaries; two downloads can order the dictionary differently."""
    catalog.register_all()
    spec = get_dataset("statcast", "pitches")
    field = spec.schema.field("game_type")
    assert pa.types.is_dictionary(field.type)
    index = _pitches([90.0, 91.0]).schema.get_field_index("game_type")

    def with_game_type(indices: list[int], dictionary: list[str]) -> pa.Table:
        array = pa.DictionaryArray.from_arrays(
            pa.array(indices, pa.int8()), pa.array(dictionary)
        ).cast(field.type)
        return _pitches([90.0, 91.0]).set_column(index, field, array)

    one = with_game_type([0, 1], ["R", "S"])  # R then S
    two = with_game_type([1, 0], ["S", "R"])  # the same values, a different dictionary order
    assert one["game_type"].to_pylist() == two["game_type"].to_pylist() == ["R", "S"]
    assert not one["game_type"].equals(two["game_type"]), "the arrays differ by dictionary order"
    assert sample_module._rows_differ(one, two, spec) is None
    other = with_game_type([0, 0], ["R", "S"])  # a real difference is still found
    assert sample_module._rows_differ(one, other, spec) == "column game_type differs"
