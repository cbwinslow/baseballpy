"""Rebuilding processed segments from raw (tasks 6.1 and 6.2 of response-log-segments). Written first.

The interface these tests fix (``baseballpy.core.segrebuild``):

* ``rebuild_season(config, source, season, normalize, unit_of, *, apply=False, force=False)`` finds the committed
  raw segments of the season that have no processed files yet (every segment with ``force=True``, the schema-change
  path), reads their raw rows (no network), keeps the newest body of each URL, groups the answers by unit,
  normalizes each unit and writes the processed files with ``SegmentWriter.refresh``. It returns a
  ``RebuildReport``: ``segments`` (rebuilt), ``units``, ``new_rows`` ({dataset: rows}), ``old_rows`` ({dataset:
  rows of the old part files}), ``moved`` (old files hidden in ``_legacy/``) and ``restored``.
* A dry run (``apply=False``) reads and counts and changes nothing.
* The old part files of the season are moved to ``_legacy/`` before any segment file appears, so a reader never
  sees both; a failure puts them back.
* The raw segment is not changed: the answers are already in it.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from baseballpy.core.config import LakeConfig
from baseballpy.core.rawsegconvert import convert_raw_to_segments
from baseballpy.core.responselog import Response
from baseballpy.core.segments import DatasetRows
from baseballpy.core.segrebuild import rebuild_season
from baseballpy.core.stores import RawStore

SOURCE = "fake_api"
SEASON = 2024
URL = "https://example.test/game/{pk}/{part}"


def _unit_of(url: str) -> str:
    parts = url.split("/")
    return parts[4] if len(parts) > 5 and parts[3] == "game" else url


def _normalize(unit_id: str, responses: Sequence[Response]) -> dict[str, DatasetRows]:
    """Two datasets cut from the 'feed' answer and one from the 'box' answer of a game."""
    rows: dict[str, DatasetRows] = {}
    for response in responses:
        data = json.loads(response.body)
        if response.url.endswith("/feed"):
            plays = pa.table({"game": [unit_id] * len(data["plays"]), "play": data["plays"]})
            info = pa.table({"game": [unit_id], "version": [data["version"]]})
            rows["plays"] = DatasetRows(plays, response.sha256)
            rows["info"] = DatasetRows(info, response.sha256)
        else:
            rows["box"] = DatasetRows(
                pa.table({"game": [unit_id], "runs": [data["runs"]]}), response.sha256
            )
    return rows


def _put_old_raw(
    config: LakeConfig, pk: int, feed: dict[str, object], fetched: str = "2024-05-01"
) -> None:
    raw = RawStore(config)
    body = json.dumps(feed).encode()
    raw.put(
        SOURCE,
        "plays",
        f"plays_{pk}_{fetched}.json",
        body,
        season=SEASON,
        source_ref=URL.format(pk=pk, part="feed"),
    )
    raw.put(
        SOURCE,
        "info",
        f"info_{pk}_{fetched}.json",
        body,
        season=SEASON,
        source_ref=URL.format(pk=pk, part="feed"),
    )
    box = json.dumps({"runs": 7}).encode()
    raw.put(
        SOURCE,
        "box",
        f"box_{pk}.json",
        box,
        season=SEASON,
        source_ref=URL.format(pk=pk, part="box"),
    )


def _old_parts(config: LakeConfig, dataset: str, rows: int) -> Path:
    folder = config.processed_dir(SOURCE, dataset, SEASON)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "part-old.parquet"
    pq.write_table(pa.table({"game": ["x"] * rows}), path)
    return path


def _lake(tmp_path: Path) -> LakeConfig:
    config = LakeConfig(home=tmp_path)
    _put_old_raw(config, 1, {"version": 1, "plays": ["a", "b"]})
    _put_old_raw(config, 2, {"version": 1, "plays": ["c"]})
    _old_parts(config, "plays", 3)
    _old_parts(config, "info", 2)
    _old_parts(config, "box", 2)
    report = convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, unit_of=_unit_of)
    assert report.verified and report.segments
    return config


def _segment_rows(config: LakeConfig, dataset: str) -> list[dict[str, object]]:
    folder = config.processed_dir(SOURCE, dataset, SEASON)
    rows: list[dict[str, object]] = []
    for path in sorted(folder.glob("seg-*.parquet")):
        rows += pq.read_table(path).to_pylist()
    return rows


def test_a_season_is_rebuilt_from_raw_with_the_same_rows(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    dry = rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of)
    assert dry.new_rows == {} and dry.moved == 0, "a dry run changes nothing"
    assert not list(config.processed_dir(SOURCE, "plays", SEASON).glob("seg-*.parquet"))
    report = rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of, apply=True)
    assert report.units == 2
    assert report.new_rows == {"plays": 3, "info": 2, "box": 2}
    assert report.old_rows == {"plays": 3, "info": 2, "box": 2}, (
        "the old part files held the same row counts"
    )
    assert sorted(r["play"] for r in _segment_rows(config, "plays")) == ["a", "b", "c"]
    assert all(r["_raw_sha256"] for r in _segment_rows(config, "box")), (
        "every row names its response"
    )
    again = rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of, apply=True)
    assert again.segments == [] and again.new_rows == report.new_rows, (
        "a rerun finds nothing to rebuild"
    )
    assert again.old_rows == report.old_rows and again.matches, (
        "the hidden old files still count for the comparison"
    )


def test_a_schema_change_is_applied_by_rebuilding_from_raw(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of, apply=True)

    def wider(unit_id: str, responses: Sequence[Response]) -> dict[str, DatasetRows]:
        rows = _normalize(unit_id, responses)
        if "box" in rows:
            table = rows["box"].table.append_column("extra", pa.array([1], pa.int32()))
            rows["box"] = DatasetRows(table, rows["box"].raw_sha256)
        return rows

    untouched = rebuild_season(config, SOURCE, SEASON, wider, _unit_of, apply=True)
    assert untouched.segments == [], "without force nothing is rebuilt"
    forced = rebuild_season(config, SOURCE, SEASON, wider, _unit_of, apply=True, force=True)
    assert forced.segments and forced.units == 2
    assert all("extra" in row for row in _segment_rows(config, "box"))
    assert len(_segment_rows(config, "plays")) == 3, "no row was lost or doubled"
    raw_rows = sum(
        pq.read_table(p).num_rows
        for p in (config.raw_root / SOURCE / f"season={SEASON}").glob("seg-*.parquet")
    )
    assert raw_rows == 4, "the raw answers are the same: two feeds and two boxes, none added"


def test_old_files_are_hidden_before_segments_appear(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    seen: list[tuple[int, int, int]] = []

    def spying(unit_id: str, responses: Sequence[Response]) -> dict[str, DatasetRows]:
        folder = config.processed_dir(SOURCE, "plays", SEASON)
        seen.append(
            (
                len(list(folder.glob("part-*.parquet"))),
                len(list((folder / "_legacy").glob("part-*.parquet"))),
                len(list(folder.glob("seg-*.parquet"))),
            )
        )
        return _normalize(unit_id, responses)

    report = rebuild_season(config, SOURCE, SEASON, spying, _unit_of, apply=True)
    assert seen and all(visible == 0 and hidden == 1 for visible, hidden, _ in seen), seen
    assert report.moved == 3, "one old part file per dataset was moved to _legacy"
    assert (config.processed_dir(SOURCE, "plays", SEASON) / "_legacy" / "part-old.parquet").exists()


def test_a_failure_puts_the_old_files_back(tmp_path: Path) -> None:
    config = _lake(tmp_path)

    def failing(unit_id: str, responses: Sequence[Response]) -> dict[str, DatasetRows]:
        raise RuntimeError("normalizer broke")

    with pytest.raises(RuntimeError, match="normalizer broke"):
        rebuild_season(config, SOURCE, SEASON, failing, _unit_of, apply=True)
    folder = config.processed_dir(SOURCE, "plays", SEASON)
    assert (folder / "part-old.parquet").exists(), "the old file is back where readers look"
    assert not list(folder.glob("seg-*.parquet"))


def test_a_url_with_two_stored_versions_is_rebuilt_from_the_newest_for_every_dataset(
    tmp_path: Path,
) -> None:
    """Design 5b rule 3: both feed datasets are cut from the same (newest) body."""
    config = LakeConfig(home=tmp_path)
    _put_old_raw(config, 1, {"version": 1, "plays": ["a"]}, fetched="2024-05-01")
    _put_old_raw(config, 1, {"version": 2, "plays": ["a", "b"]}, fetched="2024-06-01")
    convert_raw_to_segments(config, SOURCE, SEASON, dry_run=False, unit_of=_unit_of)
    report = rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of, apply=True)
    assert report.new_rows["plays"] == 2 and report.new_rows["info"] == 1
    assert [r["version"] for r in _segment_rows(config, "info")] == [2], (
        "info agrees with plays: the later body"
    )
    assert sorted(r["play"] for r in _segment_rows(config, "plays")) == ["a", "b"]


def test_hidden_old_files_are_deleted_only_when_the_row_counts_matched(tmp_path: Path) -> None:
    from baseballpy.core.segrebuild import RebuildReport, remove_legacy

    config = _lake(tmp_path)
    report = rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of, apply=True)
    legacy = config.processed_dir(SOURCE, "plays", SEASON) / "_legacy" / "part-old.parquet"
    bad = RebuildReport(new_rows={"plays": 99}, old_rows={"plays": 3})
    with pytest.raises(ValueError, match="do not match"):
        remove_legacy(config, SOURCE, SEASON, bad)
    assert legacy.exists(), "a mismatch removes nothing"
    assert report.matches
    assert remove_legacy(config, SOURCE, SEASON, report) == 3
    assert not legacy.exists()


def test_the_command_reports_a_dry_run_then_rebuilds_and_removes_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from baseballpy.cli import main
    from baseballpy.core import units

    monkeypatch.setenv("BASEBALLPY_HOME", str(tmp_path))
    config = _lake(tmp_path)
    monkeypatch.setitem(units._NORMALIZERS, SOURCE, lambda: _normalize)
    monkeypatch.setitem(units._RESOLVERS, SOURCE, _unit_of)
    runner = CliRunner()
    dry = runner.invoke(main, ["rebuild-segments", SOURCE, "--season", str(SEASON)])
    assert dry.exit_code == 0, dry.output
    assert "dry run" in dry.output
    assert not list(config.processed_dir(SOURCE, "plays", SEASON).glob("seg-*.parquet"))
    done = runner.invoke(
        main, ["rebuild-segments", SOURCE, "--season", str(SEASON), "--apply", "--remove-legacy"]
    )
    assert done.exit_code == 0, done.output
    assert list(config.processed_dir(SOURCE, "plays", SEASON).glob("seg-*.parquet"))
    assert not (config.processed_dir(SOURCE, "plays", SEASON) / "_legacy").exists()
    unknown = runner.invoke(main, ["rebuild-segments", "no_such_source"])
    assert unknown.exit_code != 0 and "no registered segment normalizer" in unknown.output


def test_only_the_datasets_the_rebuild_writes_have_their_old_files_hidden(tmp_path: Path) -> None:
    config = _lake(tmp_path)
    other = _old_parts(config, "awards", 5)  # a dataset the segments do not write
    report = rebuild_season(
        config, SOURCE, SEASON, _normalize, _unit_of, apply=True, datasets={"plays", "info", "box"}
    )
    assert other.exists(), "an unrelated dataset keeps its files"
    assert report.moved == 3


def test_a_failure_before_any_commit_puts_old_files_back_and_a_rerun_finishes(
    tmp_path: Path,
) -> None:
    """Both games sit in one segment, so a broken second game commits nothing; the rerun then completes."""
    config = _lake(tmp_path)

    def flaky(unit_id: str, responses: Sequence[Response]) -> dict[str, DatasetRows]:
        if unit_id == "2":
            raise RuntimeError("second game broke")
        return _normalize(unit_id, responses)

    with pytest.raises(RuntimeError, match="second game"):
        rebuild_season(config, SOURCE, SEASON, flaky, _unit_of, apply=True)
    folder = config.processed_dir(SOURCE, "plays", SEASON)
    assert (folder / "part-old.parquet").exists() and not list(folder.glob("seg-*.parquet"))
    done = rebuild_season(config, SOURCE, SEASON, _normalize, _unit_of, apply=True)
    assert done.new_rows["plays"] == 3 and not (folder / "part-old.parquet").exists()
