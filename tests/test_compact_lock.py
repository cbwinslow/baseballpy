"""One compaction per dataset at a time (change compact-one-writer).

Two compactions of one dataset once chose the same file numbers and overwrote each other's files
(MLB 2019 player boxscores, 2026-11-08). A second one must be refused and change nothing.
"""

import hashlib
import subprocess
import sys
from pathlib import Path

import pyarrow as pa
import pytest
from click.testing import CliRunner

from baseballpy.cli import main
from baseballpy.core.compact import compact_dataset
from baseballpy.core.config import LakeConfig
from baseballpy.core.datasets import DatasetSpec, get_dataset
from baseballpy.core.hostlock import HostBusyError, claim_named, release_all
from baseballpy.core.stores import ProcessedStore
from baseballpy.sources import catalog

#: claims a lock name, says so, then waits for a line and ends abruptly with no clean-up (a crash)
_HOLD = (
    "import os, sys\n"
    "from pathlib import Path\n"
    "from baseballpy.core.hostlock import claim_named\n"
    "claim_named(Path(sys.argv[1]), sys.argv[2], 'busy')\n"
    "print('held', flush=True)\n"
    "sys.stdin.readline()\n"
    "os._exit(1)\n"
)


def _hold(directory: Path, name: str) -> "subprocess.Popen[str]":
    process = subprocess.Popen(  # noqa: S603 - runs this interpreter on a fixed script
        [sys.executable, "-c", _HOLD, str(directory), name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    assert process.stdout.readline().strip() == "held"
    return process


def _crash(process: "subprocess.Popen[str]") -> None:
    assert process.stdin is not None
    process.stdin.write("\n")
    process.stdin.flush()
    process.wait(timeout=30)


def _pitches(speeds: list[float], year: int) -> pa.Table:
    schema = get_dataset("statcast", "pitches").schema
    n = len(speeds)
    columns = {f.name: pa.nulls(n, f.type) for f in schema}
    columns["release_speed"] = pa.array(speeds, schema.field("release_speed").type)
    columns["game_year"] = pa.array([year] * n, schema.field("game_year").type)
    return pa.table(columns, schema=schema)


@pytest.fixture
def spec() -> DatasetSpec:
    catalog.register_all()
    return get_dataset("statcast", "pitches")


@pytest.fixture
def lake(tmp_path: Path, spec: DatasetSpec) -> LakeConfig:
    cfg = LakeConfig(home=tmp_path)
    store = ProcessedStore(cfg)
    for chunk, speeds in (("a", [90.0, 91.0]), ("b", [92.0]), ("c", [93.0, 94.0])):
        store.put(spec, _pitches(speeds, 2023), chunk_id=chunk, season=2023)
    return cfg


def _lock_name(spec: DatasetSpec) -> str:
    return f"compact-{spec.source}-{spec.name}"


def _snapshot(cfg: LakeConfig, spec: DatasetSpec) -> dict[str, str]:
    """Every file of the dataset (parts, compacted files, the records) with its digest."""
    root = cfg.processed_dir(spec.source, spec.name)
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_a_second_compaction_of_one_dataset_is_refused_and_changes_nothing(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    before = _snapshot(lake, spec)
    holder = _hold(lake.locks_root, _lock_name(spec))
    try:
        with pytest.raises(HostBusyError):
            compact_dataset(spec, lake)
        assert _snapshot(lake, spec) == before
    finally:
        _crash(holder)  # no clean exit: the operating system drops the lock with the process
        release_all(lake.locks_root)
    report = compact_dataset(spec, lake)  # free again once the holder is gone
    assert report.chunks == 3 and report.files_after == 1


def test_another_dataset_is_not_blocked_and_a_dry_run_needs_no_lock(
    lake: LakeConfig, spec: DatasetSpec
) -> None:
    other = _hold(lake.locks_root, "compact-lahman-awards_players")
    holder = _hold(lake.locks_root, _lock_name(spec))
    try:
        assert compact_dataset(spec, lake, dry_run=True).files_after == 1  # reads only
        assert compact_dataset(get_dataset("statcast", "pitches_minors"), lake).chunks == 0
    finally:
        _crash(holder)
        _crash(other)
        release_all(lake.locks_root)


def test_the_lock_is_given_back_when_a_compaction_ends(lake: LakeConfig, spec: DatasetSpec) -> None:
    compact_dataset(spec, lake)
    # a lock still held by this process would make the next claim from another process fail
    holder = _hold(lake.locks_root, _lock_name(spec))
    _crash(holder)
    claim_named(lake.locks_root, _lock_name(spec), "busy")
    release_all(lake.locks_root)


def test_a_failed_compaction_still_gives_the_lock_back(
    lake: LakeConfig, spec: DatasetSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    from baseballpy.core import compact as compact_module

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(compact_module, "_compact_group", boom)
    with pytest.raises(RuntimeError, match="boom"):
        compact_dataset(spec, lake)
    holder = _hold(lake.locks_root, _lock_name(spec))  # would be refused if still held here
    _crash(holder)


def test_the_compact_command_skips_a_busy_dataset_and_fails(
    lake: LakeConfig, spec: DatasetSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BASEBALLPY_HOME", str(lake.home))
    before = _snapshot(lake, spec)
    holder = _hold(lake.locks_root, _lock_name(spec))
    try:
        result = CliRunner().invoke(
            main, ["compact", "--source", "statcast", "--dataset", "pitches"]
        )
    finally:
        _crash(holder)
        release_all(lake.locks_root)
    assert result.exit_code != 0
    assert "busy" in result.output
    assert _snapshot(lake, spec) == before
